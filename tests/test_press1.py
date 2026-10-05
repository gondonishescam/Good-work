from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from press1 import config, db
from press1.compliance import Contact, check_contact, normalize_phone


def contact(**kw):
    base = dict(phone="+12125550123", first_name="John", timezone="America/New_York",
                state="NY", consent_date="2026-01-01", consent_source="form#1")
    base.update(kw)
    return Contact(**base)


NOON_NY = datetime(2026, 10, 5, 16, 0, tzinfo=ZoneInfo("UTC"))
NINE_PM_NY = datetime(2026, 10, 6, 1, 0, tzinfo=ZoneInfo("UTC"))
SEVEN_PM_NY = datetime(2026, 10, 5, 23, 30, tzinfo=ZoneInfo("UTC"))
no_dnc = lambda p: False


def test_normalize():
    assert normalize_phone("(212) 555-0123") == "+12125550123"


def test_allowed():
    assert check_contact(contact(), no_dnc, NOON_NY) is None


@pytest.mark.parametrize("kw,reason", [
    (dict(consent_source=""), "no_written_consent"),
    (dict(consent_date="bad"), "invalid_consent_date"),
    (dict(phone="+1212"), "invalid_phone"),
    (dict(timezone="Mars/Base"), "unknown_timezone"),
])
def test_rejections(kw, reason):
    assert check_contact(contact(**kw), no_dnc, NOON_NY) == reason


def test_dnc():
    assert check_contact(contact(), lambda p: True, NOON_NY) == "dnc"


def test_hours():
    assert check_contact(contact(), no_dnc, NINE_PM_NY) == "outside_calling_hours"
    assert check_contact(contact(state="FL"), no_dnc, SEVEN_PM_NY) is None
    assert check_contact(contact(state="FL"), no_dnc, NINE_PM_NY) == "outside_calling_hours"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "PUBLIC_URL", "https://x.test")
    monkeypatch.setattr(config, "THREECX_SIP_URI", "sip:800@pbx.test")
    from press1.app import app
    app.config["TESTING"] = True
    with db.connect() as conn:
        db.log_call(conn, "req-1", "+12125550123", "c", "queued")
    return app.test_client()


def test_flow_press_1(client):
    r = client.post("/ivr/answer?first_name=John", data={"CallUUID": "call-1", "RequestUUID": "req-1"})
    assert b"Press 9 to stop" in r.data and b"GetInput" in r.data
    r = client.post("/ivr/input", data={"CallUUID": "call-1", "Digits": "1"})
    assert b"sip:800@pbx.test" in r.data


def test_flow_press_9_adds_dnc(client):
    client.post("/ivr/answer", data={"CallUUID": "call-1", "RequestUUID": "req-1"})
    client.post("/ivr/input", data={"CallUUID": "call-1", "Digits": "9"})
    with db.connect() as conn:
        assert db.is_dnc(conn, "+12125550123")


def test_signature_required(tmp_path, monkeypatch):
    from press1.app import app
    app.config["TESTING"] = False
    try:
        assert app.test_client().post("/ivr/answer").status_code == 403
    finally:
        app.config["TESTING"] = True
