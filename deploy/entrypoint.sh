#!/bin/sh
set -eu
export PORT="${PORT:-8000}"
export DATABASE_PATH="${DATABASE_PATH:-/var/data/coffee.sqlite3}"
export WORKER_HEARTBEAT_PATH=/tmp/youngcha/expiry.heartbeat
export REQUIRE_WORKER_HEARTBEAT=1
export DJANGO_DEBUG=0
export DEMO_MODE=0
python /app/deploy/initialize.py
exec supervisord -c /app/deploy/supervisord.conf
