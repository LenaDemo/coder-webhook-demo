"""Regression tests: one order per webhook event_id, enforced by SQLite."""
from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app
from demo import event


def count(db_path, sql, *params):
    db = sqlite3.connect(db_path)
    try:
        return db.execute(sql, params).fetchone()[0]
    finally:
        db.close()


def deliver_in_process(db_path, payload, barrier, results):
    """Runs in a separate OS process with its own sqlite3 connection."""
    app.DB_PATH = Path(db_path)
    barrier.wait(timeout=30)
    try:
        results.put(("ok", app.process_event(payload)))
    except Exception as exc:  # reported back to the parent test
        results.put(("error", repr(exc)))


class TempDatabase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = app.DB_PATH
        self.db_path = Path(self.temp.name) / "orders.sqlite3"
        app.DB_PATH = self.db_path
        app.initialize()

    def tearDown(self):
        app.DB_PATH = self.previous
        self.temp.cleanup()

    def orders(self, event_id=None):
        if event_id is None:
            return count(self.db_path, "SELECT COUNT(*) FROM orders")
        return count(self.db_path, "SELECT COUNT(*) FROM orders WHERE event_id = ?", event_id)

    def markers(self, event_id):
        return count(self.db_path, "SELECT COUNT(*) FROM processed_events WHERE event_id = ?", event_id)


class Idempotency(TempDatabase):
    def test_repeated_delivery_returns_existing_order(self):
        first = app.process_event(event("evt_1001"))
        self.assertTrue(first["created"])
        for _ in range(4):
            again = app.process_event(event("evt_1001"))
            self.assertEqual(again, {"order_id": first["order_id"], "created": False})
        self.assertEqual(self.orders("evt_1001"), 1)
        self.assertEqual(app.state()["summary"]["extra_orders"], 0)

    def test_different_event_still_creates_new_order(self):
        a = app.process_event(event("evt_1001"))
        b = app.process_event(event("evt_1002"))
        self.assertTrue(a["created"] and b["created"])
        self.assertNotEqual(a["order_id"], b["order_id"])
        self.assertEqual(app.process_event(event("evt_1002"))["order_id"], b["order_id"])
        self.assertEqual(self.orders(), 2)

    def test_dedup_state_survives_reinitialize_and_new_connections(self):
        first = app.process_event(event("evt_1003"))
        app.initialize()
        self.assertEqual(app.process_event(event("evt_1003")),
                         {"order_id": first["order_id"], "created": False})
        self.assertEqual(self.orders(), 1)

    def test_database_rejects_second_marker_for_same_event(self):
        order_id = app.process_event(event("evt_1001"))["order_id"]
        db = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO processed_events (event_id, order_id) VALUES (?, ?)",
                           ("evt_1001", order_id + 1))
        finally:
            db.close()

    def test_failure_before_commit_leaves_no_marker_or_order_then_retry_succeeds(self):
        with self.assertRaises(app.SimulatedFailure):
            app.process_event(event("evt_1004"), fail_before_commit=True)
        self.assertEqual(self.orders("evt_1004"), 0)
        self.assertEqual(self.markers("evt_1004"), 0)
        retry = app.process_event(event("evt_1004"))
        self.assertTrue(retry["created"])
        self.assertEqual(self.orders("evt_1004"), 1)
        self.assertEqual(self.markers("evt_1004"), 1)
        self.assertFalse(app.process_event(event("evt_1004"))["created"])
        self.assertEqual(self.orders("evt_1004"), 1)

    def test_concurrent_processes_create_exactly_one_order(self):
        ctx = multiprocessing.get_context("spawn")
        n = 10
        barrier, results = ctx.Barrier(n), ctx.Queue()
        payload = event("evt_1002")
        procs = [ctx.Process(target=deliver_in_process,
                             args=(str(self.db_path), payload, barrier, results))
                 for _ in range(n)]
        for p in procs:
            p.start()
        outcomes = [results.get(timeout=60) for _ in range(n)]
        for p in procs:
            p.join(timeout=30)
            self.assertEqual(p.exitcode, 0)
        errors = [o for kind, o in outcomes if kind != "ok"]
        self.assertEqual(errors, [])
        results_ok = [o for _, o in outcomes]
        self.assertEqual(sum(r["created"] for r in results_ok), 1)
        self.assertEqual(len({r["order_id"] for r in results_ok}), 1)
        self.assertEqual(self.orders("evt_1002"), 1)
        self.assertEqual(self.markers("evt_1002"), 1)

    def test_concurrent_threads_create_exactly_one_order(self):
        n = 10
        barrier = threading.Barrier(n)
        def deliver(_):
            barrier.wait(timeout=15)
            return app.process_event(event("evt_1003"))
        with ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(deliver, range(n)))
        self.assertEqual(sum(r["created"] for r in results), 1)
        self.assertEqual(len({r["order_id"] for r in results}), 1)
        self.assertEqual(self.orders("evt_1003"), 1)


class LegacyDatabaseMigration(unittest.TestCase):
    def test_existing_duplicate_orders_are_marked_processed_without_new_orders(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "orders.sqlite3"
            db = sqlite3.connect(path)
            db.executescript("""
                CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
                    order_reference TEXT NOT NULL, customer TEXT NOT NULL, product TEXT NOT NULL,
                    total_cents INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT 'x');
                INSERT INTO orders (event_id, order_reference, customer, product, total_cents)
                VALUES ('evt_1001','ORD-2048','Avery Chen','Mechanical keyboard',12900),
                       ('evt_1001','ORD-2048','Avery Chen','Mechanical keyboard',12900);
            """)
            db.close()
            previous, app.DB_PATH = app.DB_PATH, path
            try:
                app.initialize()
                app.initialize()
                self.assertEqual(app.process_event(event("evt_1001")),
                                 {"order_id": 1, "created": False})
                self.assertEqual(count(path, "SELECT COUNT(*) FROM orders"), 2)
                self.assertTrue(app.process_event(event("evt_1002"))["created"])
            finally:
                app.DB_PATH = previous


class HttpAcrossRestart(unittest.TestCase):
    """Runs the real server as a subprocess on a temporary database and free port."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "orders.sqlite3"
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.proc = None

    def tearDown(self):
        self.stop()
        self.temp.cleanup()

    def start(self):
        env = {**os.environ, "ORDERDESK_DB": str(self.db_path)}
        self.proc = subprocess.Popen([sys.executable, str(ROOT / "app.py"), "--port", str(self.port)],
                                     env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if self.call("GET", "/healthz")[1]["pid"] == self.proc.pid:
                    return
            except (URLError, ConnectionError):
                time.sleep(0.1)
        self.fail("server did not start")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=10)

    def call(self, method, path, body=None, headers=None):
        req = Request(f"http://127.0.0.1:{self.port}{path}", method=method,
                      data=None if body is None else json.dumps(body).encode(),
                      headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urlopen(req, timeout=40) as r:
                return r.status, json.load(r)
        except HTTPError as r:
            with r:
                return r.code, json.load(r)

    def test_json_contract_restart_concurrency_and_retry(self):
        self.start()
        status, body = self.call("POST", "/webhooks/orders", event("evt_1001"))
        self.assertEqual(status, 201)
        self.assertEqual(set(body), {"event_id", "order_id", "created"})
        self.assertEqual((body["event_id"], body["created"]), ("evt_1001", True))
        original = body["order_id"]

        self.stop()
        self.start()
        for _ in range(4):
            self.assertEqual(self.call("POST", "/webhooks/orders", event("evt_1001")),
                             (200, {"event_id": "evt_1001", "order_id": original, "created": False}))

        barrier = threading.Barrier(10)
        def deliver(_):
            barrier.wait(timeout=15)
            return self.call("POST", "/webhooks/orders", event("evt_1002"))
        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(deliver, range(10)))
        self.assertEqual(sorted(s for s, _ in responses), [200] * 9 + [201])
        self.assertEqual(len({b["order_id"] for _, b in responses}), 1)

        status, body = self.call("POST", "/webhooks/orders", event("evt_1004"),
                                 {"X-Demo-Fail-Before-Commit": "1"})
        self.assertEqual(status, 503)
        self.assertIn("error", body)
        self.assertEqual(self.call("POST", "/webhooks/orders", event("evt_1004"))[0], 201)

        summary = self.call("GET", "/api/state")[1]["summary"]
        self.assertEqual(summary["orders"], 3)
        self.assertEqual(summary["extra_orders"], 0)
        self.assertEqual(summary["deliveries"], 1 + 4 + 10 + 2)


if __name__ == "__main__":
    unittest.main()
