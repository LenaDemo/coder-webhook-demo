"""Submit the real fix through Coder's Chats API. Run this DURING recording."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"
URL = os.environ.get("CODER_URL", "http://localhost:3000").rstrip("/")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["preflight","run","status"])
    parser.add_argument("--workspace", default="orderdesk")
    parser.add_argument("--chat")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("CODER_SESSION_TOKEN")
    tokenfile = STATE / "headless-token"
    if not token and tokenfile.exists():
        if tokenfile.stat().st_mode & 0o077:
            raise SystemExit("Restrict .state/headless-token to mode 600 before continuing.")
        token = tokenfile.read_text().strip()
    if not token:
        raise SystemExit("Create a Coder API token and save it privately in .state/headless-token, or set CODER_SESSION_TOKEN.")
    def api(path, body=None):
        req=Request(URL+"/api/v2"+path, headers={"Content-Type":"application/json","Coder-Session-Token":token},
                    data=None if body is None else json.dumps(body).encode())
        try:
            with urlopen(req,timeout=45) as response:
                return json.load(response)
        except HTTPError as response:
            detail=json.load(response)
            raise SystemExit(f"Coder returned HTTP {response.code}: {detail.get('message','Request failed')}")
    if args.command in ("preflight","run"):
        workspace=api("/users/me/workspace/"+args.workspace)
        if workspace["latest_build"]["status"] != "running":
            raise SystemExit("The workspace is not running.")
        print("Coder workspace: "+workspace["name"])
        configuration=api("/organizations/"+workspace["organization_id"]+"/chats/models")
        available={p["id"] for p in configuration.get("providers",[]) if p.get("available")}
        model=next((m for m in configuration.get("models",[]) if m.get("enabled")
                    and m.get("is_default") and m.get("ai_provider_id") in available),None)
        if model is None:
            raise SystemExit("Configure an available default model in Coder before recording.")
        print("Configured model: "+model["display_name"])
        if args.command=="preflight":
            print("API authentication, workspace lookup, and model configuration checks passed. No model was called.")
            return
        prompt=(ROOT/"prompts/fix-duplicate-orders.txt").read_text()
        result=api("/chats",{
            "client_type":"api","content":[{"type":"text","text":prompt}],
            "workspace_id":workspace["id"],"organization_id":workspace["organization_id"],
            "model_config_id":model["id"],
            "title":"Fix duplicate webhook orders"})
        chat=result["id"]
        STATE.mkdir(exist_ok=True)
        (STATE/"last-chat-id").write_text(chat)
        print("Submitted to Coder Agents: "+chat)
        print("Review in Coder: "+URL+"/agents/"+chat)
    else:
        chat=args.chat or (STATE/"last-chat-id").read_text().strip()
    if args.command=="status" or args.wait:
        previous=None
        deadline=time.monotonic()+1800
        while True:
            result=api("/chats/"+chat)
            status=result["status"]
            if status!=previous:
                print("Agent status: "+status,flush=True)
                previous=status
            if status=="error":
                error=result.get("last_error") or {}
                raise SystemExit(error.get("message","Agent failed. Review its chat."))
            if not args.wait or status in ("waiting","requires_action"):
                print("Review the actual response, diff, and tests in Coder before accepting the result.")
                break
            if time.monotonic()>deadline:
                raise SystemExit("Polling stopped after 30 minutes. The task may still be running; inspect Coder.")
            time.sleep(3)

if __name__=="__main__":
    try: main()
    except (URLError,FileNotFoundError) as exc:
        raise SystemExit(str(exc))
