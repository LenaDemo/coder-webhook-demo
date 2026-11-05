"""Use off camera only. Shows this demo's generated local login, never API keys."""
import json
from pathlib import Path
login=json.loads((Path(__file__).resolve().parents[1]/".state/admin-login.json").read_text())
print("Coder: http://localhost:3000")
print("Email:",login["email"])
print("Password:",login["password"])
