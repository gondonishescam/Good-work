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
    upd, ctx = make_update(42, ["plivo_auth_token", "supersecret99"])
    asyncio.run(bot.set_cmd(upd, ctx))
    upd.message.delete.assert_awaited()
    sent = upd.effective_chat.send_message.call_args[0][0]
    assert "supersecret99" not in sent
    assert config.PLIVO_AUTH_TOKEN == "supersecret99"


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
