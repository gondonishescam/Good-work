import os

from dotenv import load_dotenv

load_dotenv()


def env(name, default=None):
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing environment variable {name}")
    return value


PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID", "")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN", "")
CALLER_ID = os.getenv("CALLER_ID", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
THREECX_SIP_URI = os.getenv("THREECX_SIP_URI", "")
OPT_OUT_PHONE = os.getenv("OPT_OUT_PHONE", CALLER_ID)
COMPANY_NAME = os.getenv("COMPANY_NAME", "our company")
DB_PATH = os.getenv("DB_PATH", "press1.db")
MAX_CONCURRENT_CALLS = int(os.getenv("MAX_CONCURRENT_CALLS", "20"))
CALLS_PER_SECOND = float(os.getenv("CALLS_PER_SECOND", "2"))
MAX_AGENT_CHANNELS = int(os.getenv("MAX_AGENT_CHANNELS", "10"))
STALE_CALL_MINUTES = int(os.getenv("STALE_CALL_MINUTES", "20"))

# Settings editable at runtime (Telegram bot). Stored in the DB `settings` table and
# applied on top of env vars by apply_overrides(); both the bot and webhook server read them.
EDITABLE = {
    "PLIVO_AUTH_ID": str,
    "PLIVO_AUTH_TOKEN": str,
    "CALLER_ID": str,
    "PUBLIC_URL": lambda v: v.rstrip("/"),
    "THREECX_SIP_URI": str,
    "OPT_OUT_PHONE": str,
    "COMPANY_NAME": str,
    "MAX_CONCURRENT_CALLS": int,
    "CALLS_PER_SECOND": float,
    "MAX_AGENT_CHANNELS": int,
    "STALE_CALL_MINUTES": int,
    "TEST_NUMBERS": str,  # comma-separated numbers you own, allowed for /test calls
}
SECRET = {"PLIVO_AUTH_TOKEN"}
TEST_NUMBERS = os.getenv("TEST_NUMBERS", "")


def apply_overrides(values):
    g = globals()
    for name, raw in values.items():
        if name in EDITABLE:
            g[name] = EDITABLE[name](raw)
