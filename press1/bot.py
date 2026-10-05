"""Telegram control panel for the dialer: python -m press1.bot

Only TELEGRAM_OWNER_ID can use it. All compliance checks stay in the dialer.
Everything is driven by inline menus; the slash commands still work as shortcuts.
"""
import asyncio
import html
import logging
import os
import threading

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from . import config, control, db, dialer, runner, validate
from .compliance import normalize_phone
from .control import current, mask

log = logging.getLogger("press1.bot")

OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID") or 0)


# name -> (label, hint shown when asking). Validation lives in validate.py.
FIELDS = {
    "PLIVO_AUTH_ID": ("Auth ID", "Plivo Console → Overview → <b>Auth ID</b>"),
    "PLIVO_AUTH_TOKEN": ("Auth Token", "Plivo Console → Overview → <b>Auth Token</b>.\n"
                         "Сообщение удалится сразу после сохранения."),
    "CALLER_ID": ("Caller ID", "Твой номер в Plivo, который увидит клиент: +1XXXXXXXXXX.\n"
                  "Проще выбрать кнопкой «Мои номера»."),
    "PUBLIC_URL": ("Webhook URL", "Публичный https-адрес сервера с приложением "
                   "(Plivo шлёт туда события звонков)."),
    "THREECX_SIP_URI": ("SIP URI", "Полный адрес очереди 3CX: sip:800@company.3cx.us\n"
                        "Или нажми «Мастер настройки»."),
    "MAX_AGENT_CHANNELS": ("Линий на 3CX", "Сколько звонков одновременно могут принять "
                           "агенты/транк 3CX (1–500)."),
    "MAX_CONCURRENT_CALLS": ("Одновременных звонков", "Сколько звонков в эфире одновременно "
                             "(каналы Plivo, 1–500)."),
    "CALLS_PER_SECOND": ("Звонков в секунду", "Лимит CPS твоего аккаунта Plivo (0.1–50)."),
    "STALE_CALL_MINUTES": ("Зависший звонок, мин", "Через сколько минут считать звонок "
                           "завершённым, если Plivo не прислал hangup (1–240)."),
    "COMPANY_NAME": ("Компания", "Название, которое произносится в сообщении."),
    "OPT_OUT_PHONE": ("Номер для отписки", "Номер, который озвучивается для отказа "
                      "от звонков: +1XXXXXXXXXX."),
    "TEST_NUMBERS": ("Тестовые номера", "Твои собственные номера через запятую — "
                     "только на них разрешён тестовый звонок."),
}

SECTIONS = {
    "plivo": ("📡 Plivo", ["PLIVO_AUTH_ID", "PLIVO_AUTH_TOKEN", "CALLER_ID", "PUBLIC_URL"]),
    "3cx": ("☎️ 3CX", ["THREECX_SIP_URI", "MAX_AGENT_CHANNELS"]),
    "limits": ("⚡️ Нагрузка", ["MAX_CONCURRENT_CALLS", "CALLS_PER_SECOND", "STALE_CALL_MINUTES"]),
    "company": ("🏢 Компания", ["COMPANY_NAME", "OPT_OUT_PHONE", "TEST_NUMBERS"]),
}
FIELD_SECTION = {f: s for s, (_, fs) in SECTIONS.items() for f in fs}


save = control.save
ready = control.ready
warnings = control.warnings


# ---------------------------------------------------------------- screens

def kb(*rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t, d in r]
                                 for r in rows])


BACK = ("⬅️ Меню", "m:main")


def screen_main():
    def dot(s):
        return "🟢" if ready(s) else "🔴"
    st = runner.get()
    run = f"▶️ идёт кампания <b>{html.escape(st['name'])}</b>" if st["busy"] else "⏸ кампания не запущена"
    text = (f"<b>📞 Press 1 — панель управления</b>\n\n"
            f"{dot('plivo')} Plivo   {dot('3cx')} 3CX\n{run}\n\nВыбери раздел:")
    return text, kb(
        [("📡 Plivo", "m:plivo"), ("☎️ 3CX", "m:3cx")],
        [("⚡️ Нагрузка", "m:limits"), ("🏢 Компания", "m:company")],
        [("🧪 Тестовый звонок", "m:test"), ("🚀 Кампания", "m:campaign")],
        [("🩺 Проверить всё", "a:check")],
    )


def screen_section(key, note=""):
    title, fields = SECTIONS[key]
    lines = [f"<b>{title}</b>", ""]
    for f in fields:
        v = current(f)
        shown = html.escape(mask(f, v)) if v else "<i>не задано</i>"
        lines.append(f"✅ {FIELDS[f][0]}: <code>{shown}</code>" if v else f"⚪️ {FIELDS[f][0]}: {shown}")
    lines += [f"\n⚠️ {w}" for w in warnings(key)]
    if note:
        lines.append("\n" + note)
    rows = [[(f"✏️ {FIELDS[f][0]}", f"e:{f}") for f in fields[i:i + 2]]
            for i in range(0, len(fields), 2)]
    if key == "plivo":
        rows.append([("📋 Мои номера", "a:numbers"), ("🔌 Проверить", "a:plivo")])
    elif key == "3cx":
        rows.append([("🧙 Мастер настройки", "a:wiz3cx"), ("🔌 Проверить", "a:3cx")])
    rows.append([BACK])
    return "\n".join(lines), kb(*rows)


def screen_ask(name, error=""):
    label, hint = FIELDS[name]
    v = current(name)
    text = f"<b>✏️ {label}</b>\n\n{hint}"
    if v and name not in config.SECRET:
        text += f"\n\nСейчас: <code>{html.escape(v)}</code>"
    if error:
        text += f"\n\n❌ {html.escape(error)}"
    return text + "\n\n👇 Отправь значение сообщением", kb([("✖️ Отмена", f"m:{FIELD_SECTION[name]}")])


def screen_test(note=""):
    nums = [n for n in config.TEST_NUMBERS.split(",") if n.strip()]
    text = "<b>🧪 Тестовый звонок</b>\n\nПозвоню на твой номер: возьми трубку, нажми 1 — должен соединить с 3CX."
    if not nums:
        text += "\n\n⚪️ Тестовых номеров нет — добавь в разделе 🏢 Компания."
    if note:
        text += "\n\n" + note
    rows = [[(f"📞 {n.strip()}", f"t:{n.strip()}")] for n in nums[:6]]
    rows.append([("➕ Тестовые номера", "e:TEST_NUMBERS")])
    rows.append([BACK])
    return text, kb(*rows)


STATUS_RU = {"idle": "не запускалась", "pending": "запускается…", "running": "идёт",
             "stopping": "останавливается…", "stopped": "остановлена", "done": "завершена",
             "failed": "ошибка"}


def screen_campaign(note=""):
    csv_ok = runner.contacts_path().exists()
    st = runner.get()
    with db.connect() as conn:
        active = db.active_calls(conn)
        agents = db.transferred_calls(conn)
        results = db.campaign_stats(conn, st["name"]) if st["name"] else {}
    icon = "▶️" if st["busy"] else "⏸"
    name = f": <b>{html.escape(st['name'])}</b>" if st["name"] else ""
    text = (f"<b>🚀 Кампания</b>\n\n{icon} {STATUS_RU.get(st['status'], st['status'])}{name}\n"
            f"📄 Контакты: {'загружены' if csv_ok else 'нет — пришли .csv файлом'}\n"
            f"📶 В эфире: {active}/{config.MAX_CONCURRENT_CALLS}\n"
            f"👥 На 3CX: {agents}/{config.MAX_AGENT_CHANNELS}")
    if st["progress"]:
        text += "\n⚙️ Дозвон: " + html.escape(", ".join(f"{k} {v}" for k, v in st["progress"].items()))
    if results:
        text += "\n📊 Итоги: " + html.escape(", ".join(f"{k} {v}" for k, v in results.items()))
    if st["message"]:
        text += "\n❗️ " + html.escape(st["message"])
    if note:
        text += "\n\n" + note
    rows = []
    if st["status"] in ("pending", "running"):
        rows.append([("⏹ Остановить", "a:stop")])
    elif not st["busy"] and csv_ok:
        rows.append([("🚀 Запустить", "a:run")])
    rows.append([("🔄 Обновить", "m:campaign"), ("🚫 Добавить в DNC", "e:_DNC")])
    rows.append([BACK])
    return text, kb(*rows)


def render(target):
    if target == "main":
        return screen_main()
    if target in SECTIONS:
        return screen_section(target)
    if target == "test":
        return screen_test()
    if target == "campaign":
        return screen_campaign()
    return screen_main()


# ---------------------------------------------------------------- plumbing

def owner_only(fn):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id != OWNER_ID:
            log.warning("rejected user %s", user.id if user else None)
            return
        db.load_settings()
        return await fn(update, ctx)
    return wrapper


async def show(update, ctx, text_kb, new=False):
    """Edit the panel message in place; send a fresh one when that's not possible."""
    text, markup = text_kb
    ud = ctx.user_data
    chat = update.effective_chat
    q = update.callback_query
    if q and not new:
        try:
            await q.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
            ud["panel"] = q.message.message_id
            return
        except Exception as e:
            if "not modified" in str(e):
                return
    if ud.get("panel") and not new:
        try:
            await ctx.bot.edit_message_text(text, chat_id=chat.id, message_id=ud["panel"],
                                            reply_markup=markup, parse_mode=ParseMode.HTML)
            return
        except Exception as e:
            if "not modified" in str(e):
                return
    msg = await chat.send_message(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    ud["panel"] = msg.message_id


# ---------------------------------------------------------------- checks

def _plivo_sync():
    if not (config.PLIVO_AUTH_ID and config.PLIVO_AUTH_TOKEN):
        return "❌ Сначала укажи Auth ID и Auth Token"
    try:
        acc = control.plivo_account()
        out = [f"✅ Ключи верные: <b>{html.escape(acc['name'])}</b>, баланс ${html.escape(acc['balance'])}"]
    except Exception as e:
        return f"❌ Plivo не принял ключи: {html.escape(str(e))[:200]}"
    if config.CALLER_ID:
        owned = [n for n, _ in _numbers_sync()[0]]
        out.append("✅ Caller ID есть в аккаунте" if config.CALLER_ID in owned
                   else "⚠️ Caller ID не найден среди твоих номеров Plivo")
    out.append(_webhook_sync())
    return "\n".join(out)


def _webhook_sync():
    if not config.PUBLIC_URL:
        return "⚪️ Webhook URL не задан"
    try:
        ok, code = control.webhook_ok()
        return "✅ Webhook-сервер отвечает" if ok else f"❌ Webhook /health: {code}"
    except Exception as e:
        return f"❌ Webhook-сервер недоступен: {html.escape(type(e).__name__)}"


def _numbers_sync():
    try:
        return [(n["number"], n["alias"]) for n in control.plivo_numbers()], ""
    except Exception as e:
        return [], str(e)


def _3cx_sync():
    if not config.THREECX_SIP_URI:
        return "❌ SIP URI не задан"
    host = control.sip_host()
    try:
        out = [f"✅ {html.escape(host)} найден ({control.resolve(host)})"]
    except OSError:
        return f"❌ Адрес {html.escape(host)} не находится в DNS — проверь опечатку"
    port = control.open_sip_port(host)
    out.append(f"✅ SIP-порт {port} открыт" if port else
               "ℹ️ TCP 5060/5061 закрыт — нормально, если транк по UDP. Проверь тестовым звонком.")
    out += [f"⚠️ {w}" for w in warnings("3cx")]
    return "\n".join(out)


def _check_sync():
    out = []
    missing = [FIELDS[n][0] for n in control.REQUIRED if not current(n)]
    out.append("❌ Не задано: " + ", ".join(missing) if missing else "✅ Все обязательные настройки заданы")
    out += [f"⚠️ {w}" for w in warnings()]
    out.append("\n<b>Plivo</b>\n" + _plivo_sync())
    out.append("\n<b>3CX</b>\n" + _3cx_sync())
    return "\n".join(out)


# ---------------------------------------------------------------- handlers

@owner_only
async def start(update, ctx):
    ctx.user_data.pop("await", None)
    await show(update, ctx, screen_main(), new=True)


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
        value = save(name, value)
    except ValueError as e:
        await update.effective_chat.send_message(f"{name}: invalid value ({e})")
        return
    await update.effective_chat.send_message(f"✅ {name} = {mask(name, value)}")


@owner_only
async def settings(update, ctx):
    lines = [f"{n} = {mask(n, current(n)) or '—'}" for n in config.EDITABLE]
    await update.message.reply_text("\n".join(lines))


@owner_only
async def check(update, ctx):
    await update.message.reply_text(await asyncio.to_thread(_check_sync), parse_mode=ParseMode.HTML)


async def _start_test(number):
    try:
        req = await asyncio.to_thread(dialer.test_call, number)
        return f"📞 Звоню на {html.escape(number)}… (request {req})\nНажми 1 — должна ответить 3CX."
    except Exception as e:
        return f"❌ {html.escape(str(e))}"


@owner_only
async def test(update, ctx):
    if not ctx.args:
        await show(update, ctx, screen_test(), new=True)
        return
    await update.message.reply_text(await _start_test(ctx.args[0]), parse_mode=ParseMode.HTML)


@owner_only
async def upload(update, ctx):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".csv"):
        await update.message.reply_text("Нужен файл .csv")
        return
    if runner.get()["busy"]:
        await update.message.reply_text("Кампания идёт — новый список можно загрузить после остановки.")
        return
    data = bytes(await (await doc.get_file()).download_as_bytearray())
    stats = await asyncio.to_thread(runner.save_contacts, data)
    ok = stats.get("would_call", 0)
    skipped = "\n".join(f"  {k}: {v}" for k, v in stats.items() if k != "would_call") or "  нет"
    note = (f"📄 {html.escape(doc.file_name)} проверен (без звонков)\n"
            f"Можно звонить сейчас: <b>{ok}</b>\nПропущено:\n{html.escape(skipped)}\n"
            "Пропуски по времени звонков будут повторены в следующем запуске.")
    await show(update, ctx, screen_campaign(note), new=True)


def _confirm_run(name):
    return (f"<b>Запустить «{html.escape(name)}»?</b>\n\n"
            f"до {config.MAX_CONCURRENT_CALLS} звонков одновременно, {config.CALLS_PER_SECOND}/с, "
            f"{config.MAX_AGENT_CHANNELS} линий на 3CX",
            kb([("✅ Старт", f"run:{name}"), ("✖️ Отмена", "m:campaign")]))


@owner_only
async def run_cmd(update, ctx):
    st = runner.get()
    if st["busy"]:
        await update.message.reply_text(f"Уже идёт: {st['name']}. Сначала /stop.")
        return
    if not runner.contacts_path().exists():
        await update.message.reply_text("Сначала пришли CSV с контактами.")
        return
    if not ctx.args:
        await update.message.reply_text("Usage: /run campaign_name")
        return
    try:
        name = validate.campaign_name(ctx.args[0])
    except validate.Invalid as e:
        await update.message.reply_text(f"❌ {e}")
        return
    await show(update, ctx, _confirm_run(name), new=True)


@owner_only
async def button(update, ctx):
    q = update.callback_query
    data = q.data or ""
    ud = ctx.user_data
    kind, _, arg = data.partition(":")
    if kind != "e":
        ud.pop("await", None)

    if kind == "m":
        await q.answer()
        await show(update, ctx, render(arg))
    elif kind == "e":
        await q.answer()
        ud["await"] = arg
        if arg == "_DNC":
            await show(update, ctx, ("<b>🚫 Do-not-call</b>\n\n👇 Отправь номер, на который больше "
                                     "никогда не звонить", kb([("✖️ Отмена", "m:campaign")])))
        else:
            await show(update, ctx, screen_ask(arg))
    elif kind == "a":
        await _action(update, ctx, arg)
    elif kind == "cid":
        save("CALLER_ID", arg)
        await q.answer("Caller ID сохранён")
        await show(update, ctx, screen_section("plivo", f"✅ Caller ID = {html.escape(arg)}"))
    elif kind == "t":
        await q.answer("Звоню…")
        await show(update, ctx, screen_test(await _start_test(arg)))
    elif kind == "run":
        await q.answer()
        try:
            runner.request_start(validate.campaign_name(arg))
            note = f"🚀 «{html.escape(arg)}» запускается — я напишу, когда дозвон закончится."
        except runner.Busy:
            note = "Уже идёт кампания"
        except (FileNotFoundError, validate.Invalid) as e:
            note = f"❌ {html.escape(str(e))}"
        await show(update, ctx, screen_campaign(note))
    else:  # legacy "cancel"
        await q.answer()
        await show(update, ctx, screen_main())


async def _action(update, ctx, arg):
    q = update.callback_query
    ud = ctx.user_data
    if arg == "plivo":
        await q.answer("Проверяю…")
        await show(update, ctx, screen_section("plivo", await asyncio.to_thread(_plivo_sync)))
    elif arg == "3cx":
        await q.answer("Проверяю…")
        await show(update, ctx, screen_section("3cx", await asyncio.to_thread(_3cx_sync)))
    elif arg == "check":
        await q.answer("Проверяю…")
        await show(update, ctx, (await asyncio.to_thread(_check_sync), kb([BACK])))
    elif arg == "numbers":
        if not (config.PLIVO_AUTH_ID and config.PLIVO_AUTH_TOKEN):
            await q.answer("Сначала Auth ID и Auth Token", show_alert=True)
            return
        await q.answer("Загружаю номера…")
        nums, err = await asyncio.to_thread(_numbers_sync)
        if err or not nums:
            note = f"❌ {html.escape(err)[:200]}" if err else "В аккаунте Plivo нет номеров — купи номер в Console."
            await show(update, ctx, screen_section("plivo", note))
            return
        rows = [[(f"{'✅ ' if n == config.CALLER_ID else ''}{n} {a}".strip(), f"cid:{n}")] for n, a in nums]
        rows.append([("⬅️ Plivo", "m:plivo")])
        await show(update, ctx, ("<b>📋 Номера в Plivo</b>\n\nВыбери, с какого звонить (Caller ID):",
                                 kb(*rows)))
    elif arg == "wiz3cx":
        await q.answer()
        ud["await"] = "_3CX_HOST"
        await show(update, ctx, ("<b>🧙 3CX — шаг 1 из 2</b>\n\nАдрес твоей АТС 3CX "
                                 "(как в браузере), например <code>company.3cx.us</code>\n\n👇 Отправь сообщением",
                                 kb([("✖️ Отмена", "m:3cx")])))
    elif arg == "stop":
        runner.request_stop()
        await q.answer("Останавливаю")
        await show(update, ctx, screen_campaign("⏹ Новых звонков не будет, текущие договорят."))
    elif arg == "run":
        await q.answer()
        ud["await"] = "_RUN"
        await show(update, ctx, ("<b>🚀 Новая кампания</b>\n\n👇 Отправь название (латиницей, без пробелов), "
                                 "например <code>fall-promo</code>", kb([("✖️ Отмена", "m:campaign")])))
    else:
        await q.answer()


@owner_only
async def on_text(update, ctx):
    ud = ctx.user_data
    name = ud.get("await")
    raw = update.message.text or ""
    # Keep the chat clean and never leave keys in history.
    try:
        await update.message.delete()
    except Exception:
        pass
    if not name:
        await show(update, ctx, screen_main(), new=True)
        return

    if name == "_3CX_HOST":
        try:
            ud["3cx_host"] = validate.host(raw)
        except ValueError as e:
            await show(update, ctx, (f"<b>🧙 3CX — шаг 1 из 2</b>\n\n❌ {html.escape(str(e))}\n\n👇 Попробуй ещё раз",
                                     kb([("✖️ Отмена", "m:3cx")])))
            return
        ud["await"] = "_3CX_EXT"
        await show(update, ctx, (f"<b>🧙 3CX — шаг 2 из 2</b>\n\nАТС: <code>{html.escape(ud['3cx_host'])}</code>\n\n"
                                 "Номер очереди или ринг-группы продаж, куда переводить нажавших 1 "
                                 "(3CX → Ring Groups / Queues), например <code>800</code>\n\n👇 Отправь сообщением",
                                 kb([("✖️ Отмена", "m:3cx")])))
        return
    if name == "_3CX_EXT":
        try:
            uri = save("THREECX_SIP_URI", f"sip:{validate.extension(raw)}@{ud.pop('3cx_host')}")
        except (ValueError, KeyError) as e:
            await show(update, ctx, screen_section("3cx", f"❌ {html.escape(str(e))}"))
        else:
            ud.pop("await", None)
            await show(update, ctx, screen_section("3cx", f"✅ SIP URI = <code>{html.escape(uri)}</code>\n"
                                                          "Нажми 🔌 Проверить или сделай тестовый звонок."))
        return
    if name == "_RUN":
        try:
            cname = validate.campaign_name(raw)
        except validate.Invalid:
            await show(update, ctx, ("<b>🚀 Новая кампания</b>\n\n❌ Только буквы, цифры, - _ .\n\n👇 Ещё раз",
                                     kb([("✖️ Отмена", "m:campaign")])))
            return
        ud.pop("await", None)
        await show(update, ctx, _confirm_run(cname))
        return
    if name == "_DNC":
        phone = normalize_phone(raw)
        ud.pop("await", None)
        with db.connect() as conn:
            db.add_dnc(conn, phone, "telegram")
        await show(update, ctx, screen_campaign(f"🚫 {html.escape(phone)} добавлен в DNC"))
        return

    try:
        value = save(name, raw)
    except ValueError as e:
        await show(update, ctx, screen_ask(name, str(e)))
        return
    ud.pop("await", None)
    await show(update, ctx, screen_section(FIELD_SECTION[name],
                                           f"✅ {FIELDS[name][0]} = <code>{html.escape(mask(name, value))}</code>"))


@owner_only
async def stop(update, ctx):
    if not runner.request_stop():
        await update.message.reply_text("Ничего не запущено")
        return
    await update.message.reply_text("⏹ Новых звонков не будет, текущие договорят.")


@owner_only
async def status(update, ctx):
    await show(update, ctx, screen_campaign(), new=True)


@owner_only
async def dnc(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Usage: /dnc +1XXXXXXXXXX")
        return
    phone = normalize_phone(ctx.args[0])
    with db.connect() as conn:
        db.add_dnc(conn, phone, "telegram")
    await update.message.reply_text(f"🚫 {phone} добавлен в DNC")


STATUS_DONE = {"done": "🏁 «{}» — дозвон завершён", "stopped": "⏹ «{}» остановлена",
               "failed": "❌ «{}» — ошибка"}


async def _notify_finished(app):
    """The runner is another process: poll its state and report finished campaigns."""
    while True:
        await asyncio.sleep(5)
        try:
            st = await asyncio.to_thread(runner.get)
            if not st["notified"] and st["status"] in STATUS_DONE:
                text = STATUS_DONE[st["status"]].format(st["name"])
                if st["progress"]:
                    text += "\n" + ", ".join(f"{k} {v}" for k, v in st["progress"].items())
                if st["message"]:
                    text += "\n" + st["message"]
                await app.bot.send_message(OWNER_ID, text)
                await asyncio.to_thread(runner.mark_notified)
        except Exception:
            log.exception("notify loop")


async def _post_init(app):
    # Plain asyncio task (keep a reference so it isn't garbage-collected).
    app.bot_data["notify_task"] = asyncio.get_running_loop().create_task(_notify_finished(app))
    await app.bot.set_my_commands([
        BotCommand("start", "Главное меню"),
        BotCommand("status", "Кампания и статистика"),
        BotCommand("test", "Тестовый звонок"),
        BotCommand("check", "Проверить настройки"),
        BotCommand("stop", "Остановить кампанию"),
    ])


def build(token):
    app = Application.builder().token(token).post_init(_post_init).build()
    for name, fn in [("start", start), ("help", start), ("menu", start), ("set", set_cmd),
                     ("settings", settings), ("check", check), ("test", test), ("run", run_cmd),
                     ("stop", stop), ("status", status), ("dnc", dnc)]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.Document.ALL, upload))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its log lines include the bot token
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not OWNER_ID:
        # Idle instead of exiting so `restart: unless-stopped` doesn't crash-loop a panel-only setup.
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID not set: Telegram bot disabled")
        threading.Event().wait()
    build(token).run_polling()


if __name__ == "__main__":
    main()
