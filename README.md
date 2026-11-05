# OrderDesk: fix duplicate orders with Coder Agents

Follow along with Lena's Coder demo: send one webhook five times, reproduce five
orders, then use Coder Agents to fix the handler so only one order is saved.

- `starter/`: the app with the duplicate-order bug.
- `app/`: the working fix and regression tests.
- `prompts/`: the task to give Coder Agents.
- `coder/` and `scripts/`: the local Coder setup and headless launcher.

## Run the working app

Install Git and Python (the demo uses Python 3.15.2). No pip packages are needed.

```sh
git clone https://github.com/LenaDemo/coder-webhook-demo.git
cd coder-webhook-demo/app
python3 -m unittest discover -s tests -v
python3 demo.py start
```

Open http://127.0.0.1:8000. The app stores its SQLite database in `.data/`.
To try the original bug without Coder, stop the app, then run the same commands
from `starter/` instead.

## Follow along in Coder

Also install Docker Desktop with Compose and the Coder 2.39.0 CLI. Have an
Anthropic API key ready. From the repository root:

```sh
python3 scripts/setup.py
python3 scripts/show-login.py
```

Sign in at http://localhost:3000 using the displayed local login. Add Anthropic
under **Admin settings > AI > Providers**, then select a default model under
**AI > Models**. The video uses Claude Opus 5.5; use a model available to your
account. Keep credentials private. Setup saves local access files in the
ignored `.state/` directory.

Open the `orderdesk` workspace and its **OrderDesk** app. Send `evt_1001` five
times: the starter should show 5 deliveries, 5 orders, and 4 extras. The
**VS Code Web** app opens the source and workspace terminal.

In your computer's terminal, from the repository root, review and submit the task:

```sh
cat prompts/fix-duplicate-orders.txt
python3 scripts/headless.py run
```

Open the review URL printed by the helper. After the agent finishes, inspect its
changes in VS Code Web and run this in the workspace terminal:

```sh
cd /home/coder/orderdesk
python3 -m unittest discover -s tests -v
```

The agent's output may differ. Compare it with `app/` and verify the behavior below.

## Replay the checks

Run these from `app/`, or `/home/coder/orderdesk` in the fixed Coder workspace.
Reset clears demo data while keeping the code changes.

```sh
python3 demo.py reset
python3 demo.py send --event evt_1001 --count 5
curl -s http://127.0.0.1:8000/healthz
python3 demo.py restart
curl -s http://127.0.0.1:8000/healthz
python3 demo.py send --event evt_1001 --count 1
python3 demo.py send --event evt_1002 --count 10 --concurrent
python3 demo.py send --event evt_1003 --count 1
python3 demo.py send --event evt_1004 --count 1 --fail-before-commit
python3 demo.py send --event evt_1004 --count 1
python3 demo.py send --event evt_1004 --count 1
```

| Check | Expected responses | Total orders |
| --- | --- | ---: |
| Five copies of evt_1001 | One 201, four 200s | 1 |
| Same event after restart | 200 | 1 |
| Ten concurrent copies of fresh evt_1002 | One 201, nine 200s | 2 |
| New evt_1003 | 201 | 3 |
| evt_1004 fails before commit | 503 | 3 |
| Retry evt_1004 | 201 | 4 |
| Repeat evt_1004 | 200 | 4 |

The final dashboard should show **20 deliveries, 4 events, 4 orders, 0 extras**.
The health endpoint's process ID should change after restart.

## Stop

Run `python3 demo.py stop` in the app folder. To stop the local Coder setup,
run `bash scripts/stop-infrastructure.sh` from the repository root. Saved data
is retained.

This is a local learning demo with fictional orders, not a production webhook
service. It uses SQLite on one machine, has no webhook signature validation,
and tests a controlled failure before commit rather than every crash scenario.
Coder runs locally; model inference uses your configured provider.
