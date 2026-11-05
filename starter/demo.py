"""Process control and real HTTP replay for the local OrderDesk demo."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / ".data"
PID = DATA / "server.pid"
URL = os.environ.get("ORDERDESK_URL", "http://127.0.0.1:8000")
FIXTURES = {
    "evt_1001": ("ORD-2048", "Avery Chen", "Mechanical keyboard", 12900),
    "evt_1002": ("ORD-2049", "Morgan Lee", "Studio headphones", 8900),
    "evt_1003": ("ORD-2050", "Jordan Ellis", "USB-C dock", 14900),
    "evt_1004": ("ORD-2051", "Sam Rivera", "Desk light", 5900),
}

def event(key):
    ref, customer, product, amount = FIXTURES[key]
    return dict(event_id=key, order_reference=ref, customer=customer, product=product, total_cents=amount)

def request(path, body=None, headers=None):
    req = Request(URL + path, data=None if body is None else json.dumps(body).encode(),
                  headers={"Content-Type":"application/json", **(headers or {})})
    try:
        with urlopen(req, timeout=40) as response:
            return response.status, json.load(response)
    except HTTPError as response:
        return response.code, json.load(response)

def start():
    DATA.mkdir(exist_ok=True)
    try:
        status, health = request("/healthz")
        if status == 200:
            if PID.exists() and int(PID.read_text()) == health["pid"]:
                print("OrderDesk is already running.")
                return
            raise SystemExit("Port already serves another OrderDesk process. Refusing to replace it.")
    except URLError:
        pass
    with (DATA / "server.log").open("ab") as log:
        proc = subprocess.Popen([sys.executable, str(ROOT / "app.py")], cwd=ROOT,
                                stdout=log, stderr=log, start_new_session=True)
    PID.write_text(str(proc.pid))
    for _ in range(100):
        if proc.poll() is not None:
            raise SystemExit("App failed to start; inspect .data/server.log")
        try:
            code, health = request("/healthz")
            if code == 200 and health["pid"] == proc.pid:
                print("OrderDesk is running at " + URL)
                return
        except URLError:
            pass
        time.sleep(.1)
    raise SystemExit("Timed out waiting for OrderDesk.")

def stop():
    if not PID.exists():
        print("No managed OrderDesk process.")
        return
    pid = int(PID.read_text())
    try:
        status, health = request("/healthz")
        if status != 200 or health.get("pid") != pid:
            raise SystemExit("PID mismatch. Refusing to stop an unrelated process.")
    except URLError:
        PID.unlink()
        print("OrderDesk is already stopped.")
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        try:
            request("/healthz")
        except (URLError, ConnectionError):
            PID.unlink(missing_ok=True)
            print("OrderDesk stopped; database kept.")
            return
        time.sleep(.1)
    raise SystemExit("App is still responding; inspect before continuing.")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "stop", "restart", "status", "reset"):
        subs.add_parser(name)
    send = subs.add_parser("send")
    send.add_argument("--event", choices=FIXTURES, default="evt_1001")
    send.add_argument("--count", type=int, default=5)
    send.add_argument("--concurrent", action="store_true")
    send.add_argument("--fail-before-commit", action="store_true")
    args = parser.parse_args()
    if args.command == "start": return start()
    if args.command == "stop": return stop()
    if args.command == "restart":
        stop()
        return start()
    if args.command == "reset":
        code, result = request("/api/demo/reset", {"confirm":"reset-demo-data"})
        if code != 200: raise SystemExit(result)
        print("Demo data cleared. Schema and code changes kept.")
    if args.command == "send":
        if not 1 <= args.count <= 100:
            parser.error("--count must be between 1 and 100")
        barrier = threading.Barrier(args.count) if args.concurrent else None
        def deliver(_):
            if barrier: barrier.wait(timeout=15)
            return request("/webhooks/orders", event(args.event),
                           {"X-Demo-Fail-Before-Commit":"1"} if args.fail_before_commit else {})
        if args.concurrent:
            with ThreadPoolExecutor(max_workers=args.count) as pool:
                responses = list(pool.map(deliver, range(args.count)))
        else:
            responses = [deliver(i) for i in range(args.count)]
        print(f"Event: {args.event}; requests: {args.count}; concurrent: {args.concurrent}")
        for status, count in sorted(Counter(r[0] for r in responses).items()):
            print(f"HTTP {status}: {count}")
    code, result = request("/api/state")
    if code != 200: raise SystemExit(result)
    print(json.dumps(result["summary"], indent=2))
    if args.command == "send" and any(s >= 400 for s, _ in responses):
        raise SystemExit(1)

if __name__ == "__main__":
    main()
