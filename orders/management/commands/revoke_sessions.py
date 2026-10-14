from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session


class Command(BaseCommand):
    help = "Revoke all Django sessions for one account; does not reveal session keys."

    def add_arguments(self, p):
        p.add_argument("username")

    def handle(self, *args, **opts):
        user = User.objects.get(username=opts["username"])
        count = 0
        for session in Session.objects.iterator():
            if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
                session.delete()
                count += 1
        self.stdout.write(f"Revoked {count} sessions.")
