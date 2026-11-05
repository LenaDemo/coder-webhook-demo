#!/bin/bash
set -euo pipefail
base="$(cd "$(dirname "$0")/.." && pwd)"
bash "$base/scripts/coder-cli" stop orderdesk --yes
docker compose --env-file "$base/.state/compose.env" -f "$base/coder/compose.yaml" stop
# Named volumes and workspace code are preserved.
