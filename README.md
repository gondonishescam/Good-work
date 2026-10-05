# Press 1 campaign (Plivo + 3CX)

An outbound sales call to customers who gave **prior express written consent**.
1. The customer hears who is calling and why.
2. **1** connects them to the 3CX queue. **9** opts them out (DNC).
3. If an answering machine picks up, a voicemail plays with a callback number and opt-out instructions.

## Setup
1. `pip install -r requirements.txt`, then `cp .env.example .env` and fill it in.
2. **Plivo:** buy a DID for `CALLER_ID` (your own number, no spoofing). Register the number for STIR/SHAKEN / CNAM so calls don't get flagged as "Spam Likely".
3. **3CX:** add a SIP trunk to Plivo (Plivo Zentrunk / SIP endpoint). Create an inbound rule that routes calls from Plivo to the queue or ring group. Put that queue's SIP URI in `THREECX_SIP_URI`.
4. Run the webhooks app: `gunicorn -c gunicorn.conf.py press1.app:app` behind HTTPS (nginx) at `PUBLIC_URL`. Don't use `flask run` in production.
5. Prepare the contacts CSV (see `contacts.example.csv`). Every row needs `consent_date` and `consent_source`.
6. Do a dry run (checks only, no calls): `python -m press1.dialer contacts.csv --campaign fall --dry-run`
7. Launch: `python -m press1.dialer contacts.csv --campaign fall`

## What the code enforces
- It won't call without consent records (date + source).
- It won't call numbers on the internal DNC list. Pressing 9 adds the number there immediately.
- Calling hours are 8:00–21:00 in the customer's local time; FL, OK and MD use 8:00–20:00.
- The message identifies the company first and offers opt-out at the start.
- Plivo webhooks are checked with a V3 signature.

## What you must handle outside the code (not legal advice)
- **Consent:** keep proof of written consent for at least 4–5 years. It must specifically cover prerecorded/autodialed calls from your company. Since 2025, consent is one-to-one: lead-generator consent given "for partners" doesn't count.
- **Revocation:** honor revocation through any reasonable channel (SMS "STOP", email, phone) within 10 business days. Add those numbers to the `dnc` table too.
- **DNC lists:** maintain an internal DNC list, and check state DNC lists and state mini-TCPA laws (FL, OK, MD, WA and others limit call frequency and hours).
- **Abandonment rate:** keep it ≤3% per 30 days if agents don't pick up in time. Size the 3CX queue to match `MAX_CALLS_PER_MINUTE`.

## Telegram control (from your phone)
1. Create a bot with @BotFather to get a token. Get your id from @userinfobot.
2. On a server: put `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_ID` in `.env`, then run `docker compose up -d --build`. HTTPS for `PUBLIC_URL` points to port 8000.
3. In the bot: `/start` opens the menu (Russian UI); everything is set with buttons:
   - **📡 Plivo**: Auth ID, Auth Token, Webhook URL; **📋 Мои номера** picks the Caller ID from your Plivo account; **🔌 Проверить** checks keys, balance, Caller ID ownership and `/health`
   - **☎️ 3CX**: **🧙 Мастер настройки** asks the PBX address and queue number and builds the SIP URI; **🔌 Проверить** resolves the host and probes SIP ports
   - **⚡️ Нагрузка**, **🏢 Компания** (incl. test numbers), **🧪 Тестовый звонок**, **🚀 Кампания** (send the CSV for a dry-run report, then start/stop/status)
   - Values are validated (phone/URL/SIP formats, number ranges) before saving. `/set NAME value` and the other commands still work.
- Only `TELEGRAM_OWNER_ID` is answered. Messages with keys are deleted right after saving.
- The keys still pass through Telegram servers. After testing, rotate the Plivo token, or set secrets only via `.env`.

## Load and concurrency
The bottlenecks, in the order they usually show up:

| Limit | Setting | What happens if you exceed it |
|---|---|---|
| Plivo CPS (default ~2/s on an account) | `CALLS_PER_SECOND` | 429 errors, calls never get created |
| Simultaneous calls on the 3CX trunk and licence | `MAX_AGENT_CHANNELS` | SIP 503/486, the transfer after pressing 1 drops |
| Available agents | `MAX_CONCURRENT_CALLS` | the 3CX queue overflows, customers wait or are abandoned |
| Webhook server | `gunicorn.conf.py` | Plivo gets no XML in time and the caller hears silence |

How the code handles each one:
- The dialer places a new call only when there is a free channel (it counts active calls), and never faster than the CPS limit. On a 429 it backs off and retries.
- A "press 1" atomically takes an agent line. If none is free, the customer hears a polite callback message instead of a broken transfer.
- SQLite runs in WAL mode with busy_timeout and creates the schema only once. Webhooks don't hit "database is locked" errors.
- Every call gets a tracking id (`cid`) before it is placed, so a fast pickup can't outrun the database record.
- Calls whose hangup webhook was lost are released after `STALE_CALL_MINUTES`.
- The AMD-to-voicemail transfer runs in a background pool and doesn't block webhooks.

Rule of thumb: `MAX_CONCURRENT_CALLS` ≈ agents × 2–3 (most calls end on IVR or voicemail). `MAX_AGENT_CHANNELS` must not exceed the simultaneous calls allowed by your 3CX licence and trunk.

Load test: `PRESS1_TESTING=1 gunicorn -c gunicorn.conf.py press1.app:app`, then `python tests/load_test.py 300`.

## Tests
`python -m pytest`
