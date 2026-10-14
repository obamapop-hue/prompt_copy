from getpass import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from orders.models import Profile


class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument("username")

    def handle(self, *args, **opts):
        if Profile.objects.filter(role="admin").exists():
            raise CommandError(
                "An operator already exists. Use documented password reset procedure."
            )
        password = getpass("운영자 비밀번호: ")
        u = User(username=opts["username"])
        validate_password(password, u)
        with transaction.atomic():
            u.set_password(password)
            u.save()
            Profile.objects.create(user=u, role="admin")
        self.stdout.write("운영자 생성 완료")
