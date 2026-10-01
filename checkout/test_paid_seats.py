"""Unit tests for verified £1,500 seat classification. No Stripe calls."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "intake"))

import paid_seats
import receive_intake

LONDON = ZoneInfo("Europe/London")
PROOF = "cs_live_a1H8TuTq3AxaYg1h8XbXnRTe7aNyNQucXXUwHlyredZM7sRnYq7fahZE7i"
UNPAID = "cs_live_a1rJ8zrwaOzLmbyBXxylbftYUnDaRFdakvkRenLTGdOBzQBgPfPPcCy24b"


def ts(year, month, day):
    return int(datetime(year, month, day, 12, 0, tzinfo=LONDON).timestamp())


def seat(session_id, created, **overrides):
    session = {
        "id": session_id,
        "status": "complete",
        "payment_status": "paid",
        "amount_total": 150000,
        "currency": "gbp",
        "created": created,
        "payment_intent": "pi_" + session_id,
        "metadata": {"sku": "vcore_sprint", "month": "2026-10"},
        "line_items": {"data": [{"price": {"id": paid_seats.PRICE_ID}}]},
    }
    session.update(overrides)
    return session


class ClassifyTests(unittest.TestCase):
    def test_october_seat_counts_once(self):
        included, excluded = paid_seats.verified_seats(
            [seat("cs_ok", ts(2026, 10, 2))],
            "2026-10",
        )
        self.assertEqual(len(included), 1)
        self.assertEqual(included[0]["session_id"], "cs_ok")
        self.assertEqual(excluded, [])

    def test_proof_and_unpaid_and_zero_excluded(self):
        sessions = [
            {
                "id": PROOF,
                "status": "complete",
                "payment_status": "paid",
                "amount_total": 0,
                "currency": "gbp",
                "created": ts(2026, 9, 30),
                "metadata": {"sku": "vcore_sprint", "purpose": "proof", "month": "2026-09"},
            },
            {
                "id": UNPAID,
                "status": "open",
                "payment_status": "unpaid",
                "amount_total": 150000,
                "currency": "gbp",
                "created": ts(2026, 9, 30),
                "metadata": {"sku": "vcore_sprint", "month": "2026-09"},
            },
            seat("cs_zero", ts(2026, 10, 2), amount_total=0, metadata={"sku": "vcore_sprint", "purpose": "practice"}),
        ]
        included, excluded = paid_seats.verified_seats(sessions, "2026-10")
        self.assertEqual(included, [])
        reasons = {item["session_id"]: item["reason"] for item in excluded}
        self.assertIn("purpose=proof", reasons[PROOF])
        self.assertIn("unpaid", reasons[UNPAID])
        self.assertIn("practice", reasons["cs_zero"])

    def test_september_payment_not_an_october_seat(self):
        included, excluded = paid_seats.verified_seats(
            [seat("cs_sep", ts(2026, 9, 15))],
            "2026-10",
        )
        self.assertEqual(included, [])
        self.assertIn("2026-09", excluded[0]["reason"])

    def test_duplicate_session_and_payment_intent(self):
        first = seat("cs_a", ts(2026, 10, 3), payment_intent="pi_same")
        second = seat("cs_b", ts(2026, 10, 3), payment_intent="pi_same")
        included, excluded = paid_seats.verified_seats([first, first, second], "2026-10")
        self.assertEqual([item["session_id"] for item in included], ["cs_a"])
        self.assertEqual(len(excluded), 2)

    def test_wrong_amount_excluded(self):
        included, _excluded = paid_seats.verified_seats(
            [seat("cs_low", ts(2026, 10, 4), amount_total=1500)],
            "2026-10",
        )
        self.assertEqual(included, [])


class IntakeTests(unittest.TestCase):
    def test_save_roundtrip_without_using_live_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = receive_intake.save_submission(
                {
                    "buyer_contact": "Example Buyer example@example.com",
                    "track": "a",
                    "offer_details": "A workshop",
                    "audience": "Existing list",
                    "price": "£40",
                    "intended_action": "Book",
                    "urls_or_files": "https://example.com",
                    "brand_voice": "Plain",
                    "approved_factual_claims": "None",
                    "required_timing": "This month",
                },
                store=Path(tmp),
                now=datetime(2026, 10, 1, 3, 0, tzinfo=LONDON),
            )
            record = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(record["track"], "A")
            self.assertEqual(record["files_stored"], False)
            self.assertIn("buyer_contact", record)


if __name__ == "__main__":
    unittest.main()
