# OrderDesk, the recorded working result

This is the exact application fix and regression suite produced in the recorded
Coder Agents session. The original deliberately buggy app is in `../starter/`.
All customer names and orders are fictional. No commerce service is contacted.

Requires Python 3.15.2 to match the recording. No third-party Python packages.

```sh
python3 demo.py start
python3 -m unittest discover -s tests -v
python3 demo.py reset
python3 demo.py send --event evt_1001 --count 5
```

Open http://127.0.0.1:8000, or the OrderDesk app link inside Coder.
Read the repository README for the complete replay and expected results.
`python3 demo.py stop` stops this app without removing its database.

HTTP contract:
- POST /webhooks/orders accepts event_id, order_reference, customer, product, total_cents.
- A new event returns HTTP 201, its order_id, and created:true.
- A repeated event returns HTTP 200, the existing order_id, and created:false.
- X-Demo-Fail-Before-Commit: 1 raises a simulated exception and returns HTTP 503.
- GET /api/state reads actual orders, delivery history, and counts.
- GET /healthz includes the actual app process ID.

The SQLite database in .data/orders.sqlite3 persists across process restarts.
The event marker and order share a transaction. BEGIN IMMEDIATE serializes
writers; processed_events.event_id is a primary key. Existing duplicate orders
are preserved during migration. Deduplication uses event_id only, and does not
compare changed payloads. The delivery log is written separately.

This is a local, single-machine demo, without authentication, signatures,
payments, or production hardening. The failure hook demonstrates exception
rollback, not every crash or power-loss scenario.
