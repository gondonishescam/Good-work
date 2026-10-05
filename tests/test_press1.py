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


def test_agent_slots_capped(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_AGENT_CHANNELS", 2)
    results = []
    for i in range(4):
        client.post("/ivr/answer", data={"CallUUID": f"c{i}", "To": "+12125550100"})
        r = client.post("/ivr/input", data={"CallUUID": f"c{i}", "Digits": "1"})
        results.append(b"sip:800@pbx.test" in r.data)
    assert results == [True, True, False, False]
    client.post("/ivr/hangup", data={"CallUUID": "c0"})  # agent line freed
    client.post("/ivr/answer", data={"CallUUID": "c9", "To": "+12125550100"})
    assert b"sip:800" in client.post("/ivr/input", data={"CallUUID": "c9", "Digits": "1"}).data


def test_cid_binding_no_duplicates(client):
    with db.connect() as conn:
        db.log_call(conn, "cid-1", "+12125550111", "c", "queued")
    client.post("/ivr/answer?cid=cid-1", data={"CallUUID": "call-x", "To": "+12125550111"})
    client.post("/ivr/hangup?cid=cid-1", data={"CallUUID": "call-x", "HangupCause": "NORMAL"})
    with db.connect() as conn:
        rows = conn.execute("SELECT call_uuid, status FROM calls WHERE phone = '+12125550111'").fetchall()
    assert [tuple(r) for r in rows] == [("call-x", "ended:NORMAL")]


def test_dialer_respects_concurrency(tmp_path, monkeypatch):
    from press1 import dialer
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "d.db"))
    monkeypatch.setattr(config, "MAX_CONCURRENT_CALLS", 3)
    monkeypatch.setattr(config, "CALLS_PER_SECOND", 1000)
    csv_path = tmp_path / "c.csv"
    lines = ["phone,first_name,timezone,state,consent_date,consent_source"]
    lines += [f"+1212555{1000 + i},A,UTC,NY,2026-01-01,f#{i}" for i in range(10)]
    csv_path.write_text("\n".join(lines))
    monkeypatch.setattr("press1.compliance.DEFAULT_HOURS", (0, 24))
    peak = []

    def fake_place(contact, cid):
        with db.connect() as conn:
            peak.append(db.active_calls(conn))
        return "r"

    def fake_sleep(_):
        # simulate one call finishing whenever the dialer waits for a slot
        with db.connect() as conn:
            conn.execute("UPDATE calls SET status='ended' WHERE rowid = "
                         "(SELECT MIN(rowid) FROM calls WHERE status='queued')")

    monkeypatch.setattr(dialer, "place_call", fake_place)
    stats = dialer.run(str(csv_path), "t", sleep=fake_sleep)
    assert stats == {"called": 10}
    assert max(peak) <= 3
