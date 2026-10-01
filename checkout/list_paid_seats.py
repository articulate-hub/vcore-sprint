"""Print verified paid Sprint seats for the current Europe/London month.

Counts only successful payments of exactly £1,500 (amount_total 150000,
currency gbp, paid and complete) for sku vcore_sprint. Excludes purpose=proof,
amount_total 0, and practice records. Does not double-count a Checkout Session
or Payment Intent. Does not create charges. Does not print the API key.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paid_seats import list_sessions, london_month, verified_seats
from seat_ledger import load_stripe_secret_key


def main() -> int:
    month = london_month()
    key = load_stripe_secret_key()
    sessions = list_sessions(key)
    del key
    included, excluded = verified_seats(sessions, month)
    print(f"month={month} verified_paid_seats={len(included)}")
    if included:
        for seat in included:
            print(
                "seat session_id={session_id} payment_intent={payment_intent}".format(
                    **seat
                )
            )
    else:
        print("seat session_ids=")
    for item in excluded:
        print(f"excluded session_id={item['session_id']} reason={item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
