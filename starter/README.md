# OrderDesk
A local, fictional order dashboard for a Coder Agents demo.

The starting version deliberately creates one order for every webhook delivery.
Repeated event IDs therefore create duplicate orders. Coder Agents will make
the fix during the recorded demo.

Requires Python 3.15.2 in the prepared workspace. No third-party Python packages.

```sh
python3 demo.py start
python3 demo.py send --event evt_1001 --count 5
python3 demo.py restart
python3 demo.py status
python3 -m unittest discover -s tests -v
```

Open the OrderDesk app in Coder, or http://127.0.0.1:8000 when running directly.
Use `python3 demo.py reset` to clear data while preserving code and schema.
Data is in .data/orders.sqlite3 and persists across process restarts.

HTTP contract:
- POST /webhooks/orders accepts event_id, order_reference, customer, product, total_cents.
- A new order returns 201 with order_id and created:true.
- A safely recognized duplicate should return 200 with the original order_id and created:false.
- X-Demo-Fail-Before-Commit: 1 triggers a 503 exception at the transaction boundary.
- GET /api/state reads actual rows, delivery history, and counts.
- GET /healthz includes the actual process PID.

No commerce integration, payments, webhook signatures, or production deployment.
The local failure hook tests exception rollback. It does not prove all crash or
power-loss scenarios. SQLite is the demo's single-machine storage boundary.
