"""TCPA-oriented pre-call checks. Not legal advice: have counsel review your setup."""
import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# TCPA / FCC: no telemarketing calls before 8am or after 9pm called party's local time.
# Some states are stricter (e.g. FL, OK, MD: 8am-8pm) - tighten via STATE_HOURS.
DEFAULT_HOURS = (8, 21)
STATE_HOURS = {"FL": (8, 20), "OK": (8, 20), "MD": (8, 20)}

E164_US = re.compile(r"^\+1[2-9]\d{2}[2-9]\d{6}$")


@dataclass
class Contact:
    phone: str
    first_name: str
    timezone: str
    state: str
    consent_date: str  # ISO date when prior express written consent was captured
    consent_source: str  # e.g. form URL / record id proving consent

    @classmethod
    def from_row(cls, row):
        return cls(
            phone=normalize_phone(row.get("phone", "")),
            first_name=(row.get("first_name") or "").strip(),
            timezone=(row.get("timezone") or "").strip(),
            state=(row.get("state") or "").strip().upper(),
            consent_date=(row.get("consent_date") or "").strip(),
            consent_source=(row.get("consent_source") or "").strip(),
        )


def normalize_phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits if digits else ""


def check_contact(contact, conn_is_dnc, now_utc=None):
    """Return None if the contact may be called now, otherwise a skip reason."""
    if not E164_US.match(contact.phone):
        return "invalid_phone"
    if not contact.consent_date or not contact.consent_source:
        return "no_written_consent"
    try:
        if date.fromisoformat(contact.consent_date) > date.today():
            return "invalid_consent_date"
    except ValueError:
        return "invalid_consent_date"
    if conn_is_dnc(contact.phone):
        return "dnc"
    try:
        tz = ZoneInfo(contact.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return "unknown_timezone"
    now = (now_utc or datetime.now(ZoneInfo("UTC"))).astimezone(tz)
    start, end = STATE_HOURS.get(contact.state, DEFAULT_HOURS)
    if not (start <= now.hour < end):
        return "outside_calling_hours"
    return None
