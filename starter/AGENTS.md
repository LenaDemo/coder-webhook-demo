# OrderDesk project
This is a small Python standard-library app with a real SQLite database.
All customers and orders are fictional. Work in /home/coder/orderdesk.

Commands:
- python3 demo.py start
- python3 demo.py restart (preserves the database)
- python3 demo.py status
- python3 demo.py send --event evt_1001 --count 5
- python3 demo.py send --event evt_1002 --count 10 --concurrent
- python3 demo.py reset (clears only demo data, preserves code/schema)
- python3 -m unittest discover -s tests -v

No pip install is needed. The app listens on 127.0.0.1:8000.
Open the OrderDesk workspace app through Coder. Review files in VS Code Web.
The starting handler creates an order for each webhook delivery.
Keep the public JSON contract and demo controls. Do not weaken tests or hard-code fixture IDs.
Keep the before_commit fault hook after all event/order writes and before their shared commit.
Use temporary databases for tests. Never reset the live demo database in automated tests.
Review and report failures honestly. Do not publish or push code.
