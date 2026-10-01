"""Classify Vcore Sprint Checkout Sessions into verified £1,500 seats.

Read-only helpers. Does not create Checkout Sessions, Payment Intents,
or Payment Links, and does not print API keys.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
CAP = 2
AMOUNT = 150000
CURRENCY = "gbp"
SKU = "vcore_sprint"
PRICE_ID = "price_1UIkoACnbXmmPPcBFRGRTS9r"
API = "https://api.stripe.com"

# Named in the 1 Oct assignment. Rules below also exclude them.
KNOWN_EXCLUDE = {
    "cs_live_a1H8TuTq3AxaYg1h8XbXnRTe7aNyNQucXXUwHlyredZM7sRnYq7fahZE7i":
        "proof Checkout, amount_total 0, metadata purpose=proof",
    "cs_live_a1rJ8zrwaOzLmbyBXxylbftYUnDaRFdakvkRenLTGdOBzQBgPfPPcCy24b":
        "unpaid session left to expire; not a paid seat",
}


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


def _meta(session: dict) -> dict:
    meta = session.get("metadata") or {}
    return meta if isinstance(meta, dict) else {}


def _price_ids(session: dict) -> list:
    line_items = session.get("line_items") or {}
    data = line_items.get("data") if isinstance(line_items, dict) else None
    ids = []
    if not data:
        return ids
    for item in data:
        if not isinstance(item, dict):
            continue
        price = item.get("price")
        if isinstance(price, dict) and price.get("id"):
            ids.append(price.get("id"))
        elif isinstance(price, str):
            ids.append(price)
    return ids


def exclusion_reason(session: dict, month: str) -> str | None:
    """Return why this session is not a verified seat for month, or None if it is."""
    if not isinstance(session, dict):
        return "not a session object"
    session_id = session.get("id")
    meta = _meta(session)
    purpose = str(meta.get("purpose") or "").strip().lower()
    if purpose == "proof":
        return "purpose=proof"
    if purpose == "practice":
        return "purpose=practice"
    if session.get("amount_total") == 0:
        return "amount_total 0"
    if session.get("payment_status") != "paid" or session.get("status") != "complete":
        status = session.get("status")
        pay = session.get("payment_status")
        if session_id in KNOWN_EXCLUDE and pay != "paid":
            return KNOWN_EXCLUDE[session_id]
        return f"not a successful payment (status={status}, payment_status={pay})"
    if str(session.get("currency") or "").lower() != CURRENCY:
        return f"currency is not {CURRENCY}"
    if session.get("amount_total") != AMOUNT:
        return f"amount_total is not {AMOUNT}"
    sku = meta.get("sku")
    prices = _price_ids(session)
    sku_ok = sku == SKU
    price_ok = PRICE_ID in prices
    if sku not in (None, "", SKU):
        return f"sku is not {SKU}"
    if not sku_ok and not price_ok:
        return f"missing sku {SKU} and price {PRICE_ID}"
    created = session.get("created")
    if created is None:
        return "no created time for London month"
    try:
        seat_month = created_month(created)
    except (TypeError, ValueError, OSError):
        return "created time is not a London month"
    if seat_month != month:
        return f"paid in {seat_month}, not {month}"
    return None


def verified_seats(sessions, month: str) -> tuple[list, list]:
    """Return (included, excluded) without double-counting session or payment_intent.

    included items are {session_id, payment_intent, month, amount_total, currency, sku}.
    excluded items are {session_id, reason}.
    """
    included = []
    excluded = []
    seen_sessions = set()
    seen_intents = set()
    for session in sessions:
        if not isinstance(session, dict):
            excluded.append({"session_id": None, "reason": "not a session object"})
            continue
        session_id = session.get("id")
        reason = exclusion_reason(session, month)
        if reason:
            if session_id in KNOWN_EXCLUDE and reason == KNOWN_EXCLUDE[session_id]:
                pass
            elif session_id in KNOWN_EXCLUDE and "purpose=proof" in reason:
                reason = KNOWN_EXCLUDE[session_id]
            excluded.append({"session_id": session_id, "reason": reason})
            continue
        if session_id in seen_sessions:
            excluded.append({"session_id": session_id, "reason": "duplicate checkout session"})
            continue
        intent = session.get("payment_intent")
        if isinstance(intent, dict):
            intent = intent.get("id")
        if intent and intent in seen_intents:
            excluded.append({
                "session_id": session_id,
                "reason": f"duplicate payment_intent {intent}",
            })
            continue
        seen_sessions.add(session_id)
        if intent:
            seen_intents.add(intent)
        meta = _meta(session)
        included.append({
            "session_id": session_id,
            "payment_intent": intent,
            "month": month,
            "amount_total": session.get("amount_total"),
            "currency": session.get("currency"),
            "sku": meta.get("sku") or SKU,
        })
    return included, excluded


def stripe_get(path: str, key: str) -> dict:
    if not path.startswith("/v1/"):
        raise SystemExit("Refusing non-read Stripe path.")
    request = urllib.request.Request(
        API + path,
        headers={"Authorization": "Bearer " + key},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_type, err_code, err_message = _stripe_error(exc)
        raise SystemExit(
            f"Stripe GET failed: HTTP {exc.code} type={err_type} code={err_code} message={err_message}"
        ) from None


def _stripe_error(exc: urllib.error.HTTPError) -> tuple[str, str, str]:
    err_type = ""
    err_code = ""
    err_message = ""
    try:
        body = json.loads(exc.read().decode("utf-8", errors="replace"))
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            err_type = str(error.get("type") or "")
            err_code = str(error.get("code") or "")
            err_message = str(error.get("message") or "")
    except Exception:
        pass
    return err_type, err_code, err_message


def list_sessions(key: str) -> list:
    found = []
    starting_after = None
    for _page in range(20):
        params = [("limit", "100")]
        if starting_after:
            params.append(("starting_after", starting_after))
        payload = stripe_get("/v1/checkout/sessions?" + urllib.parse.urlencode(params), key)
        batch = payload.get("data") or []
        if not isinstance(batch, list):
            break
        for session in batch:
            if isinstance(session, dict):
                found.append(session)
        if not payload.get("has_more") or not batch:
            break
        last = batch[-1]
        starting_after = last.get("id") if isinstance(last, dict) else None
        if not starting_after:
            break
    return found
