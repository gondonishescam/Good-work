"""Run a campaign: python -m press1.dialer contacts.csv --campaign fall-promo

Pacing is by channels in flight, not by a fixed rate: a new call is placed only when
fewer than MAX_CONCURRENT_CALLS are active, and never faster than CALLS_PER_SECOND.
Blasting 100 calls at once is what overflows Plivo CPS (429s), the 3CX trunk and the
webhook server simultaneously.
"""
import argparse
import csv
import logging
import sys
import time
import uuid
from urllib.parse import urlencode

import plivo

from . import config, db
from .compliance import Contact, check_contact

log = logging.getLogger("press1.dialer")

_client = None


def client():
    global _client
    if _client is None:
        _client = plivo.RestClient(config.PLIVO_AUTH_ID, config.PLIVO_AUTH_TOKEN)
    return _client


def _url(path, **params):
    return f"{config.PUBLIC_URL}{path}?{urlencode(params)}"


def place_call(contact, cid):
    resp = client().calls.create(
        from_=config.CALLER_ID,
        to_=contact.phone,
        answer_url=_url("/ivr/answer", cid=cid, first_name=contact.first_name),
        answer_method="POST",
        hangup_url=_url("/ivr/hangup", cid=cid),
        hangup_method="POST",
        machine_detection="true",
        machine_detection_url=_url("/ivr/machine", cid=cid),
        machine_detection_method="POST",
        ring_timeout=30,
    )
    return resp.request_uuid


def transfer_to_voicemail(call_uuid):
    client().calls.update(
        call_uuid,
        legs="aleg",
        aleg_url=f"{config.PUBLIC_URL}/ivr/voicemail",
        aleg_method="POST",
    )


def _is_rate_limited(err):
    return "429" in str(err) or "too many" in str(err).lower()


def place_with_retry(contact, cid, attempts=5):
    delay = 1.0
    for i in range(attempts):
        try:
            return place_call(contact, cid)
        except plivo.exceptions.PlivoRestError as e:
            if not _is_rate_limited(e) or i == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


def wait_for_slot(poll=1.0, sleep=time.sleep):
    while True:
        with db.connect() as conn:
            db.expire_stale(conn, config.STALE_CALL_MINUTES)
            if db.active_calls(conn) < config.MAX_CONCURRENT_CALLS:
                return
        sleep(poll)


def run(csv_path, campaign, dry_run=False, sleep=time.sleep):
    min_gap = 1.0 / max(config.CALLS_PER_SECOND, 0.01)
    last = 0.0
    stats = {}

    def bump(k):
        stats[k] = stats.get(k, 0) + 1

    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            contact = Contact.from_row(row)
            with db.connect() as conn:  # short-lived: never hold the DB while waiting
                reason = check_contact(contact, lambda p: db.is_dnc(conn, p))
            if reason:
                bump(reason)
                print(f"skip {contact.phone or row.get('phone')}: {reason}")
                continue
            if dry_run:
                bump("would_call")
                continue

            wait_for_slot(sleep=sleep)
            gap = min_gap - (time.monotonic() - last)
            if gap > 0:
                sleep(gap)
            last = time.monotonic()

            # Row exists before the call, so webhooks can never arrive "too early".
            cid = uuid.uuid4().hex
            with db.connect() as conn:
                db.log_call(conn, cid, contact.phone, campaign, "queued")
            try:
                place_with_retry(contact, cid)
                bump("called")
            except plivo.exceptions.PlivoRestError as e:
                with db.connect() as conn:
                    db.update_call(conn, cid, status="create_failed")
                bump("error")
                print(f"error {contact.phone}: {e}", file=sys.stderr)
    print(stats)
    return stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--campaign", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    run(a.csv, a.campaign, a.dry_run)


if __name__ == "__main__":
    main()
