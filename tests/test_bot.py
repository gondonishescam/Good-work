import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from press1 import bot, config, db


def make_update(user_id, args=()):
    msg = SimpleNamespace(reply_text=AsyncMock(), delete=AsyncMock())
    chat = SimpleNamespace(send_message=AsyncMock())
    upd = SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=msg, effective_chat=chat)
    return upd, SimpleNamespace(args=list(args))


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "b.db"))
    monkeypatch.setattr(bot, "OWNER_ID", 42)
    monkeypatch.setattr(config, "PLIVO_AUTH_TOKEN", "")


def test_stranger_ignored():
    upd, ctx = make_update(7, ["PLIVO_AUTH_TOKEN", "x"])
    asyncio.run(bot.set_cmd(upd, ctx))
    upd.message.delete.assert_not_called()
    with db.connect() as conn:
        assert db.get_settings(conn) == {}


def test_set_secret_deleted_and_masked():
    upd, ctx = make_update(42, ["plivo_auth_token", "supersecret99supersecret"])
    asyncio.run(bot.set_cmd(upd, ctx))
    upd.message.delete.assert_awaited()
    sent = upd.effective_chat.send_message.call_args[0][0]
    assert "supersecret99supersecret" not in sent
    assert config.PLIVO_AUTH_TOKEN == "supersecret99supersecret"


def test_set_rejects_bad_number():
    upd, ctx = make_update(42, ["MAX_AGENT_CHANNELS", "lots"])
    asyncio.run(bot.set_cmd(upd, ctx))
    assert "invalid" in upd.effective_chat.send_message.call_args[0][0]


def test_dialer_stop(tmp_path, monkeypatch):
    from press1 import dialer
    monkeypatch.setattr("press1.compliance.DEFAULT_HOURS", (0, 24))
    csv = tmp_path / "c.csv"
    csv.write_text("phone,first_name,timezone,state,consent_date,consent_source\n" +
                   "\n".join(f"+1212555{1000+i},A,UTC,NY,2026-01-01,f" for i in range(5)))
    stop = threading.Event()
    calls = []

    def fake(contact, cid):
        calls.append(cid)
        stop.set()
        return "r"
    monkeypatch.setattr(dialer, "place_call", fake)
    stats = dialer.run(str(csv), "t", stop=stop, sleep=lambda _: None)
    assert len(calls) == 1 and stats["stopped_before_call"] == 4


def test_test_call_only_own_numbers(monkeypatch):
    from press1 import dialer
    monkeypatch.setattr(config, "TEST_NUMBERS", "+12125550100")
    monkeypatch.setattr(dialer, "place_call", lambda c, cid: "r")
    with pytest.raises(ValueError):
        dialer.test_call("+13055550000")
    assert dialer.test_call("(212) 555-0100") == "r"


def make_text(user_id, text, await_=None):
    upd, ctx = make_update(user_id)
    upd.message.text = text
    sent = SimpleNamespace(message_id=1)
    upd.effective_chat.id = 1
    upd.effective_chat.send_message = AsyncMock(return_value=sent)
    upd.callback_query = None
    ctx.user_data = {"await": await_} if await_ else {}
    ctx.bot = SimpleNamespace(edit_message_text=AsyncMock())
    return upd, ctx


def test_validators_normalize():
    from press1 import validate as v
    assert v.sip("800@co.3cx.us") == "sip:800@co.3cx.us"
    assert v.url("dialer.example.com/") == "https://dialer.example.com"
    assert v.phones("(212) 555-0100, 3055550000") == "+12125550100,+13055550000"
    assert v.host("https://co.3cx.us/#/login") == "co.3cx.us"
    for fn, bad in [(v.sip, "800"), (v.auth_id, "short"), (v.integer(1, 5), "9"), (v.phone, "12"),
                    (v.campaign_name, "a b"), (v.url, "")]:
        with pytest.raises(v.Invalid):
            fn(bad)


def test_menu_edit_saves_and_deletes_message():
    upd, ctx = make_text(42, "maaaaaaaaaaaaaaaaaa1", "PLIVO_AUTH_ID")
    asyncio.run(bot.on_text(upd, ctx))
    upd.message.delete.assert_awaited()
    assert config.PLIVO_AUTH_ID == "MAAAAAAAAAAAAAAAAAA1"
    assert "await" not in ctx.user_data


def test_menu_edit_rejects_and_keeps_waiting():
    upd, ctx = make_text(42, "lots", "MAX_AGENT_CHANNELS")
    asyncio.run(bot.on_text(upd, ctx))
    assert ctx.user_data["await"] == "MAX_AGENT_CHANNELS"
    with db.connect() as conn:
        assert "MAX_AGENT_CHANNELS" not in db.get_settings(conn)


def test_3cx_wizard_builds_uri():
    upd, ctx = make_text(42, "https://co.3cx.us/", "_3CX_HOST")
    asyncio.run(bot.on_text(upd, ctx))
    upd.message.text = "800"
    asyncio.run(bot.on_text(upd, ctx))
    assert config.THREECX_SIP_URI == "sip:800@co.3cx.us"


def test_stranger_text_ignored():
    upd, ctx = make_text(7, "x", "PLIVO_AUTH_ID")
    asyncio.run(bot.on_text(upd, ctx))
    upd.message.delete.assert_not_called()


def test_runner_single_campaign(tmp_path, monkeypatch):
    from press1 import runner
    monkeypatch.setattr(runner, "UPLOAD_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        runner.request_start("a")
    runner.contacts_path().write_text("phone\n")
    runner.request_start("a")
    with pytest.raises(runner.Busy):
        runner.request_start("b")
    with pytest.raises(runner.Busy):
        runner.save_contacts(b"phone\n")
    assert runner.request_stop() and runner.get()["status"] == "stopped"


def test_runner_runs_and_stops(tmp_path, monkeypatch):
    from press1 import dialer, runner
    monkeypatch.setattr(runner, "UPLOAD_DIR", tmp_path)
    runner.contacts_path().write_text("phone\n")
    monkeypatch.setattr(dialer, "run", lambda *a, **k: {"called": 3})
    runner.request_start("c")
    assert runner.step() and not runner.step()
    st = runner.get()
    assert st["status"] == "done" and st["progress"] == {"called": 3} and not st["notified"]


def test_runner_recovers_after_crash(tmp_path):
    from press1 import runner
    with db.connect() as conn:
        runner._set(conn, name="x", status="running")
    runner.recover()
    assert runner.get()["status"] == "failed"
