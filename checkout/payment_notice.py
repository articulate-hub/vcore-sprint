"""Notice stub for a new verified £1,500 Sprint payment.

Compares Stripe seats for the current London month with a gitignored
last-seen id file. Writes one line under intake/notices/ when a new
session id appears. Does not send the notice. Does not charge anyone.
Does not print the API key.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paid_seats import list_sessions, london_month, verified_seats
from seat_ledger import load_stripe_secret_key

ROOT = Path("/workspace/vcore-sprint")
LAST_SEEN = ROOT / "checkout" / "last_seen_paid_ids.json"
NOTICE_DIR = ROOT / "intake" / "notices"


def load_seen(path: Path) -> list:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = data.get("session_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        return []
    return [item for item in ids if isinstance(item, str)]


def main() -> int:
    month = london_month()
    key = load_stripe_secret_key()
    sessions = list_sessions(key)
    del key
    included, _excluded = verified_seats(sessions, month)
    current = [seat["session_id"] for seat in included if seat.get("session_id")]
    seen = load_seen(LAST_SEEN)
    new_ids = [session_id for session_id in current if session_id not in seen]
    LAST_SEEN.parent.mkdir(parents=True, exist_ok=True)
    payload = {"month": month, "session_ids": current}
    tmp = LAST_SEEN.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(LAST_SEEN)
    if not new_ids:
        print(f"month={month} new_verified_seats=0 notice=none")
        return 0
    NOTICE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo("Europe/London")).strftime("%Y%m%dT%H%M%S%z")
    notice = NOTICE_DIR / f"notice-{stamp}.txt"
    # One line. No email. Not sent.
    line = (
        f"{stamp} Europe/London new verified £1500 seat(s) month={month} "
        + "session_ids=" + ",".join(new_ids)
    )
    notice.write_text(line + "\n", encoding="utf-8")
    print(f"month={month} new_verified_seats={len(new_ids)} notice={notice}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
