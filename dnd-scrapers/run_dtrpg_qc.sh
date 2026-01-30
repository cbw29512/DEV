#!/usr/bin/env bash
set -euo pipefail

cd "/home/home/dev/dnd-scrapers"

# load optional creds
if [[ -f "/home/home/.config/dtrpg-qc/env" ]]; then
  # shellcheck disable=SC1090
  source "/home/home/.config/dtrpg-qc/env"
fi

# ensure venv exists
if [[ ! -x "/home/home/dev/dnd-scrapers/venv/bin/python3" ]]; then
  echo "❌ venv python not found at: /home/home/dev/dnd-scrapers/venv/bin/python3"
  echo "Create venv first: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

exec "/home/home/dev/dnd-scrapers/venv/bin/python3" dtrpg_qc.py
