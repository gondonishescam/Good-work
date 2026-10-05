"""Settings and connectivity checks shared by the Telegram bot and the web panel."""
import socket

import requests

from . import config, db, dialer, validate

REQUIRED = ("PLIVO_AUTH_ID", "PLIVO_AUTH_TOKEN", "CALLER_ID", "PUBLIC_URL", "THREECX_SIP_URI")
SECTION_FIELDS = {
    "plivo": ("PLIVO_AUTH_ID", "PLIVO_AUTH_TOKEN", "CALLER_ID", "PUBLIC_URL"),
    "3cx": ("THREECX_SIP_URI", "MAX_AGENT_CHANNELS"),
}


def current(name):
    return str(getattr(config, name, "") or "")


def mask(name, value):
    if name in config.SECRET and value:
        return value[:3] + "…" + value[-2:]
    return value


def save(name, raw):
    """Validate, store and apply one setting. Returns the normalized value; raises Invalid."""
    value = validate.SETTINGS[name](raw)
    config.EDITABLE[name](value)
    with db.connect() as conn:
        db.set_setting(conn, name, value)
    db.load_settings()
    return value


def ready(section):
    return all(current(f) for f in SECTION_FIELDS[section])


def warnings(section=None, lang="ru"):
    out = []
    if config.MAX_AGENT_CHANNELS > config.MAX_CONCURRENT_CALLS:
        out.append(({"3cx", "limits"},
                    "линий на 3CX больше, чем одновременных звонков — лишние линии простаивают",
                    "more 3CX lines than simultaneous calls — the extra lines will sit idle"))
    if config.PUBLIC_URL and "example.com" in config.PUBLIC_URL:
        out.append(({"plivo"}, "Webhook URL — это ещё пример, укажи свой сервер",
                    "Webhook URL is still the example — set your own server"))
    if config.THREECX_SIP_URI and "yourcompany" in config.THREECX_SIP_URI:
        out.append(({"3cx"}, "SIP URI 3CX — это ещё пример", "3CX SIP URI is still the example"))
    i = 1 if lang == "ru" else 2
    return [w[i] for w in out if section is None or section in w[0]]


# Raw probes. Each returns data or raises; callers word the result in their own language.

def plivo_account():
    acc = dialer.client().account.get()
    return {"name": str(acc.name), "balance": str(acc.cash_credits)}


def plivo_numbers():
    nums = dialer.client().numbers.list(limit=20)
    return [{"number": "+" + str(n.number).lstrip("+"), "alias": getattr(n, "alias", "") or ""}
            for n in nums]


def webhook_ok():
    r = requests.get(config.PUBLIC_URL + "/health", timeout=5)
    return r.ok, r.status_code


def sip_host():
    return config.THREECX_SIP_URI.split("@", 1)[1].split(":")[0]


def resolve(host):
    return socket.getaddrinfo(host, 5060)[0][4][0]


def open_sip_port(host):
    for port in (5060, 5061):
        try:
            with socket.create_connection((host, port), timeout=3):
                return port
        except OSError:
            continue
    return None
