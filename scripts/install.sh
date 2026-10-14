#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --requirement requirements.txt
mkdir -p .local
.venv/bin/python - <<'PY'
from pathlib import Path
import os, secrets
p=Path('.local/runtime.env')
if not p.exists():
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as f:
  f.write('export DJANGO_SECRET_KEY='+secrets.token_urlsafe(48)+'\nexport DJANGO_DEBUG=1\nexport DEMO_MODE=1\n')
PY
source .local/runtime.env
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py check
.venv/bin/python manage.py seed_demo
