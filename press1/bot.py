"""Telegram control panel for the dialer: python -m press1.bot

Only TELEGRAM_OWNER_ID can use it. All compliance checks stay in the dialer.
"""
import asyncio
import logging
import os
import threading
from pathlib import Path

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from . import config, db, dialer
from .compliance import normalize_phone

log = logging.getLogger("press1.bot")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID", "0"))

HELP = """Press 1 dialer

Setup (key messages are deleted after saving):
/set NAME value - e.g. /set PLIVO_AUTH_ID MAxxxx
/settings - current settings (secrets masked)
/check - check Plivo keys and webhook server

Test:
/set TEST_NUMBERS +1..., +1...  - your own numbers
/test +1... - one test call

Campaign:
send a .csv file - checked (dry run), no calls
/run name - start the campaign from the last CSV
/status - progress  ·  /stop - stop
/dnc +1... - add a number to the do-not-call list"""


class Campaign:
    def __init__(self):
        self.thread = None
        self.stop = threading.Event()
        self.name = None
        self.progress = {}

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()


state = Campaign()


def owner_only(fn):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id != OWNER_ID:
            log.warning("rejected user %s", user.id if user else None)
            return
        db.load_settings()
        return await fn(update, ctx)
    return wrapper


def mask(name, value):
    if name in config.SECRET and value:
        return value[:3] + "…" + value[-2:]
    return value


@owner_only
async def start(update, ctx):
    await update.message.reply_text(HELP)


@owner_only
async def set_cmd(update, ctx):
    # Delete first: the message holds a secret and should not stay in chat history.
    try:
        await update.message.delete()
    except Exception:
        pass
    if len(ctx.args) < 2 or ctx.args[0].upper() not in config.EDITABLE:
        names = ", ".join(config.EDITABLE)
        await update.effective_chat.send_message(f"Usage: /set NAME value\nNames: {names}")
        return
    name, value = ctx.args[0].upper(), " ".join(ctx.args[1:]).strip()
    try:
        config.EDITABLE[name](value)
    except ValueError:
        await update.effective_chat.send_message(f"{name}: invalid value")
        return
    with db.connect() as conn:
        db.set_setting(conn, name, value)
    db.load_settings()
    await update.effective_chat.send_message(f"✅ {name} = {mask(name, value)}")


@owner_only
async def settings(update, ctx):
    lines = [f"{n} = {mask(n, str(getattr(config, n, ''))) or '—'}" for n in config.EDITABLE]
    await update.message.reply_text("\n".join(lines))


def _check_sync():
    out = []
    missing = [n for n in ("PLIVO_AUTH_ID", "PLIVO_AUTH_TOKEN", "CALLER_ID", "PUBLIC_URL",
                           "THREECX_SIP_URI") if not getattr(config, n)]
    out.append("❌ not set: " + ", ".join(missing) if missing else "✅ all required settings set")
    try:
        acc = dialer.client().account.get()
        out.append(f"✅ Plivo: {acc.name}, balance {acc.cash_credits}")
    except Exception as e:
        out.append(f"❌ Plivo: {e}")
    try:
        r = requests.get(config.PUBLIC_URL + "/health", timeout=5)
        out.append("✅ webhook server reachable" if r.ok else f"❌ webhook /health: {r.status_code}")
    except Exception as e:
        out.append(f"❌ webhook server: {e}")
    return "\n".join(out)


@owner_only
async def check(update, ctx):
    await update.message.reply_text(await asyncio.to_thread(_check_sync))


@owner_only
async def test(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Usage: /test +1XXXXXXXXXX")
        return
    try:
        req = await asyncio.to_thread(dialer.test_call, ctx.args[0])
        await update.message.reply_text(f"📞 Calling… request {req}\nPress 1 — you should reach 3CX.")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


@owner_only
async def upload(update, ctx):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".csv"):
        await update.message.reply_text("I need a .csv file")
        return
    UPLOAD_DIR.mkdir(exist_ok=True)
    path = UPLOAD_DIR / "contacts.csv"
    await (await doc.get_file()).download_to_drive(path)
    stats = await asyncio.to_thread(dialer.run, str(path), "dry-run", True)
    ok = stats.get("would_call", 0)
    skipped = "\n".join(f"  {k}: {v}" for k, v in stats.items() if k != "would_call") or "  none"
    await update.message.reply_text(
        f"📄 {doc.file_name} saved\nCan call right now: {ok}\nSkipped:\n{skipped}\n\n"
        "Skips for calling hours will be retried in the next run.\nStart: /run campaign_name"
    )


@owner_only
async def run_cmd(update, ctx):
    if state.running:
        await update.message.reply_text(f"Already running: {state.name}. /stop first.")
        return
    if not ctx.args:
        await update.message.reply_text("Usage: /run campaign_name")
        return
    if not (UPLOAD_DIR / "contacts.csv").exists():
        await update.message.reply_text("Send the contacts CSV first.")
        return
    name = ctx.args[0]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Start", callback_data=f"run:{name}"),
                                InlineKeyboardButton("Cancel", callback_data="cancel")]])
    await update.message.reply_text(
        f"Start '{name}'?\nup to {config.MAX_CONCURRENT_CALLS} simultaneous calls, "
        f"{config.CALLS_PER_SECOND}/s, {config.MAX_AGENT_CHANNELS} lines to 3CX",
        reply_markup=kb,
    )


@owner_only
async def button(update, ctx):
    q = update.callback_query
    await q.answer()
    if q.data == "cancel":
        await q.edit_message_text("Cancelled")
        return
    name = q.data.split(":", 1)[1]
    if state.running:
        await q.edit_message_text("Already running")
        return
    loop = asyncio.get_running_loop()
    chat_id = q.message.chat_id
    state.stop.clear()
    state.name, state.progress = name, {}

    def work():
        try:
            stats = dialer.run(str(UPLOAD_DIR / "contacts.csv"), name, stop=state.stop,
                               on_progress=lambda s: setattr(state, "progress", s))
            text = f"🏁 '{name}' finished dialing: {stats}\nResults: /status"
        except Exception as e:
            log.exception("campaign failed")
            text = f"❌ '{name}' failed: {e}"
        asyncio.run_coroutine_threadsafe(ctx.bot.send_message(chat_id, text), loop)

    state.thread = threading.Thread(target=work, daemon=True, name=f"campaign-{name}")
    state.thread.start()
    await q.edit_message_text(f"🚀 '{name}' started. /status · /stop")


@owner_only
async def stop(update, ctx):
    if not state.running:
        await update.message.reply_text("Nothing is running")
        return
    state.stop.set()
    await update.message.reply_text("⏹ No new calls will be placed; calls in progress will finish.")


@owner_only
async def status(update, ctx):
    with db.connect() as conn:
        active = db.active_calls(conn)
        agents = db.transferred_calls(conn)
        results = db.campaign_stats(conn, state.name) if state.name else {}
    head = f"{'▶️ running' if state.running else '⏸ idle'}: {state.name or '—'}"
    await update.message.reply_text(
        f"{head}\nactive calls: {active}/{config.MAX_CONCURRENT_CALLS}\n"
        f"on 3CX: {agents}/{config.MAX_AGENT_CHANNELS}\n"
        f"dialer: {state.progress}\nresults: {results}"
    )


@owner_only
async def dnc(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Usage: /dnc +1XXXXXXXXXX")
        return
    phone = normalize_phone(ctx.args[0])
    with db.connect() as conn:
        db.add_dnc(conn, phone, "telegram")
    await update.message.reply_text(f"🚫 {phone} added to DNC")


def build(token):
    app = Application.builder().token(token).build()
    for name, fn in [("start", start), ("help", start), ("set", set_cmd), ("settings", settings),
                     ("check", check), ("test", test), ("run", run_cmd), ("stop", stop),
                     ("status", status), ("dnc", dnc)]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.Document.ALL, upload))
    return app


def main():
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not OWNER_ID:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_ID")
    build(token).run_polling()


if __name__ == "__main__":
    main()
