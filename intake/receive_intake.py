"""Local intake receiver for Vcore Sprint briefs.

Writes one JSON file per submission under intake/submissions/.
That directory is gitignored. This process is not reachable from
GitHub Pages. It does not send email and does not charge anyone.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("/workspace/vcore-sprint")
STORE = ROOT / "intake" / "submissions"
FIELDS = (
    "buyer_contact",
    "track",
    "offer_details",
    "audience",
    "price",
    "intended_action",
    "urls_or_files",
    "brand_voice",
    "approved_factual_claims",
    "required_timing",
)


def save_submission(data: dict, store: Path = STORE, now=None) -> Path:
    if not isinstance(data, dict):
        raise ValueError("submission must be an object")
    record = {field: data.get(field) for field in FIELDS}
    track = str(record.get("track") or "").strip().upper()
    if track not in {"A", "B"}:
        raise ValueError("track must be A or B")
    record["track"] = track
    for field in FIELDS:
        if field == "track":
            continue
        value = record.get(field)
        if value is None:
            record[field] = ""
        elif not isinstance(value, str):
            record[field] = str(value)
    if now is None:
        now = datetime.now(ZoneInfo("Europe/London"))
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("Europe/London"))
    else:
        now = now.astimezone(ZoneInfo("Europe/London"))
    record["received_london"] = now.isoformat()
    record["files_stored"] = False
    store.mkdir(parents=True, exist_ok=True)
    name = now.strftime("%Y%m%dT%H%M%S%f%z") + ".json"
    dest = store / name
    if dest.exists():
        raise ValueError("submission file already exists")
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    tmp.replace(dest)
    return dest


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print("No submission on stdin. Pass a JSON object.", file=sys.stderr)
        return 2
    data = json.loads(raw)
    dest = save_submission(data)
    print(f"stored={dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
