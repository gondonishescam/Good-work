import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, Response, abort, request
from plivo.utils import validate_v3_signature

from . import config, db, ivr

app = Flask(__name__)
app.config["TESTING"] = os.getenv("PRESS1_TESTING") == "1"  # load tests only
log = logging.getLogger("press1")

# Outbound Plivo API calls (AMD -> voicemail) must not run inside the webhook:
# under load a slow API response ties up a worker and Plivo's next webhook times out.
_background = ThreadPoolExecutor(max_workers=8, thread_name_prefix="plivo-api")


def xml(body):
    return Response(body, mimetype="application/xml")


_settings_loaded_at = 0.0


@app.before_request
def refresh_settings():
    global _settings_loaded_at
    if time.monotonic() - _settings_loaded_at > 5:
        try:
            db.load_settings()
        except Exception:
            log.exception("could not load settings")
        _settings_loaded_at = time.monotonic()


@app.before_request
def verify_plivo_signature():
    if request.path == "/health" or app.config.get("TESTING"):
        return
    sig = request.headers.get("X-Plivo-Signature-V3", "")
    nonce = request.headers.get("X-Plivo-Signature-V3-Nonce", "")
    params = request.form.to_dict() if request.method == "POST" else {}
    url = config.PUBLIC_URL + request.full_path.rstrip("?")
    try:
        valid = validate_v3_signature(request.method, url, nonce, config.PLIVO_AUTH_TOKEN, sig, params)
    except Exception:
        valid = False
    if not valid:
        abort(403)


@app.get("/health")
def health():
    return "ok"


@app.post("/ivr/answer")
def answer():
    call_uuid = request.form.get("CallUUID", "")
    first_name = request.args.get("first_name", "")
    try:
        with db.connect() as conn:
            db.bind_call_uuid(conn, request.args.get("cid") or request.form.get("RequestUUID", ""), call_uuid,
                              request.form.get("To", ""))
            db.update_call(conn, call_uuid, status="answered")
    except Exception:
        # Bookkeeping must never cost the caller the IVR.
        log.exception("answer: db error for %s", call_uuid)
    return xml(ivr.greeting(first_name))


def _claim_agent_slot(conn, call_uuid):
    """Atomically reserve one of MAX_AGENT_CHANNELS 3CX lines."""
    conn.execute("BEGIN IMMEDIATE")
    if db.transferred_calls(conn) >= config.MAX_AGENT_CHANNELS:
        db.update_call(conn, call_uuid, status="agents_full")
        return False
    db.update_call(conn, call_uuid, status="transferred")
    return True


@app.post("/ivr/input")
def handle_input():
    call_uuid = request.form.get("CallUUID", "")
    digit = request.form.get("Digits", "")
    if digit == "9":
        # Opt-out must succeed even under load: let a DB error surface as 500 so
        # Plivo retries instead of silently losing the request.
        with db.connect() as conn:
            phone = db.phone_for_call(conn, call_uuid) or request.form.get("To", "")
            db.add_dnc(conn, phone, source="ivr_press_9")
            db.update_call(conn, call_uuid, digit=digit, status="opted_out")
        return xml(ivr.opted_out())
    if digit == "1":
        try:
            with db.connect() as conn:
                ok = _claim_agent_slot(conn, call_uuid)
                db.update_call(conn, call_uuid, digit=digit)
        except Exception:
            log.exception("input: db error for %s", call_uuid)
            ok = True  # prefer connecting a customer who pressed 1 over dropping them
        return xml(ivr.connect_agent() if ok else ivr.agents_unavailable())
    return xml(ivr.invalid_choice())


@app.post("/ivr/dial-status")
def dial_status():
    status = request.form.get("DialStatus", "")
    call_uuid = request.form.get("CallUUID", "")
    if status in ("completed", "answer"):
        return xml("<Response/>")
    with db.connect() as conn:
        db.update_call(conn, call_uuid, status=f"agent_{status or 'failed'}")
    return xml(ivr.agents_unavailable())


def _to_voicemail(call_uuid):
    from .dialer import transfer_to_voicemail
    try:
        transfer_to_voicemail(call_uuid)
    except Exception:
        log.exception("voicemail transfer failed for %s", call_uuid)


@app.post("/ivr/machine")
def machine_detected():
    """Async AMD callback: replace the live IVR with a compliant voicemail."""
    call_uuid = request.form.get("CallUUID", "")
    if request.form.get("Machine", "").lower() == "true":
        with db.connect() as conn:
            db.bind_call_uuid(conn, request.args.get("cid", ""), call_uuid, request.form.get("To", ""))
            db.update_call(conn, call_uuid, status="voicemail", amd="machine")
        _background.submit(_to_voicemail, call_uuid)
    return "", 204


@app.post("/ivr/voicemail")
def voicemail():
    return xml(ivr.voicemail())


@app.post("/ivr/hangup")
def hangup():
    call_uuid = request.form.get("CallUUID", "")
    with db.connect() as conn:
        db.bind_call_uuid(conn, request.args.get("cid") or request.form.get("RequestUUID", ""), call_uuid,
                          request.form.get("To", ""))
        db.update_call(conn, call_uuid, status=f"ended:{request.form.get('HangupCause', '')}")
    return "", 204
