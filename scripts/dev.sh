#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .local/runtime.env ]]; then
  echo 'Run scripts/install.sh first.' >&2; exit 1
fi
source .local/runtime.env
exec .venv/bin/python manage.py runserver 127.0.0.1:8001
