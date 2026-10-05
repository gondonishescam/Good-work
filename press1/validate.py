"""Setting validators shared by the Telegram bot and the web panel.

Each validator returns the normalized value or raises Invalid, which carries the
message in Russian (bot, also str()) and English (panel).
"""
import re

from .compliance import normalize_phone


class Invalid(ValueError):
    def __init__(self, ru, en):
        super().__init__(ru)
        self.ru, self.en = ru, en


def phone(v):
    p = normalize_phone(v)
    if not re.fullmatch(r"\+\d{10,15}", p):
        raise Invalid("нужен номер в формате +1XXXXXXXXXX", "use the format +1XXXXXXXXXX")
    return p


def phones(v):
    items = [x for x in re.split(r"[,;\n]+", v or "") if x.strip()]
    if not items:
        raise Invalid("нужен хотя бы один номер", "add at least one number")
    return ",".join(phone(x) for x in items)


def auth_id(v):
    v = (v or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{20}", v):
        raise Invalid("Auth ID — 20 латинских букв/цифр, обычно начинается с MA или SA",
                      "Auth ID is 20 letters/digits, usually starting with MA or SA")
    return v


def auth_token(v):
    v = (v or "").strip()
    if len(v) < 20 or " " in v:
        raise Invalid("токен слишком короткий — скопируй целиком из Plivo Console",
                      "token looks too short — copy the whole value from Plivo Console")
    return v


def url(v):
    v = (v or "").strip().rstrip("/")
    if v and not v.startswith("http"):
        v = "https://" + v
    if not re.fullmatch(r"https://[\w.-]+(:\d+)?(/[\w./-]*)?", v):
        raise Invalid("нужен https-адрес, например https://dialer.example.com",
                      "needs an https address, e.g. https://dialer.example.com")
    return v


def sip(v):
    v = (v or "").strip()
    if v and not v.lower().startswith("sip:"):
        v = "sip:" + v
    if not re.fullmatch(r"sip:[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}(:\d+)?", v):
        raise Invalid("нужно вида sip:800@company.3cx.us", "use the form sip:800@company.3cx.us")
    return v


def extension(v):
    v = (v or "").strip()
    if not re.fullmatch(r"[\w.+-]{1,32}", v):
        raise Invalid("номер очереди/группы, например 800", "queue or ring group number, e.g. 800")
    return v


def host(v):
    v = re.sub(r"^(https?://|sip:)", "", (v or "").strip()).split("/")[0]
    if not re.fullmatch(r"[\w.-]+\.[a-zA-Z]{2,}(:\d+)?", v):
        raise Invalid("нужен адрес АТС, например company.3cx.us", "PBX address, e.g. company.3cx.us")
    return v


def integer(lo, hi):
    def f(v):
        try:
            n = int(str(v).strip())
        except ValueError:
            raise Invalid("нужно целое число", "must be a whole number")
        if not lo <= n <= hi:
            raise Invalid(f"допустимо от {lo} до {hi}", f"allowed range is {lo}–{hi}")
        return str(n)
    return f


def number(lo, hi):
    def f(v):
        try:
            n = float(str(v).strip().replace(",", "."))
        except ValueError:
            raise Invalid("нужно число", "must be a number")
        if not lo <= n <= hi:
            raise Invalid(f"допустимо от {lo} до {hi}", f"allowed range is {lo}–{hi}")
        return str(n)
    return f


def text(v):
    v = (v or "").strip()
    if not 1 <= len(v) <= 60:
        raise Invalid("от 1 до 60 символов", "1 to 60 characters")
    return v


def campaign_name(v):
    v = (v or "").strip()
    if not re.fullmatch(r"[\w.-]{1,40}", v):
        raise Invalid("только буквы, цифры, - _ .", "letters, digits, - _ . only (no spaces)")
    return v


# Setting name -> validator. Every editable setting goes through one of these.
SETTINGS = {
    "PLIVO_AUTH_ID": auth_id,
    "PLIVO_AUTH_TOKEN": auth_token,
    "CALLER_ID": phone,
    "PUBLIC_URL": url,
    "THREECX_SIP_URI": sip,
    "MAX_AGENT_CHANNELS": integer(1, 500),
    "MAX_CONCURRENT_CALLS": integer(1, 500),
    "CALLS_PER_SECOND": number(0.1, 50),
    "STALE_CALL_MINUTES": integer(1, 240),
    "COMPANY_NAME": text,
    "OPT_OUT_PHONE": phone,
    "TEST_NUMBERS": phones,
}
