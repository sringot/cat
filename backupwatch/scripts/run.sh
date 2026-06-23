#!/usr/bin/env bash
# Lance BackupWatch une fois. À planifier chaque matin (cron / systemd timer).
set -euo pipefail
cd "$(dirname "$0")/.."

# Active un éventuel environnement virtuel s'il existe.
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec python3 -m backupwatch --source graph "$@"
