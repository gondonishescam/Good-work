from flask import Flask, Response, abort, request
from plivo.utils import validate_v3_signature

from . import config, db, ivr

app = Flask(__name__)


def xml(body):
    return Response(body, mimetype="application/xml")


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
    with db.connect() as conn:
        db.bind_call_uuid(conn, request.form.get("RequestUUID", ""), call_uuid)
        db.update_call(conn, call_uuid, status="answered")
    return xml(ivr.greeting(first_name))


@app.post("/ivr/input")
def handle_input():
    call_uuid = request.form.get("CallUUID", "")
    digit = request.form.get("Digits", "")
    with db.connect() as conn:
        db.update_call(conn, call_uuid, digit=digit)
        if digit == "1":
            db.update_call(conn, call_uuid, status="transferred")
            return xml(ivr.connect_agent())
        if digit == "9":
            phone = db.phone_for_call(conn, call_uuid) or request.form.get("To", "")
            db.add_dnc(conn, phone, source="ivr_press_9")
            db.update_call(conn, call_uuid, status="opted_out")
            return xml(ivr.opted_out())
    return xml(ivr.invalid_choice())


@app.post("/ivr/dial-status")
def dial_status():
    status = request.form.get("DialStatus", "")
    if status in ("completed", "answer"):
        return xml("<Response/>")
    with db.connect() as conn:
        db.update_call(conn, request.form.get("CallUUID", ""), status=f"agent_{status or 'failed'}")
    return xml(ivr.agents_unavailable())


@app.post("/ivr/machine")
def machine_detected():
    """Async AMD callback: replace the live IVR with a compliant voicemail."""
    call_uuid = request.form.get("CallUUID", "")
    if request.form.get("Machine", "").lower() == "true":
        with db.connect() as conn:
            db.update_call(conn, call_uuid, status="voicemail", amd="machine")
        from .dialer import transfer_to_voicemail
        transfer_to_voicemail(call_uuid)
    return "", 204


@app.post("/ivr/voicemail")
def voicemail():
    return xml(ivr.voicemail())


@app.post("/ivr/hangup")
def hangup():
    call_uuid = request.form.get("CallUUID", "")
    with db.connect() as conn:
        db.bind_call_uuid(conn, request.form.get("RequestUUID", ""), call_uuid)
        db.update_call(conn, call_uuid, status=f"ended:{request.form.get('HangupCause', '')}")
    return "", 204
