"""Web control panel: the same controls as the Telegram bot, in the browser.

Login is a single password (PANEL_PASSWORD, 10+ chars). Every state-changing call is a
JSON POST that must carry the X-Panel header, which a cross-site form cannot send.
"""
import hashlib
import hmac
import os
import time
from datetime import timedelta
from functools import wraps

from flask import Blueprint, jsonify, request, send_from_directory, session

from . import config, control, db, dialer, runner, validate
from .compliance import normalize_phone

bp = Blueprint("panel", __name__)
STATIC = os.path.join(os.path.dirname(__file__), "static", "panel")

PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "")
MAX_FAILS_PER_IP = 5
MAX_FAILS_TOTAL = 50
FAIL_WINDOW = 15 * 60

LABELS = {
    "PLIVO_AUTH_ID": "Auth ID", "PLIVO_AUTH_TOKEN": "Auth Token", "CALLER_ID": "Caller ID",
    "PUBLIC_URL": "Webhook URL", "THREECX_SIP_URI": "SIP URI", "MAX_AGENT_CHANNELS": "3CX lines",
    "MAX_CONCURRENT_CALLS": "Simultaneous calls", "CALLS_PER_SECOND": "Calls per second",
    "STALE_CALL_MINUTES": "Stale call timeout", "COMPANY_NAME": "Company name",
    "OPT_OUT_PHONE": "Opt-out number", "TEST_NUMBERS": "Test numbers",
}


def enabled():
    return len(PANEL_PASSWORD) >= 10


def secret_key():
    # Derived from the password: changing it logs every session out.
    return hashlib.sha256(b"press1-panel:" + PANEL_PASSWORD.encode()).digest()


def init_app(app):
    app.secret_key = os.getenv("PANEL_SECRET") or secret_key()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=os.getenv("PANEL_INSECURE_COOKIE") != "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    )
    app.register_blueprint(bp)


def err(msg, code=400, **extra):
    return jsonify(ok=False, error=msg, **extra), code


def api(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not enabled():
            return err("Panel is disabled: set PANEL_PASSWORD (10+ characters) in .env", 503)
        if request.method == "POST" and request.headers.get("X-Panel") != "1":
            return err("bad request", 400)
        if not session.get("auth"):
            return err("login required", 401)
        db.load_settings()
        return fn(*a, **kw)
    return wrapper


def body():
    return request.get_json(silent=True) or {}


# ---------------------------------------------------------------- pages

@bp.get("/")
def index():
    resp = send_from_directory(STATIC, "index.html")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.get("/panel/<path:name>")
def asset(name):
    return send_from_directory(STATIC, name, max_age=300)


@bp.after_app_request
def security_headers(resp):
    if not request.path.startswith("/ivr/"):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    return resp


# ---------------------------------------------------------------- auth

def _fails(conn, ip, now):
    conn.execute("DELETE FROM login_failures WHERE at < ?", (now - FAIL_WINDOW,))
    per_ip = conn.execute("SELECT COUNT(*) FROM login_failures WHERE ip = ?", (ip,)).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM login_failures").fetchone()[0]
    return per_ip, total


@bp.post("/api/login")
def login():
    if not enabled():
        return err("Panel is disabled: set PANEL_PASSWORD (10+ characters) in .env", 503)
    if request.headers.get("X-Panel") != "1":
        return err("bad request", 400)
    ip, now = request.remote_addr or "?", time.time()
    with db.connect() as conn:
        per_ip, total = _fails(conn, ip, now)
        if per_ip >= MAX_FAILS_PER_IP or total >= MAX_FAILS_TOTAL:
            return err("Too many attempts. Try again in 15 minutes.", 429)
        given = str(body().get("password", ""))
        if not hmac.compare_digest(given.encode(), PANEL_PASSWORD.encode()):
            conn.execute("INSERT INTO login_failures (ip, at) VALUES (?, ?)", (ip, now))
            left = MAX_FAILS_PER_IP - per_ip - 1
            return err("Wrong password" + (f" · {left} attempts left" if left < 3 else ""), 401)
        conn.execute("DELETE FROM login_failures WHERE ip = ?", (ip,))
    session.clear()
    session.permanent = True
    session["auth"] = True
    return jsonify(ok=True)


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/api/session")
def session_info():
    return jsonify(enabled=enabled(), auth=bool(session.get("auth")) and enabled())


# ---------------------------------------------------------------- state

def _settings_view():
    out = {}
    for name in validate.SETTINGS:
        v = control.current(name)
        out[name] = {"label": LABELS[name], "set": bool(v), "secret": name in config.SECRET,
                     "value": control.mask(name, v) if name in config.SECRET else v}
    return out


@bp.get("/api/state")
@api
def state():
    st = runner.get()
    with db.connect() as conn:
        live = {"active": db.active_calls(conn), "max": config.MAX_CONCURRENT_CALLS,
                "agents": db.transferred_calls(conn), "max_agents": config.MAX_AGENT_CHANNELS}
        results = db.campaign_stats(conn, st["name"]) if st["name"] else {}
        dnc_count = conn.execute("SELECT COUNT(*) FROM dnc").fetchone()[0]
    return jsonify(
        ok=True,
        settings=_settings_view(),
        ready={"plivo": control.ready("plivo"), "3cx": control.ready("3cx")},
        missing=[LABELS[n] for n in control.REQUIRED if not control.current(n)],
        warnings={s: control.warnings(s, "en") for s in ("plivo", "3cx", "limits")},
        campaign={**st, "contacts": runner.contacts_path().exists(), "results": results},
        live=live,
        test_numbers=[n for n in config.TEST_NUMBERS.split(",") if n.strip()],
        dnc_count=dnc_count,
    )


@bp.post("/api/settings")
@api
def save_settings():
    values = body().get("values") or {}
    errors, saved = {}, {}
    for name, raw in values.items():
        if name not in validate.SETTINGS:
            errors[name] = "unknown setting"
            continue
        if name in config.SECRET and not str(raw).strip():
            continue  # blank secret field = keep the stored one
        try:
            v = control.save(name, str(raw))
            saved[name] = control.mask(name, v)
        except validate.Invalid as e:
            errors[name] = e.en
    return jsonify(ok=not errors, errors=errors, saved=saved), (200 if not errors else 422)


@bp.post("/api/3cx/wizard")
@api
def wizard_3cx():
    b = body()
    errors = {}
    try:
        host = validate.host(b.get("host"))
    except validate.Invalid as e:
        errors["host"] = e.en
    try:
        ext = validate.extension(b.get("extension"))
    except validate.Invalid as e:
        errors["extension"] = e.en
    if errors:
        return jsonify(ok=False, errors=errors), 422
    uri = control.save("THREECX_SIP_URI", f"sip:{ext}@{host}")
    return jsonify(ok=True, value=uri)


# ---------------------------------------------------------------- checks

def item(level, text):
    return {"level": level, "text": text}


def check_plivo():
    if not (config.PLIVO_AUTH_ID and config.PLIVO_AUTH_TOKEN):
        return [item("error", "Set Auth ID and Auth Token first")]
    try:
        acc = control.plivo_account()
        out = [item("ok", f"Keys accepted · {acc['name']} · balance ${acc['balance']}")]
    except Exception as e:
        return [item("error", f"Plivo rejected the keys: {str(e)[:200]}")]
    if config.CALLER_ID:
        try:
            owned = [n["number"] for n in control.plivo_numbers()]
            out.append(item("ok", "Caller ID belongs to this account") if config.CALLER_ID in owned
                       else item("warn", "Caller ID is not one of your Plivo numbers"))
        except Exception as e:
            out.append(item("warn", f"Could not list numbers: {str(e)[:120]}"))
    else:
        out.append(item("warn", "Caller ID is not set"))
    out.append(check_webhook())
    return out


def check_webhook():
    if not config.PUBLIC_URL:
        return item("warn", "Webhook URL is not set")
    try:
        ok, code = control.webhook_ok()
        return item("ok", "Webhook server is reachable") if ok else item("error", f"Webhook /health returned {code}")
    except Exception as e:
        return item("error", f"Webhook server unreachable ({type(e).__name__})")


def check_3cx():
    if not config.THREECX_SIP_URI:
        return [item("error", "SIP URI is not set")]
    host = control.sip_host()
    try:
        out = [item("ok", f"{host} resolves to {control.resolve(host)}")]
    except OSError:
        return [item("error", f"{host} does not resolve — check for a typo")]
    port = control.open_sip_port(host)
    out.append(item("ok", f"SIP port {port} is open") if port else
               item("info", "TCP 5060/5061 closed — fine for a UDP trunk. Confirm with a test call."))
    out += [item("warn", w) for w in control.warnings("3cx", "en")]
    return out


@bp.post("/api/check/<what>")
@api
def run_check(what):
    if what == "plivo":
        items = check_plivo()
    elif what == "3cx":
        items = check_3cx()
    elif what == "all":
        missing = [LABELS[n] for n in control.REQUIRED if not control.current(n)]
        items = [item("error", "Not set: " + ", ".join(missing)) if missing
                 else item("ok", "All required settings are set")]
        items += [item("warn", w) for w in control.warnings(None, "en")]
        items += [dict(i, group="Plivo") for i in check_plivo()]
        items += [dict(i, group="3CX") for i in check_3cx()]
    else:
        return err("unknown check", 404)
    return jsonify(ok=True, items=items)


@bp.get("/api/plivo/numbers")
@api
def numbers():
    if not (config.PLIVO_AUTH_ID and config.PLIVO_AUTH_TOKEN):
        return err("Set Auth ID and Auth Token first", 422)
    try:
        return jsonify(ok=True, numbers=control.plivo_numbers(), current=config.CALLER_ID)
    except Exception as e:
        return err(f"Plivo: {str(e)[:200]}", 502)


# ---------------------------------------------------------------- calls

@bp.post("/api/test")
@api
def test_call():
    try:
        req = dialer.test_call(str(body().get("phone", "")))
    except ValueError as e:
        return err(str(e), 422)
    except Exception as e:
        return err(f"Call failed: {str(e)[:200]}", 502)
    return jsonify(ok=True, request=str(req))


@bp.post("/api/contacts")
@api
def upload_contacts():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        return err("Choose a .csv file", 422)
    try:
        stats = runner.save_contacts(f.read())
    except runner.Busy:
        return err("A campaign is running — upload after it stops", 409)
    except Exception as e:
        return err(f"Could not read the CSV: {str(e)[:200]}", 422)
    return jsonify(ok=True, filename=f.filename, stats=stats)


@bp.post("/api/campaign/start")
@api
def start_campaign():
    try:
        runner.request_start(validate.campaign_name(body().get("name")))
    except validate.Invalid as e:
        return err(e.en, 422)
    except FileNotFoundError:
        return err("Upload a contacts CSV first", 422)
    except runner.Busy as e:
        return err(f"Campaign '{e}' is already running", 409)
    return jsonify(ok=True)


@bp.post("/api/campaign/stop")
@api
def stop_campaign():
    return jsonify(ok=True, stopped=runner.request_stop())


@bp.post("/api/dnc")
@api
def add_dnc():
    try:
        phone = validate.phone(str(body().get("phone", "")))
    except validate.Invalid as e:
        return err(e.en, 422)
    with db.connect() as conn:
        db.add_dnc(conn, normalize_phone(phone), "panel")
    return jsonify(ok=True, phone=phone)
