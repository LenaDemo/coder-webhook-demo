"""A deliberately incomplete local webhook consumer. All orders are fictional."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ORDERDESK_DB", ROOT / ".data/orders.sqlite3"))

class SimulatedFailure(Exception):
    pass

@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        with db:
            yield db
    finally:
        db.close()

def initialize():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                order_reference TEXT NOT NULL,
                customer TEXT NOT NULL,
                product TEXT NOT NULL,
                total_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                status INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            -- One row per successfully processed event. The PRIMARY KEY is the
            -- database-enforced idempotency guarantee across threads and processes.
            CREATE TABLE IF NOT EXISTS processed_events (
                event_id TEXT PRIMARY KEY,
                order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
                processed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            -- Databases created before this table existed: treat the earliest
            -- existing order for each event as the processed one.
            INSERT OR IGNORE INTO processed_events (event_id, order_id)
                SELECT event_id, MIN(id) FROM orders GROUP BY event_id;
        """)

def validate_event(event):
    if not isinstance(event, dict):
        raise ValueError("Expected a JSON object")
    for name in ("event_id", "order_reference", "customer", "product"):
        value = event.get(name)
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            raise ValueError(f"{name} must be a non-empty string of at most 120 characters")
    if type(event.get("total_cents")) is not int or not 0 <= event["total_cents"] <= 100000000:
        raise ValueError("total_cents must be a non-negative integer")

def before_commit(fail_before_commit):
    """Keep this fault hook after ALL event/order writes, inside their transaction.
    This tests exception rollback, not a power failure or a real payment.
    """
    if fail_before_commit:
        raise SimulatedFailure("Simulated failure before commit; retry this event")

def process_event(event, fail_before_commit=False):
    """Create one order per event_id; repeated deliveries return the original order.

    BEGIN IMMEDIATE takes SQLite's write lock before the lookup, so concurrent
    deliveries (from any thread or process) serialize and later ones see the
    committed marker. The processed_events PRIMARY KEY backs this up: a second
    marker for the same event can never be committed. The marker and the order
    share one transaction, so a failure rolls back both.
    """
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT order_id FROM processed_events WHERE event_id = ?",
                              (event["event_id"],)).fetchone()
        if existing is not None:
            return {"order_id": existing["order_id"], "created": False}
        order_id = db.execute(
            "INSERT INTO orders (event_id, order_reference, customer, product, total_cents) "
            "VALUES (?, ?, ?, ?, ?)",
            (event["event_id"], event["order_reference"], event["customer"],
             event["product"], event["total_cents"]),
        ).lastrowid
        db.execute("INSERT INTO processed_events (event_id, order_id) VALUES (?, ?)",
                   (event["event_id"], order_id))
        before_commit(fail_before_commit)
    return {"order_id": order_id, "created": True}

def record_delivery(event_id, status, outcome):
    with connect() as db:
        db.execute("INSERT INTO deliveries(event_id,status,outcome) VALUES (?,?,?)",
                   (event_id, status, outcome))

def state():
    with connect() as db:
        orders = [dict(row) for row in db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 100")]
        deliveries = [dict(row) for row in db.execute("SELECT * FROM deliveries ORDER BY id DESC LIMIT 100")]
        total = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        unique_orders = db.execute("SELECT COUNT(DISTINCT event_id) FROM orders").fetchone()[0]
        attempts = db.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
        unique_events = db.execute("SELECT COUNT(DISTINCT event_id) FROM deliveries").fetchone()[0]
    return {"orders": orders, "deliveries": deliveries, "summary": {
        "orders": total, "deliveries": attempts, "unique_events": unique_events,
        "extra_orders": total - unique_orders}}

def reset_data():
    """Only for this dedicated demo DB, with no requests in flight. Keep schema/code."""
    with connect() as db:
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("BEGIN IMMEDIATE")
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            db.execute('DELETE FROM "' + table.replace('"', '""') + '"')
        db.execute("DELETE FROM sqlite_sequence")

class Handler(BaseHTTPRequestHandler):
    server_version = "OrderDesk"
    def log_message(self, format, *args):
        pass
    def respond(self, status, body, content_type="application/json"):
        if content_type == "application/json":
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            return self.respond(200, {"status": "ok", "pid": os.getpid()})
        if path == "/api/state":
            return self.respond(200, state())
        files = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/style.css": ("style.css", "text/css; charset=utf-8"),
                 "/app.js": ("app.js", "text/javascript; charset=utf-8")}
        if path in files:
            filename, content_type = files[path]
            return self.respond(200, (ROOT / "static" / filename).read_bytes(), content_type)
        self.respond(404, {"error": "Not found"})
    def do_POST(self):
        path = urlsplit(self.path).path
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.respond(415, {"error": "Content-Type must be application/json"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("Request must contain 1 to 16384 bytes")
            event = json.loads(self.rfile.read(length))
            if path == "/api/demo/reset":
                if event != {"confirm": "reset-demo-data"}:
                    raise ValueError("Explicit reset confirmation is required")
                reset_data()
                return self.respond(200, {"reset": True})
            if path != "/webhooks/orders":
                return self.respond(404, {"error": "Not found"})
            validate_event(event)
        except (ValueError, UnicodeError) as exc:
            return self.respond(400, {"error": str(exc)})
        try:
            result = process_event(event, self.headers.get("X-Demo-Fail-Before-Commit") == "1")
            status = 201 if result["created"] else 200
            outcome = "created" if result["created"] else "duplicate"
        except SimulatedFailure as exc:
            status, outcome, result = 503, "rolled back", {"error": str(exc)}
        except sqlite3.Error:
            status, outcome, result = 500, "database error", {"error": "Database operation failed"}
        record_delivery(event["event_id"], status, outcome)
        self.respond(status, {"event_id": event["event_id"], **result})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    initialize()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"OrderDesk listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
