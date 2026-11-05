# OrderDesk: fix duplicate webhook orders with Coder Agents

The follow-along code for Lena Hall's Coder demo. Deliver the same event five
times: the starter saves five orders. The recorded fix saves one order and
recognizes the other deliveries as duplicates.

## What is included

- `app/`: the working application and all 15 tests from the recording.
- `starter/`: the original deliberately buggy app with its 6 baseline tests.
- `prompts/fix-duplicate-orders.txt`: the exact task given to Coder Agents.
- `coder/`: local control-plane, workspace image, and Terraform template.
- `scripts/`: local provisioning, login display, and headless task submission.
- `.env.example`: environment guidance, with no real credentials.

The app uses Python's standard library, SQLite, and a small browser dashboard.
All orders are fictional. There is no payment provider or commerce integration.

## Clone and run the working result

Install Python 3.15.2 to match the recording, plus Git. No Python packages or
model API key are needed for this path.

```sh
git clone https://github.com/LenaDemo/coder-webhook-demo.git
cd coder-webhook-demo/app
python3 -m unittest discover -s tests -v
python3 demo.py start
```

Open http://127.0.0.1:8000. Stop any other OrderDesk instance on port 8000 first.
The dashboard sender and the CLI call the same webhook endpoint.

## Replay the recorded checks

Run these commands from `app/`, or `/home/coder/orderdesk` after the agent has
fixed the starter in a Coder workspace. Reset removes demo rows and delivery
history, while keeping code and schema. The tests use temporary databases.

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

| Check | HTTP responses | Cumulative deliveries | Orders | Extra orders |
| --- | --- | ---: | ---: | ---: |
| Five copies of evt_1001 | 1 x 201, 4 x 200 | 5 | 1 | 0 |
| Same event after restart | 200 | 6 | 1 | 0 |
| Ten concurrent copies of fresh evt_1002 | 1 x 201, 9 x 200 | 16 | 2 | 0 |
| Distinct evt_1003 | 201 | 17 | 3 | 0 |
| evt_1004 fails before commit | 503 | 18 | 3 | 0 |
| Retry evt_1004 | 201 | 19 | 4 | 0 |
| Repeat evt_1004 | 200 | 20 | 4 | 0 |

The process IDs change on restart; your IDs and timings will differ. The final
dashboard shows 20 deliveries, 4 distinct event IDs, 4 orders, and 0 extra orders.

```sh
python3 demo.py status
python3 demo.py stop
```

## Follow the Coder Agents workflow from the buggy starter

This local setup was recorded on macOS with Docker Desktop. It uses Coder
2.39.0, Python 3.15.2, code-server 4.144.0, PostgreSQL 17, and the pinned
Terraform providers in `coder/template/main.tf`. Install a matching Coder CLI,
Docker Desktop with Compose, Git, and Python before provisioning.

You also need an Anthropic account with API access and credits for the agent
run. The recorded default model was Claude Opus 5.5. Model access and pricing
depend on your provider account. The helper uses the available default model
you configure in Coder, and agent output may differ from this recorded result.

From the repository root:

```sh
python3 scripts/setup.py
python3 scripts/show-login.py
```

Setup downloads official image/release artifacts, builds local images, starts
Coder at http://localhost:3000, and prepares the `orderdesk` workspace. Its
image seeds `/home/coder/orderdesk` from `starter/`, so the agent has a real bug
to fix. It does not submit an AI task. Generated login details and tokens stay
in the ignored `.state/` folder. View the login privately, away from recording.

Sign in, then open Admin settings > AI > Providers and configure Anthropic.
Under AI > Models, enable an available model and make it the default. Enter the
key in Coder, never in the repo, prompt, or recorded terminal. Provider model
inference is external; self-hosting Coder does not make inference local.

Open the workspace's OrderDesk app and send the same event 5 times. The starter
shows 5 deliveries, 1 distinct event, 5 orders, and 4 extra orders. Open VS Code
Web to review the unconditional INSERT in app.py. Then, from a host terminal
in the repository root:

```sh
cat prompts/fix-duplicate-orders.txt
python3 scripts/headless.py preflight
python3 scripts/headless.py run
python3 scripts/headless.py status --wait
```

The helper submits the prompt through Coder's Chats API and prints the review
URL. Follow that URL to inspect the agent's changes, commands, tests, and final
response. Coder's native agent loop runs in its control plane; tools execute
inside the prepared workspace. This is headless submission with browser review.

In the workspace terminal, review the diff and run the tests yourself:

```sh
cd /home/coder/orderdesk
git diff
python3 -m unittest discover -s tests -v
```

The recorded agent added 9 tests, giving 15 passing tests. Its migration kept
the original duplicate rows, so reset the demo data before comparing the fixed
result. Follow the replay sequence above. The checked-in `app/` is the exact
known working result if you want to compare your agent's implementation.

The generated API token expires after 7 days. For a later session, use a fresh
Coder token through CODER_SESSION_TOKEN or replace .state/headless-token
privately with file permissions 600. Never commit it. To repeat from scratch,
use a fresh workspace/home volume; restarting an existing workspace preserves
its code and database. `git restore app.py` in the demo workspace restores the
buggy tracked baseline but discards local changes to that file.

## Boundaries and cleanup

This setup is for a local demo, not a production deployment. Coder binds to
localhost. Its control plane has the Docker socket to provision workspaces;
the workspace container does not. The template's apps are owner-only. This
does not demonstrate network isolation, egress filtering, or premium policy
features. Do not expose this setup as a public service.

The app deduplicates by event_id. It does not validate webhook signatures or
reconcile a changed payload under an existing ID. SQLite serializes writers
on one machine; this is not a distributed database design or throughput test.
The regression suite exercises 10 separate processes and 10 threads. The live
concurrency check sends 10 requests together. The failure hook checks exception
rollback before commit, not arbitrary crashes, power loss, or real payments.

`python3 demo.py stop` stops only the app. From the repository root,
`bash scripts/stop-infrastructure.sh` stops the Coder demo containers and retains
their persistent volumes. Do not delete volumes unless you intend to discard
the saved demo state. The `.state/` directory is needed to reuse local access.

Official references: [Coder Agents](https://coder.com/docs/ai-coder/agents),
[getting started](https://coder.com/docs/ai-coder/agents/getting-started), and
[Agent Relay](https://coder.com/docs/ai-coder/agent-relay).
