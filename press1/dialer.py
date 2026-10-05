"""Run a campaign: python -m press1.dialer contacts.csv --campaign fall-promo"""
import argparse
import csv
import sys
import time
from urllib.parse import urlencode

import plivo

from . import config, db
from .compliance import Contact, check_contact


def client():
    return plivo.RestClient(config.PLIVO_AUTH_ID, config.PLIVO_AUTH_TOKEN)


def place_call(contact):
    query = urlencode({"first_name": contact.first_name})
    resp = client().calls.create(
        from_=config.CALLER_ID,
        to_=contact.phone,
        answer_url=f"{config.PUBLIC_URL}/ivr/answer?{query}",
        answer_method="POST",
        hangup_url=f"{config.PUBLIC_URL}/ivr/hangup",
        hangup_method="POST",
        machine_detection="true",
        machine_detection_url=f"{config.PUBLIC_URL}/ivr/machine",
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


def run(csv_path, campaign, dry_run=False):
    interval = 60.0 / max(config.MAX_CALLS_PER_MINUTE, 1)
    stats = {}
    with open(csv_path, newline="") as f, db.connect() as conn:
        for row in csv.DictReader(f):
            contact = Contact.from_row(row)
            reason = check_contact(contact, lambda p: db.is_dnc(conn, p))
            if reason:
                stats[reason] = stats.get(reason, 0) + 1
                print(f"skip {contact.phone or row.get('phone')}: {reason}")
                continue
            if dry_run:
                stats["would_call"] = stats.get("would_call", 0) + 1
                continue
            try:
                uuid = place_call(contact)
            except plivo.exceptions.PlivoRestError as e:
                stats["error"] = stats.get("error", 0) + 1
                print(f"error {contact.phone}: {e}", file=sys.stderr)
                continue
            db.log_call(conn, uuid, contact.phone, campaign, "queued")
            conn.commit()
            stats["called"] = stats.get("called", 0) + 1
            time.sleep(interval)
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
