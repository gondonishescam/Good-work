# Press 1 campaign (Plivo + 3CX)

An outbound sales call to customers who gave **prior express written consent**.
1. The customer hears who is calling and why.
2. **1** connects them to the 3CX queue. **9** opts them out (DNC).
3. If an answering machine picks up, a voicemail plays with a callback number and opt-out instructions.

## Setup
1. `pip install -r requirements.txt`, then `cp .env.example .env` and fill it in.
2. **Plivo:** buy a DID for `CALLER_ID` (your own number, no spoofing). Register the number for STIR/SHAKEN / CNAM so calls don't get flagged as "Spam Likely".
3. **3CX:** add a SIP trunk to Plivo (Plivo Zentrunk / SIP endpoint). Create an inbound rule that routes calls from Plivo to the queue or ring group. Put that queue's SIP URI in `THREECX_SIP_URI`.
4. Run the webhooks app: `flask --app press1.app run` behind HTTPS at `PUBLIC_URL` (in prod, use gunicorn behind nginx).
5. Prepare the contacts CSV (see `contacts.example.csv`). Every row needs `consent_date` and `consent_source`.
6. Do a dry run (checks only, no calls): `python -m press1.dialer contacts.csv --campaign fall --dry-run`
7. Launch: `python -m press1.dialer contacts.csv --campaign fall`

## What the code enforces
- It won't call without consent records (date + source).
- It won't call numbers on the internal DNC list. Pressing 9 adds the number there immediately.
- Calling hours are 8:00–21:00 in the customer's local time; FL, OK and MD use 8:00–20:00.
- The message identifies the company first and offers opt-out at the start.
- Plivo webhooks are checked with a V3 signature.
- The call rate is capped (`MAX_CALLS_PER_MINUTE`).

## What you must handle outside the code (not legal advice)
- **Consent:** keep proof of written consent for at least 4–5 years. It must specifically cover prerecorded/autodialed calls from your company. Since 2025, consent is one-to-one: lead-generator consent given "for partners" doesn't count.
- **Revocation:** honor revocation through any reasonable channel (SMS "STOP", email, phone) within 10 business days. Add those numbers to the `dnc` table too.
- **DNC lists:** maintain an internal DNC list, and check state DNC lists and state mini-TCPA laws (FL, OK, MD, WA and others limit call frequency and hours).
- **Abandonment rate:** keep it ≤3% per 30 days if agents don't pick up in time. Size the 3CX queue to match `MAX_CALLS_PER_MINUTE`.

## Tests
`python -m pytest`
