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
MAX_CALLS_PER_MINUTE = int(os.getenv("MAX_CALLS_PER_MINUTE", "30"))
