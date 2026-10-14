#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .local/runtime.env
exec .venv/bin/python manage.py expire_orders
