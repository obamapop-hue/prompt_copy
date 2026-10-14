from pathlib import Path
import os, sqlite3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a verified SQLite backup without copying a live database file."

    def add_arguments(self, p):
        p.add_argument("destination")

    def handle(self, *args, **opts):
        dest = Path(opts["destination"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            raise CommandError("Destination exists; refusing to overwrite.")
        fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with sqlite3.connect(
                settings.DATABASES["default"]["NAME"]
            ) as source, sqlite3.connect(dest) as target:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise CommandError("Backup integrity check failed")
                if target.execute("PRAGMA foreign_key_check").fetchall():
                    raise CommandError("Backup foreign key check failed")
            self.stdout.write(
                "Backup completed; integrity and foreign keys checked. Keep this private."
            )
        except Exception:
            dest.unlink(missing_ok=True)
            raise
