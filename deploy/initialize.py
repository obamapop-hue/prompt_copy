"""Prepare the persistent volume, then migrate as the unprivileged app user."""

import os
from pathlib import Path
import subprocess
import sys

if not os.environ.get("DJANGO_SECRET_KEY"):
    raise SystemExit("DJANGO_SECRET_KEY must be set in the hosting secret settings.")
if not os.environ.get("DJANGO_ALLOWED_HOSTS") and not os.environ.get(
    "RENDER_EXTERNAL_HOSTNAME"
):
    raise SystemExit("Set DJANGO_ALLOWED_HOSTS to the public hostname.")
path = Path(os.environ["DATABASE_PATH"]).resolve()
if path.parent != Path("/var/data"):
    raise SystemExit(
        "Production DATABASE_PATH must be a file directly under /var/data."
    )
for directory in [path.parent, Path("/tmp/youngcha"), Path("/app/.local")]:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(directory, 10001, 10001)
    directory.chmod(0o700)
if path.exists():
    os.chown(path, 10001, 10001)
    path.chmod(0o600)
Path(os.environ["WORKER_HEARTBEAT_PATH"]).unlink(missing_ok=True)


def drop_privileges():
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)


subprocess.run(
    [sys.executable, "/app/manage.py", "migrate", "--noinput"],
    check=True,
    preexec_fn=drop_privileges,
)
