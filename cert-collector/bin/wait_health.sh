#!/usr/bin/env bash
set -euo pipefail
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8080/api/health >/dev/null; then
    echo "✅ API healthy"
    curl -sS http://127.0.0.1:8080/api/health | cat
    echo
    exit 0
  fi
  sleep 0.2
done
echo "❌ API not healthy after waiting"
exit 1
