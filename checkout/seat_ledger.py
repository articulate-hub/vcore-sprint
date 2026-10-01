"""Local Vcore Sprint seat ledger.

Calendar month is Europe/London. Cap is 2 paid seats.
This module does not call Stripe and does not create payments.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
CAP = 2
PRICE_ID = "price_1UIkoACnbXmmPPcBFRGRTS9r"
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")

ROOT = Path("/workspace/vcore-sprint")
SEATS_PATH = ROOT / "checkout" / "seats.json"
INBOX_DIR = ROOT / "payments" / "inbox"

SECRET_PATHS = (
    Path("/home/box/sand-data/box-secrets.json"),
    Path("/home/box/agent-data/box-secrets.json"),
)


def london_month(now=None) -> str:
    if now is None:
        now = datetime.now(LONDON)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=LONDON)
    else:
        now = now.astimezone(LONDON)
    return f"{now.year:04d}-{now.month:02d}"


def created_month(created_unix) -> str:
    dt = datetime.fromtimestamp(int(created_unix), LONDON)
    return f"{dt.year:04d}-{dt.month:02d}"


def metadata_month(session: dict):
    meta = session.get("metadata") or {}
    if not isinstance(meta, dict):
        return None
    value = meta.get("month")
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def session_counts_for_month(session: dict, month: str) -> bool:
    """True if metadata month is this month OR created time falls in it."""
    if metadata_month(session) == month:
        return True
    created = session.get("created")
    if created is None:
        return False
    try:
        return created_month(created) == month
    except (TypeError, ValueError, OSError):
        return False


def distinct_ids(ids) -> list:
    seen = set()
    out = []
    for item in ids:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def remaining_for_count(count: int) -> int:
    return max(0, CAP - int(count))


def price_id_of(line_item: dict):
    price = line_item.get("price")
    if isinstance(price, dict):
        return price.get("id")
    if isinstance(price, str):
        return price
    return None


def session_has_price(session: dict, price_id: str = PRICE_ID) -> bool:
    line_items = session.get("line_items") or {}
    data = line_items.get("data") if isinstance(line_items, dict) else None
    if not data:
        return False
    for item in data:
        if isinstance(item, dict) and price_id_of(item) == price_id:
            return True
    return False


def inbox_record(session: dict) -> dict:
    """Whitelist only. Never persist card numbers or payment-method blobs."""
    details = session.get("customer_details") if isinstance(session.get("customer_details"), dict) else {}
    email = details.get("email") if isinstance(details, dict) else None
    if not email:
        email = session.get("customer_email")
    if email is not None and not isinstance(email, str):
        email = None
    month = metadata_month(session)
    if month is None and session.get("created") is not None:
        try:
            month = created_month(session.get("created"))
        except (TypeError, ValueError, OSError):
            month = None
    return {
        "session_id": session.get("id"),
        "amount": session.get("amount_total"),
        "currency": session.get("currency"),
        "customer_email": email,
        "month": month,
        "created": session.get("created"),
    }


def empty_state(month: str) -> dict:
    return {"month": month, "paid_session_ids": [], "remaining": CAP}


def read_state(path: Path) -> dict | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("seats.json must be an object")
    return data


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "month": state["month"],
        "paid_session_ids": list(state["paid_session_ids"]),
        "remaining": int(state["remaining"]),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def apply_paid_sessions(sessions, month: str, seats_path: Path, inbox_dir: Path) -> dict:
    """Recompute the month display from paid sessions. Idempotent inbox writes.

    A third distinct paid id in the same month leaves remaining at 0.
    Existing inbox files are not rewritten or deleted.
    """
    inbox_dir.mkdir(parents=True, exist_ok=True)
    ids = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        if session.get("payment_status") != "paid":
            continue
        if not session_has_price(session):
            continue
        meta = session.get("metadata") or {}
        if isinstance(meta, dict) and str(meta.get("purpose") or "") == "proof":
            continue
        if session.get("amount_total") == 0:
            continue
        record = inbox_record(session)
        session_id = record.get("session_id")
        if not isinstance(session_id, str) or not SESSION_ID_RE.fullmatch(session_id):
            continue
        dest = inbox_dir / f"{session_id}.json"
        if not dest.exists():
            dest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if session_counts_for_month(session, month):
            ids.append(session_id)
    distinct = distinct_ids(ids)
    state = {
        "month": month,
        "paid_session_ids": distinct,
        "remaining": remaining_for_count(len(distinct)),
    }
    write_state(seats_path, state)
    return state


def month_reset(seats_path: Path, now=None) -> dict:
    """If the stored month is not the current London month, reset the display count.

    Does not delete payment inbox files.
    """
    month = london_month(now)
    current = read_state(seats_path)
    if current is None or current.get("month") != month:
        state = empty_state(month)
        write_state(seats_path, state)
        return state
    # Normalise remaining in case a hand-edited file drifted.
    ids = distinct_ids(current.get("paid_session_ids") or [])
    state = {
        "month": month,
        "paid_session_ids": ids,
        "remaining": remaining_for_count(len(ids)),
    }
    write_state(seats_path, state)
    return state


def load_stripe_secret_key() -> str:
    """Read the key from box secrets. Caller must not print the return value."""
    for path in SECRET_PATHS:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        card = data.get("card") if isinstance(data, dict) else None
        if isinstance(card, dict):
            key = card.get("STRIPE_SECRET_KEY")
            if isinstance(key, str) and key.strip():
                return key.strip()
    raise SystemExit("Stripe secret key not found in box secrets. No key was printed.")
