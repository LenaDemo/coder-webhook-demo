"""Existing basic behavior. The agent should ADD idempotency regressions."""
from contextlib import contextmanager
import tempfile
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from demo import event

class Basics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = app.DB_PATH
        app.DB_PATH = Path(self.temp.name) / "orders.sqlite3"
        app.initialize()
    def tearDown(self):
        app.DB_PATH = self.previous
        self.temp.cleanup()
    def test_valid_order_fields(self):
        payload = event("evt_1001")
        app.validate_event(payload)
        result = app.process_event(payload)
        self.assertTrue(result["created"])
        row = app.state()["orders"][0]
        self.assertEqual(row["event_id"], payload["event_id"])
        self.assertEqual(row["total_cents"], 12900)
    def test_distinct_events_create_distinct_orders(self):
        app.process_event(event("evt_1001"))
        app.process_event(event("evt_1002"))
        self.assertEqual(app.state()["summary"]["orders"], 2)
    def test_schema_initialization_preserves_orders(self):
        app.process_event(event("evt_1001"))
        app.initialize()
        self.assertEqual(app.state()["summary"]["orders"], 1)
    def test_precommit_exception_rolls_back_order(self):
        with self.assertRaises(app.SimulatedFailure):
            app.process_event(event("evt_1004"), fail_before_commit=True)
        self.assertEqual(app.state()["summary"]["orders"], 0)
        app.process_event(event("evt_1004"))
        self.assertEqual(app.state()["summary"]["orders"], 1)
    def test_invalid_amount_is_rejected(self):
        for amount in [-1, True, "12900", None]:
            with self.assertRaises(ValueError):
                app.validate_event({**event("evt_1001"), "total_cents":amount})
    def test_reset_keeps_schema(self):
        app.process_event(event("evt_1001"))
        app.reset_data()
        self.assertEqual(app.state()["summary"]["orders"], 0)
        app.process_event(event("evt_1002"))
        self.assertEqual(app.state()["summary"]["orders"], 1)

if __name__ == "__main__":
    unittest.main()
