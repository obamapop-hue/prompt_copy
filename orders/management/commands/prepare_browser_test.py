import json, os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.test import Client


class Command(BaseCommand):
    help = "Create a local test session for browser acceptance checks; does not test Kakao OAuth."

    def handle(self, *args, **opts):
        if not settings.DEBUG or not settings.DEMO_MODE:
            raise CommandError("Only allowed in DEBUG demo mode")
        c = Client()
        c.force_login(User.objects.get(username="demo-organizer"))
        fd = os.open(
            settings.LOCAL / "browser-session.json",
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(fd, "w") as f:
            json.dump({"sessionid": c.cookies["sessionid"].value}, f)
        self.stdout.write(
            "Local browser test session prepared. Kakao OAuth is not tested."
        )
