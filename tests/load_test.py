"""Simulate N simultaneous answered calls against a running server.

    gunicorn -c gunicorn.conf.py press1.app:app   (with PRESS1_TESTING=1)
    python tests/load_test.py 200
"""
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "http://127.0.0.1:8000"


def one_call(i):
    s = requests.Session()
    cu = uuid.uuid4().hex
    to = f"+1212{5550000 + i:07d}"
    steps = [
        ("/ivr/answer?first_name=T", {"CallUUID": cu, "To": to}, b"GetInput"),
        ("/ivr/input", {"CallUUID": cu, "Digits": "1" if i % 3 else "9", "To": to}, b"Speak"),
        ("/ivr/hangup", {"CallUUID": cu, "HangupCause": "NORMAL"}, None),
    ]
    for path, data, expect in steps:
        r = s.post(BASE + path, data=data, timeout=10)
        if r.status_code >= 400 or (expect and expect not in r.content):
            return f"{path} -> {r.status_code}"
    return None


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    t = time.time()
    with ThreadPoolExecutor(max_workers=n) as ex:
        errors = [e for e in ex.map(one_call, range(n)) if e]
    print(f"{n} calls, {len(errors)} failed, {time.time() - t:.2f}s", errors[:5])
    sys.exit(1 if errors else 0)
