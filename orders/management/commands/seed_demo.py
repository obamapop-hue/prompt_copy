from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from orders.models import Cafe, Menu, Profile


class Command(BaseCommand):
    help = "Create labeled demo data and local test accounts with generated passwords."

    def handle(self, *args, **opts):
        if not settings.DEBUG or not settings.DEMO_MODE:
            raise CommandError("Requires DEBUG=1 and DEMO_MODE=1")
        import secrets, json, os

        target = settings.LOCAL / "demo-accounts.json"
        if target.exists():
            self.stdout.write("Existing demo accounts preserved.")
            return
        credentials = {}
        with transaction.atomic():
            c = Cafe.objects.create(
                name="시연 · 모퉁이 커피",
                description="함께 주문하고, 가볍게 픽업하세요. 실제 제휴 매장이 아닌 시연 데이터입니다.",
                location="시연 주소 · 서울 성동구 커피길 12",
                demo=True,
            )
            options = [
                {"id": "ice", "name": "ICE", "price": 0, "group": "온도"},
                {"id": "hot", "name": "HOT", "price": 0, "group": "온도"},
                {"id": "shot", "name": "샷 추가", "price": 500},
            ]
            for name, price, desc in [
                ("아메리카노", 3500, "고소하고 깔끔한 오늘의 한 잔"),
                ("카페라떼", 4500, "부드러운 우유와 에스프레소"),
                ("바닐라 라떼", 5000, "기분 좋은 달콤함"),
                ("콜드브루", 4500, "천천히 내려 깊어진 풍미"),
                ("말차 라떼", 5500, "진한 말차와 부드러운 우유"),
                ("레몬 에이드", 5500, "산뜻하게 채우는 오후"),
            ]:
                Menu.objects.create(
                    cafe=c, name=name, price=price, description=desc, options=options
                )
            for role in ["organizer", "seller", "admin"]:
                password = secrets.token_urlsafe(24)
                u = User.objects.create_user(username="demo-" + role, password=password)
                Profile.objects.create(
                    user=u,
                    role=role,
                    cafe=c if role == "seller" else None,
                    nickname="시연총무" if role == "organizer" else "",
                    nickname_key="시연총무" if role == "organizer" else None,
                )
                credentials[role] = {"username": u.username, "password": password}
            # Account credentials remain in an ignored, owner-only local file.
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(credentials, f)
        self.stdout.write(
            "Demo ready. Local credentials saved to .local/demo-accounts.json (do not commit or log)."
        )
