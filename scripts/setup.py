"""Provision only the local Coder infrastructure. Does not run an AI task."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"
URL = "http://localhost:3000"

def private_write(name, text):
    path = STATE / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)

def api(path, body=None, token=None):
    headers = {"Content-Type":"application/json"}
    if token: headers["Coder-Session-Token"] = token
    request = Request(URL + "/api/v2" + path,
                      data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as response:
        return response.code, json.load(response)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-image-build", action="store_true")
    parser.add_argument("--infrastructure-only", action="store_true")
    args = parser.parse_args()
    STATE.mkdir(mode=0o700, exist_ok=True)
    os.chmod(STATE, 0o700)
    if not (STATE / "compose.env").exists():
        private_write("compose.env", "CODER_DB_PASSWORD=" + secrets.token_hex(24) + "\n")
    compose = ["docker","compose","--env-file",str(STATE/"compose.env"),
               "-f",str(ROOT/"coder/compose.yaml")]
    if not args.skip_image_build:
        subprocess.run(["docker","build","-t","lena-orderdesk-workspace:2026-11-04",
                        "-f",str(ROOT/"coder/workspace.Dockerfile"),str(ROOT)],check=True)
    image_check = subprocess.run(["docker","image","inspect","lena-coder-control:2.39.0"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if image_check.returncode:
        subprocess.run([sys.executable,str(ROOT/"scripts/build-control.py")],check=True)
    subprocess.run(compose + ["up","-d"],check=True)
    for _ in range(120):
        try:
            code, _ = api("/buildinfo")
            if code == 200: break
        except (URLError, ConnectionError, json.JSONDecodeError):
            pass
        time.sleep(1)
    else: raise SystemExit("Coder did not become ready. Inspect docker compose logs.")
    code, _ = api("/users/first")
    if code == 404:
        if not (STATE/"admin-login.json").exists():
            private_write("admin-login.json", json.dumps({
                "email":"lena@example.test","password":secrets.token_urlsafe(30)+"Aa1!"}))
        login = json.loads((STATE/"admin-login.json").read_text())
        code, result = api("/users/first", {**login,"username":"lena","name":"Lena Demo","trial":False})
        if code != 201: raise SystemExit(f"First-user creation failed: HTTP {code}: {result}")
    elif code != 200:
        raise SystemExit(f"Unexpected first-user status {code}")
    if not (STATE/"admin-login.json").exists():
        raise SystemExit("Existing Coder account detected. Sign in normally; no password was changed.")
    login = json.loads((STATE/"admin-login.json").read_text())
    code, result = api("/users/login",login)
    if code != 201: raise SystemExit(f"Login failed: HTTP {code}")
    token = result["session_token"]
    private_write("admin-token", token)
    if not (STATE/"headless-token").exists():
        key_status, key_result = api("/users/me/keys/tokens", {"token_name":"orderdesk-headless", "lifetime":604800000000000, "scopes":["coder:all"]}, token=token)
        if key_status != 201:
            raise SystemExit(f"Headless token creation failed: HTTP {key_status}")
        private_write("headless-token", key_result["key"])
    environment = {**os.environ,"CODER_URL":URL,"CODER_SESSION_TOKEN":token,
                   "CODER_CONFIG_DIR":str(STATE/"cli")}
    if args.infrastructure_only:
        print("Coder is ready at " + URL + ". No AI task has run.")
        return
    subprocess.run(["coder","templates","push","orderdesk","--directory",str(ROOT/"coder/template"),
                    "--ignore-lockfile","--yes"],env=environment,check=True)
    code, _ = api("/users/me/workspace/orderdesk",token=token)
    if code == 404:
        subprocess.run(["coder","create","orderdesk","--template","orderdesk",
                        "--stop-after","12h","--yes"],env=environment,check=True)
    elif code != 200:
        raise SystemExit(f"Workspace lookup failed: HTTP {code}")
    print("Local Coder and the OrderDesk workspace are prepared. No agent prompt has run.")
    print("Open " + URL + " and configure Anthropic under Admin settings > AI.")

if __name__ == "__main__":
    main()
