import io

import pytest

from press1 import config, db, panel, runner

PW = "correct-horse-battery"
H = {"X-Panel": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setattr(panel, "PANEL_PASSWORD", PW)
    monkeypatch.setattr(runner, "UPLOAD_DIR", tmp_path / "up")
    monkeypatch.setattr(config, "PLIVO_AUTH_TOKEN", "")
    from press1.app import app
    app.config["SESSION_COOKIE_SECURE"] = False
    return app.test_client()


def login(c, pw=PW):
    return c.post("/api/login", json={"password": pw}, headers=H)


def test_index_served_without_auth(client):
    r = client.get("/")
    assert r.status_code == 200 and b"Press 1" in r.data
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_api_requires_login(client):
    assert client.get("/api/state").status_code == 401
    assert client.post("/api/settings", json={}, headers=H).status_code == 401


def test_disabled_without_password(client, monkeypatch):
    monkeypatch.setattr(panel, "PANEL_PASSWORD", "short")
    assert login(client, "short").status_code == 503
    assert client.get("/api/session").json == {"enabled": False, "auth": False}


def test_login_throttled(client):
    for _ in range(panel.MAX_FAILS_PER_IP):
        assert login(client, "nope").status_code == 401
    assert login(client).status_code == 429  # even the right password, until the window passes


def test_post_needs_custom_header(client):
    login(client)
    r = client.post("/api/settings", json={"values": {"COMPANY_NAME": "X"}})
    assert r.status_code == 400


def test_settings_validated_and_masked(client):
    assert login(client).status_code == 200
    r = client.post("/api/settings", headers=H, json={"values": {
        "COMPANY_NAME": "Acme", "MAX_AGENT_CHANNELS": "lots", "PLIVO_AUTH_TOKEN": "tok_" + "x" * 30}})
    assert r.status_code == 422
    assert r.json["errors"] == {"MAX_AGENT_CHANNELS": "must be a whole number"}
    assert r.json["saved"]["COMPANY_NAME"] == "Acme"
    st = client.get("/api/state").json
    assert st["settings"]["PLIVO_AUTH_TOKEN"]["value"] == "tok…xx"
    assert "x" * 10 not in str(st)
    # Blank secret keeps the stored one.
    client.post("/api/settings", headers=H, json={"values": {"PLIVO_AUTH_TOKEN": ""}})
    assert config.PLIVO_AUTH_TOKEN.startswith("tok_")


def test_wizard_builds_sip(client):
    login(client)
    r = client.post("/api/3cx/wizard", headers=H, json={"host": "https://co.3cx.us/", "extension": "800"})
    assert r.json["value"] == "sip:800@co.3cx.us" == config.THREECX_SIP_URI
    r = client.post("/api/3cx/wizard", headers=H, json={"host": "nope", "extension": ""})
    assert set(r.json["errors"]) == {"host", "extension"}


def test_campaign_flow(client):
    login(client)
    assert client.post("/api/campaign/start", headers=H, json={"name": "a"}).status_code == 422
    csv = b"phone,first_name,timezone,state,consent_date,consent_source\n+12125550100,A,UTC,NY,2026-01-01,f\n"
    r = client.post("/api/contacts", headers=H, data={"file": (io.BytesIO(csv), "c.csv")},
                    content_type="multipart/form-data")
    assert r.status_code == 200 and sum(r.json["stats"].values()) == 1
    assert client.post("/api/campaign/start", headers=H, json={"name": "bad name"}).status_code == 422
    assert client.post("/api/campaign/start", headers=H, json={"name": "fall"}).status_code == 200
    assert client.post("/api/campaign/start", headers=H, json={"name": "again"}).status_code == 409
    assert client.get("/api/state").json["campaign"]["status"] == "pending"
    assert client.post("/api/campaign/stop", headers=H, json={}).json["stopped"]


def test_dnc(client):
    login(client)
    assert client.post("/api/dnc", headers=H, json={"phone": "12"}).status_code == 422
    assert client.post("/api/dnc", headers=H, json={"phone": "(212) 555-0100"}).json["phone"] == "+12125550100"
    with db.connect() as conn:
        assert db.is_dnc(conn, "+12125550100")


def test_webhooks_still_signed(client, monkeypatch):
    from press1.app import app
    monkeypatch.setitem(app.config, "TESTING", False)
    assert client.post("/ivr/answer").status_code == 403
    assert client.get("/health").status_code == 200
