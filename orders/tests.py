import uuid
import os
import tempfile
import time
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from django.test import TestCase, TransactionTestCase, override_settings, Client
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import connections, IntegrityError, transaction
from django.core.management import call_command
from .models import *
from . import services as s


class HostingHealthTests(TestCase):
    @override_settings(REQUIRE_WORKER_HEARTBEAT=False)
    def test_database_health(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)

    def test_worker_missing_fresh_and_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "worker"
            with override_settings(
                REQUIRE_WORKER_HEARTBEAT=True,
                WORKER_HEARTBEAT_PATH=str(heartbeat),
            ):
                self.assertEqual(self.client.get("/healthz").status_code, 503)
                call_command("expire_orders", once=True)
                self.assertEqual(self.client.get("/healthz").status_code, 200)
                old = time.time() - 30
                os.utime(heartbeat, (old, old))
                response = self.client.get("/healthz")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"status": "unavailable"})


class Fixtures:
    def setUp(self):
        self.cafe = Cafe.objects.create(name="시험 카페", location="서울")
        self.owner = User.objects.create_user("owner", password="Coffee-Test-893!")
        self.other = User.objects.create_user("other", password="Coffee-Test-893!")
        self.seller = User.objects.create_user("seller", password="Coffee-Test-893!")
        self.admin = User.objects.create_user("operator", password="Coffee-Test-893!")
        Profile.objects.create(
            user=self.owner, role="organizer", nickname="총무", nickname_key="총무"
        )
        Profile.objects.create(
            user=self.other,
            role="organizer",
            nickname="다른총무",
            nickname_key="다른총무",
        )
        self.sp = Profile.objects.create(
            user=self.seller, role="seller", cafe=self.cafe
        )
        Profile.objects.create(user=self.admin, role="admin")
        self.menu = Menu.objects.create(
            cafe=self.cafe,
            name="라떼",
            price=4500,
            options=[
                {"id": "ice", "name": "ICE", "price": 0, "group": "온도"},
                {"id": "hot", "name": "HOT", "price": 0, "group": "온도"},
                {"id": "shot", "name": "샷 추가", "price": 500},
            ],
        )
        self.o = Order.objects.get(
            pk=s.create_order(self.owner, {"cafe": self.cafe.pk}, str(uuid.uuid4()))[
                "id"
            ]
        )

    def submit(self, **kw):
        data = {
            "name": "참여자",
            "items": [
                {"menu": self.menu.pk, "options": ["ice", "shot"], "quantity": 2}
            ],
        }
        data.update(kw)
        return s.submit(self.o.token, data, str(uuid.uuid4()))

    def act(self, who, action, **kw):
        self.o.refresh_from_db()
        data = {"action": action, "version": self.o.version}
        data.update(kw)
        return s.change(who, self.o.pk, data, str(uuid.uuid4()))

    def pending(self):
        self.submit()
        self.act(self.owner, "close")
        self.act(self.owner, "send")
        self.o.refresh_from_db()


@override_settings(DEMO_MODE=False, POLICIES_APPROVED=True)
class CoreTests(Fixtures, TestCase):
    def test_first_login_requires_nickname_and_returns_to_original_home(self):
        u = User.objects.create_user("first-login-user")
        Profile.objects.create(user=u, role="organizer")
        c = Client()
        c.force_login(u)
        response = c.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/my/orders?next=%2F")
        self.assertEqual(c.get(response.url).context["return_to"], "/")
        self.assertEqual(
            c.post(
                "/api/nickname", {"nickname": "새총무"}, content_type="application/json"
            ).status_code,
            200,
        )
        self.assertEqual(c.get("/").status_code, 200)
        self.assertEqual(c.get("/login").url, "/")
        # Participant links never gain a required nickname or login step.
        Profile.objects.filter(user=u).update(nickname="", nickname_key=None)
        self.assertEqual(c.get("/join/" + self.o.token).status_code, 200)

    def test_account_information_is_private_and_uses_own_kakao_link(self):
        from allauth.socialaccount.models import SocialAccount

        SocialAccount.objects.create(
            user=self.owner,
            provider="kakao",
            uid="test-owner-id",
            extra_data={
                "kakao_account": {
                    "email": "owner@example.test",
                    "is_email_verified": True,
                    "profile": {"nickname": "카카오이름"},
                }
            },
        )
        SocialAccount.objects.create(
            user=self.other,
            provider="kakao",
            uid="test-other-id",
            extra_data={
                "kakao_account": {
                    "email": "other@example.test",
                    "is_email_verified": True,
                    "profile": {"nickname": "다른계정"},
                }
            },
        )
        anonymous = Client().get("/api/me").json()
        self.assertEqual(anonymous, {"authenticated": False})
        c = Client()
        c.force_login(self.owner)
        d = c.get("/api/me?user_id=" + str(self.other.pk)).json()
        self.assertEqual(d["nickname"], "총무")
        self.assertEqual(d["kakao_account"]["account_id"], "test-owner-id")
        self.assertEqual(d["kakao_account"]["email"], "owner@example.test")
        self.assertNotIn("other@example.test", str(d))
        self.assertNotIn("access_token", str(d))
        self.assertNotIn("password", str(d))

    def test_unlinked_and_unverified_kakao_identity_are_not_invented(self):
        from allauth.socialaccount.models import SocialAccount

        c = Client()
        c.force_login(self.owner)
        self.assertIsNone(c.get("/api/me").json()["kakao_account"])
        SocialAccount.objects.create(
            user=self.owner,
            provider="kakao",
            uid="test-id",
            extra_data={
                "kakao_account": {
                    "email": "unverified@example.test",
                    "is_email_verified": False,
                    "profile": {"nickname": "카카오이름"},
                }
            },
        )
        d = c.get("/api/me").json()["kakao_account"]
        self.assertEqual(d["name"], "카카오이름")
        self.assertEqual(d["email"], "")
        self.owner.is_active = False
        self.owner.save()
        self.assertEqual(c.get("/api/me").json(), {"authenticated": False})

    def test_full_db_lifecycle_and_history(self):
        self.pending()
        self.act(self.seller, "accept", minutes=10)
        self.act(self.seller, "ready")
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, "READY")
        self.assertEqual(self.o.final_snapshot["total"], 10000)
        self.assertEqual(
            list(self.o.events.values_list("kind", flat=True)),
            ["create", "submit", "close", "send", "accept", "ready"],
        )
        for u in [self.owner, self.seller, self.admin]:
            self.assertEqual(
                s.serialize(s.get_order(u, self.o.pk))["summary"]["total"], 10000
            )

    def test_privacy_and_untransmitted_seller_order(self):
        self.submit()
        for u in [self.other, self.seller]:
            with self.assertRaises(PermissionDenied):
                s.get_order(u, self.o.pk)
        public = Client().get("/api/join/" + self.o.token).json()
        self.assertNotIn("submissions", public)
        self.assertNotIn("items", public)
        self.assertEqual(Client().get("/api/orders/" + str(self.o.pk)).status_code, 403)

    def test_admin_and_seller_cannot_modify_organizer_items(self):
        self.pending()
        for u in [self.admin, self.seller]:
            with self.assertRaises(PermissionDenied):
                self.act(u, "edit", item=Item.objects.first().pk, quantity=3)

    def test_option_aggregation(self):
        self.submit()
        self.submit(items=[{"menu": self.menu.pk, "options": ["hot"], "quantity": 1}])
        d = s.totals(self.o)
        self.assertEqual(d["total"], 14500)
        self.assertEqual(d["count"], 3)
        self.assertEqual(len(d["groups"]), 2)

    def test_deletion_quantity_original_history(self):
        self.submit()
        item = Item.objects.first()
        self.act(self.owner, "edit", item=item.pk, quantity=3)
        item.refresh_from_db()
        self.assertEqual(item.original_quantity, 2)
        self.assertEqual(item.quantity, 3)
        self.act(self.owner, "close")
        self.act(self.owner, "edit", item=item.pk, quantity=0)
        self.assertEqual(s.totals(self.o)["total"], 0)
        with self.assertRaises(s.RuleError):
            self.act(self.owner, "send")
        self.assertEqual(self.o.events.filter(kind="item_change").count(), 2)

    def test_late_submit_and_no_participant_edit(self):
        self.act(self.owner, "close")
        with self.assertRaises(s.RuleError):
            self.submit()
        self.assertEqual(
            Client()
            .post(
                "/api/orders/" + str(self.o.pk),
                {"action": "edit"},
                content_type="application/json",
            )
            .status_code,
            403,
        )

    def test_edit_after_send_and_cancel_after_accept(self):
        self.pending()
        with self.assertRaises(s.RuleError):
            self.act(self.owner, "edit", item=Item.objects.first().pk, quantity=3)
        self.act(self.seller, "accept", minutes=5)
        with self.assertRaises(s.RuleError):
            self.act(self.owner, "cancel")

    def test_version_conflict(self):
        self.submit()
        self.act(self.owner, "close")
        old = self.o.version
        self.act(self.owner, "edit", item=Item.objects.first().pk, quantity=5)
        with self.assertRaises(s.RuleError):
            s.change(
                self.owner,
                self.o.pk,
                {"action": "send", "version": old},
                str(uuid.uuid4()),
            )

    def test_retry_no_duplicate_submit_or_event(self):
        data = {
            "name": "同名",
            "items": [{"menu": self.menu.pk, "options": ["ice"], "quantity": 1}],
        }
        key = str(uuid.uuid4())
        first = s.submit(self.o.token, data, key)
        self.assertEqual(s.submit(self.o.token, data, key), first)
        self.assertEqual(Submission.objects.count(), 1)
        s.submit(self.o.token, data, str(uuid.uuid4()))
        self.assertEqual(Submission.objects.count(), 2)

    def test_send_retry_existing_result(self):
        self.submit()
        self.act(self.owner, "close")
        self.o.refresh_from_db()
        data = {"action": "send", "version": self.o.version}
        key = str(uuid.uuid4())
        first = s.change(self.owner, self.o.pk, data, key)
        self.assertEqual(first, s.change(self.owner, self.o.pk, data, key))
        self.assertEqual(self.o.events.filter(kind="send").count(), 1)

    def test_idempotency_payload_conflict(self):
        key = str(uuid.uuid4())
        s.create_order(self.owner, {"cafe": self.cafe.pk}, key)
        with self.assertRaises(s.RuleError):
            s.create_order(self.owner, {"cafe": 999}, key)

    def test_deadline_equal_rejects_accept_and_persists_expiry(self):
        self.pending()
        with patch("orders.services.db_now", return_value=self.o.deadline):
            r = self.act(self.seller, "accept", minutes=5)
        self.assertIn("error", r)
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, "AUTO_CANCELLED")
        self.assertEqual(self.o.events.filter(kind="auto_cancel").count(), 1)

    def test_before_deadline_accept(self):
        self.pending()
        with patch(
            "orders.services.db_now",
            return_value=self.o.deadline - timedelta(microseconds=1),
        ):
            self.act(self.seller, "accept", minutes=5)
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, "ACCEPTED")

    def test_worker_without_browser_and_accepted_preserved(self):
        self.pending()
        Order.objects.filter(pk=self.o.pk).update(
            deadline=s.db_now() - timedelta(seconds=1)
        )
        call_command("expire_orders", once=True)
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, "AUTO_CANCELLED")
        self.assertLessEqual(
            self.o.events.get(kind="auto_cancel").occurred_at,
            self.o.events.get(kind="auto_cancel").recorded_at,
        )

    def test_worker_preserves_accepted(self):
        self.pending()
        self.act(self.seller, "accept", minutes=5)
        Order.objects.filter(pk=self.o.pk).update(
            deadline=s.db_now() - timedelta(seconds=1)
        )
        call_command("expire_orders", once=True)
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, "ACCEPTED")

    def test_reject_boundaries_unicode(self):
        self.pending()
        for reason in ["가" * 9, "가" * 51, " " * 20]:
            with self.assertRaises(s.RuleError):
                self.act(self.seller, "reject", reason=reason)
        self.act(self.seller, "reject", reason="가" * 10)
        self.assertEqual(self.o.events.get(kind="reject").details["reason"], "가" * 10)

    def test_reject_fifty(self):
        self.pending()
        self.act(self.seller, "reject", reason="가" * 50)
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, "REJECTED")

    def test_invalid_option_quantity_price_server_calculation(self):
        for q in [-1, 0, 1.5, "2", True, 100]:
            with self.assertRaises(s.RuleError):
                self.submit(
                    items=[{"menu": self.menu.pk, "options": ["ice"], "quantity": q}]
                )
        for opts in [["unknown"], ["ice", "hot"], [], ["ice", "ice"], [{}]]:
            with self.assertRaises(s.RuleError):
                self.submit(
                    items=[{"menu": self.menu.pk, "options": opts, "quantity": 1}]
                )
        self.submit(
            items=[
                {
                    "menu": self.menu.pk,
                    "options": ["ice"],
                    "quantity": 1,
                    "price": 1,
                    "total": 1,
                }
            ]
        )
        self.assertEqual(s.totals(self.o)["total"], 4500)

    def test_cafe_snapshot_price_and_name_immutable(self):
        self.menu.price = 100
        self.menu.name = "변경"
        self.menu.save()
        self.cafe.name = "새이름"
        self.cafe.save()
        self.pending()
        self.o.refresh_from_db()
        self.assertEqual(self.o.final_snapshot["total"], 10000)
        self.assertEqual(self.o.cafe_snapshot["name"], "시험 카페")

    def test_seller_delete_cancels_active_orders_and_revokes_session(self):
        self.pending()
        seller = Client()
        seller.force_login(self.seller)
        admin = Client()
        admin.force_login(self.admin)
        r = admin.post(
            "/api/admin",
            {"action": "delete-seller", "id": self.sp.pk},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(r.status_code, 200)
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, "SELLER_DELETED")
        self.assertEqual(seller.get("/api/orders").status_code, 403)
        self.assertEqual(Cafe.objects.get(pk=self.cafe.pk).active, False)
        with self.assertRaises(s.RuleError):
            s.create_order(self.owner, {"cafe": self.cafe.pk}, str(uuid.uuid4()))
        self.assertEqual(self.o.events.filter(kind="seller_deleted").count(), 1)

    def test_seller_delete_accepted_order(self):
        self.pending()
        self.act(self.seller, "accept", minutes=5)
        c = Client()
        c.force_login(self.admin)
        r = c.post(
            "/api/admin",
            {"action": "delete-seller", "id": self.sp.pk},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(r.status_code, 200)
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, "SELLER_DELETED")
        self.assertTrue(self.o.events.filter(kind="accept").exists())

    def test_nickname_unique_normalized_and_no_change(self):
        u = User.objects.create_user("new")
        Profile.objects.create(user=u, role="organizer")
        c = Client()
        c.force_login(u)
        self.assertEqual(
            c.post(
                "/api/nickname",
                {"nickname": "  Abc  "},
                content_type="application/json",
            ).status_code,
            200,
        )
        self.assertEqual(
            c.post(
                "/api/nickname", {"nickname": "Def"}, content_type="application/json"
            ).status_code,
            409,
        )
        u2 = User.objects.create_user("new2")
        Profile.objects.create(user=u2, role="organizer")
        c.force_login(u2)
        self.assertEqual(
            c.post(
                "/api/nickname", {"nickname": "abc"}, content_type="application/json"
            ).status_code,
            409,
        )

    def test_csrf_rejects_mutation_without_token(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.owner)
        self.assertEqual(
            c.post(
                "/api/orders",
                {"cafe": self.cafe.pk},
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code,
            403,
        )

    def test_wrong_store_access_poll_and_role_forgery(self):
        other_cafe = Cafe.objects.create(name="다른매장", location="서울")
        u = User.objects.create_user("other-seller")
        Profile.objects.create(user=u, role="seller", cafe=other_cafe)
        self.pending()
        c = Client()
        c.force_login(u)
        self.assertEqual(c.get("/api/orders/" + str(self.o.pk)).status_code, 403)
        self.assertEqual(c.get("/api/orders").json()["total"], 0)
        participant = Client()
        self.assertEqual(
            participant.post(
                "/api/admin", {"role": "admin"}, content_type="application/json"
            ).status_code,
            403,
        )

    def test_receipt_only_own_submission(self):
        a = self.submit(name="하나")
        self.submit(name="둘")
        d = Client().get("/api/receipts/" + a["receipt"]).json()
        self.assertEqual(d["name"], "하나")
        self.assertEqual(len(d["items"]), 1)

    def test_operator_ui_registers_real_cafe_menu_seller(self):
        c = Client()
        c.force_login(self.admin)

        def post(data):
            return c.post(
                "/api/admin",
                data,
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            )

        new = post(
            {
                "action": "cafe",
                "name": "실제등록",
                "description": "소개",
                "location": "주소",
            }
        ).json()["id"]
        self.assertEqual(
            post(
                {
                    "action": "menu",
                    "cafe": new,
                    "name": "에스프레소",
                    "description": "",
                    "price": 3000,
                    "options": [],
                }
            ).status_code,
            200,
        )
        self.assertEqual(
            post(
                {
                    "action": "seller",
                    "cafe": new,
                    "username": "real-seller",
                    "password": "SufficientPassword-398!",
                }
            ).status_code,
            200,
        )
        cafes = Client().get("/api/cafes").json()["cafes"]
        self.assertTrue(
            any(x["id"] == new and x["menus"][0]["price"] == 3000 for x in cafes)
        )

    def test_role_login_returns_to_original_screen_without_external_redirect(self):
        c = Client()
        url = "/seller/orders/" + str(self.o.pk)
        self.assertIn("next=", c.get(url).url)
        r = c.post(
            "/seller/login?next=" + url,
            {"username": "seller", "password": "Coffee-Test-893!"},
        )
        self.assertEqual(r.url, url)
        c.logout()
        r = c.post(
            "/seller/login?next=https://evil.example",
            {"username": "seller", "password": "Coffee-Test-893!"},
        )
        self.assertEqual(r.url, "/seller/orders")

    def test_password_login_rate_limit(self):
        c = Client()
        for _ in range(10):
            self.assertEqual(
                c.post(
                    "/seller/login", {"username": "seller", "password": "incorrect"}
                ).status_code,
                400,
            )
        self.assertEqual(
            c.post(
                "/seller/login", {"username": "seller", "password": "incorrect"}
            ).status_code,
            429,
        )

    def test_log_redacts_link_and_receipt_tokens(self):
        import logging
        from .logging import RedactCapabilities

        record = logging.LogRecord(
            "django.server",
            20,
            "",
            0,
            "GET /api/join/%s and /api/receipts/%s",
            ("secret-token", "private-receipt"),
            None,
        )
        RedactCapabilities().filter(record)
        self.assertNotIn("secret-token", record.getMessage())
        self.assertNotIn("private-receipt", record.getMessage())

    def test_get_and_wrong_role_mutations_do_not_change_state(self):
        c = Client()
        c.force_login(self.seller)
        self.assertEqual(
            c.post(
                "/api/admin",
                {"action": "cafe", "name": "forged"},
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code,
            403,
        )
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, "COLLECTING")

    def test_pagination_and_history_filters(self):
        for _ in range(23):
            s.create_order(self.owner, {"cafe": self.cafe.pk}, str(uuid.uuid4()))
        c = Client()
        c.force_login(self.owner)
        self.assertEqual(len(c.get("/api/orders?page=1").json()["orders"]), 20)
        self.assertEqual(len(c.get("/api/orders?page=2").json()["orders"]), 4)
        self.assertEqual(c.get("/api/orders?status=PENDING").json()["total"], 0)
        self.assertEqual(
            c.get("/api/orders?number=" + self.o.number).json()["total"], 1
        )


@override_settings(DEMO_MODE=False, POLICIES_APPROVED=True)
class ConcurrentTests(Fixtures, TransactionTestCase):
    def race(self, a, b):
        def run(fn):
            connections.close_all()
            try:
                fn()
                return "ok"
            except (s.RuleError, IntegrityError):
                return "blocked"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, [a, b]))

    def test_close_vs_submit(self):
        result = self.race(
            lambda: s.change(
                self.owner,
                self.o.pk,
                {"action": "close", "version": 0},
                str(uuid.uuid4()),
            ),
            lambda: self.submit(),
        )
        self.o.refresh_from_db()
        if self.o.status == "COLLECTING":
            self.act(self.owner, "close")
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, "CLOSED")
        with self.assertRaises(s.RuleError):
            self.submit()
        for e in self.o.events.filter(kind="submit"):
            self.assertLessEqual(e.occurred_at, self.o.closed_at)

    def test_accept_vs_cancel(self):
        self.pending()
        result = self.race(
            lambda: s.change(
                self.seller,
                self.o.pk,
                {"action": "accept", "minutes": 5},
                str(uuid.uuid4()),
            ),
            lambda: s.change(
                self.owner, self.o.pk, {"action": "cancel"}, str(uuid.uuid4())
            ),
        )
        self.assertEqual(sorted(result), ["blocked", "ok"])
        self.o.refresh_from_db()
        self.assertIn(self.o.status, ["ACCEPTED", "CANCELLED"])
        self.assertEqual(self.o.events.filter(kind__in=["accept", "cancel"]).count(), 1)

    def test_edit_vs_send(self):
        self.submit()
        self.act(self.owner, "close")
        self.o.refresh_from_db()
        v = self.o.version
        i = Item.objects.first()
        result = self.race(
            lambda: s.change(
                self.owner,
                self.o.pk,
                {"action": "send", "version": v},
                str(uuid.uuid4()),
            ),
            lambda: s.change(
                self.owner,
                self.o.pk,
                {"action": "edit", "version": v, "item": i.pk, "quantity": 3},
                str(uuid.uuid4()),
            ),
        )
        self.assertEqual(sorted(result), ["blocked", "ok"])
        self.o.refresh_from_db()
        if self.o.status == "PENDING":
            self.assertEqual(self.o.final_snapshot["total"], 10000)
        else:
            self.assertEqual(s.totals(self.o)["total"], 15000)

    def test_same_retry_concurrently(self):
        data = {
            "name": "하나",
            "items": [{"menu": self.menu.pk, "options": ["ice"], "quantity": 1}],
        }
        key = str(uuid.uuid4())
        result = self.race(
            lambda: s.submit(self.o.token, data, key),
            lambda: s.submit(self.o.token, data, key),
        )
        self.assertEqual(result, ["ok", "ok"])
        self.assertEqual(Submission.objects.count(), 1)

    def test_nickname_unique_concurrently(self):
        a = Profile.objects.get(user=self.owner)
        b = Profile.objects.get(user=self.other)

        def rename(p):
            with transaction.atomic():
                p.nickname = "같음"
                p.nickname_key = "같음"
                p.save()

        result = self.race(lambda: rename(a), lambda: rename(b))
        self.assertEqual(sorted(result), ["blocked", "ok"])
        self.assertEqual(Profile.objects.filter(nickname_key="같음").count(), 1)

    def test_delete_vs_send(self):
        self.submit()
        self.act(self.owner, "close")
        self.o.refresh_from_db()
        v = self.o.version

        def delete():
            c = Client()
            c.force_login(self.admin)
            r = c.post(
                "/api/admin",
                {"action": "delete-seller", "id": self.sp.pk},
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            )
            if r.status_code != 200:
                raise AssertionError(r.content)

        self.race(
            delete,
            lambda: s.change(
                self.owner,
                self.o.pk,
                {"action": "send", "version": v},
                str(uuid.uuid4()),
            ),
        )
        self.o.refresh_from_db()
        self.assertIn(self.o.status, ["CLOSED", "SELLER_DELETED"])
        self.assertFalse(Cafe.objects.get(pk=self.cafe.pk).active)
