import json, re, unicodedata
from functools import wraps
from urllib.parse import urlencode
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError, ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from . import services as s
from .models import *

LABELS = {
    "COLLECTING": "모집 중",
    "CLOSED": "마감",
    "PENDING": "접수 대기",
    "ACCEPTED": "준비 중",
    "READY": "준비 완료",
    "CANCELLED": "총무 취소",
    "REJECTED": "판매자 거절",
    "AUTO_CANCELLED": "자동 취소",
    "SELLER_DELETED": "판매자 삭제로 취소",
}


def api(fn):
    @wraps(fn)
    def wrapped(request, *args, **kwargs):
        try:
            response = JsonResponse(fn(request, *args, **kwargs))
            response["Cache-Control"] = "no-store"
            return response
        except ObjectDoesNotExist:
            return JsonResponse({"error": "자료를 찾을 수 없습니다."}, status=404)
        except PermissionDenied:
            return JsonResponse({"error": "접근 권한이 없습니다."}, status=403)
        except s.RuleError as e:
            return JsonResponse({"error": e.message}, status=e.status)
        except (ValueError, TypeError, KeyError, ValidationError):
            return JsonResponse({"error": "입력 형식을 확인하세요."}, status=400)
        except IntegrityError:
            return JsonResponse(
                {"error": "중복된 값입니다. 최신 상태를 확인하세요."}, status=409
            )

    return wrapped


def body(r):
    if len(r.body) > 100000:
        raise s.RuleError("요청이 너무 큽니다.", 400)
    data = json.loads(r.body or "{}")
    if not isinstance(data, dict):
        raise ValueError
    return data


def key(r):
    return r.headers.get("Idempotency-Key", "")


@never_cache
def page(r, mode, oid=None, token=None):
    if mode in ["orders", "detail", "seller", "admin", "admin-orders"]:
        if not r.user.is_authenticated:
            target = (
                "/seller/login"
                if mode == "seller"
                else "/admin/login" if mode.startswith("admin") else "/login"
            )
            return redirect(target + "?" + urlencode({"next": r.get_full_path()}))
        p = s.profile(r.user)
        if mode == "seller" and p.role != "seller":
            raise PermissionDenied
        if mode.startswith("admin") and p.role != "admin":
            raise PermissionDenied
        if mode in ["orders", "detail"] and p.role != "organizer":
            raise PermissionDenied
        if oid:
            s.get_order(r.user, oid)
    return_to = r.GET.get("next", "")
    if not return_to.startswith("/") or not url_has_allowed_host_and_scheme(
        return_to, allowed_hosts={r.get_host()}
    ):
        return_to = ""
    if r.user.is_authenticated and mode in ["home", "login", "cafes"]:
        account = s.profile(r.user)
        if account.role == "organizer" and not account.nickname:
            target = return_to or (r.path if mode != "login" else "/")
            return redirect("/my/orders?" + urlencode({"next": target}))
        if mode == "login":
            return redirect(return_to or "/")
    return render(
        r,
        "orders/app.html",
        {
            "return_to": return_to,
            "login_next": return_to
            or (r.path if mode not in ["home", "login"] else "/"),
            "mode": mode,
            "oid": oid or "",
            "token": token or "",
            "demo": settings.DEMO_MODE,
            "kakao_ready": bool(
                settings.SOCIALACCOUNT_PROVIDERS["kakao"]["APPS"][0]["client_id"]
            ),
        },
    )


@never_cache
def role_login(r, role):
    if r.method == "POST":
        from django.utils.crypto import salted_hmac
        from datetime import timedelta

        username = r.POST.get("username", "")[:150]
        subjects = [
            salted_hmac("login-user", username).hexdigest(),
            salted_hmac("login-ip", r.META.get("REMOTE_ADDR", "")).hexdigest(),
        ]
        with transaction.atomic():
            cutoff = s.db_now() - timedelta(minutes=5)
            LoginAttempt.objects.filter(at__lt=cutoff).delete()
            if any(
                LoginAttempt.objects.filter(subject=x, at__gte=cutoff).count() >= 10
                for x in subjects
            ):
                return render(
                    r,
                    "orders/login.html",
                    {
                        "role": role,
                        "error": "로그인 시도가 많습니다. 5분 후 다시 시도하세요.",
                    },
                    status=429,
                )
            for subject in subjects:
                LoginAttempt.objects.create(subject=subject)
        user = authenticate(r, username=username, password=r.POST.get("password"))
        try:
            if not user:
                raise PermissionDenied
            s.profile(user, role)
            login(r, user)
            target = r.GET.get("next", "")
            if not target.startswith(
                "/seller/orders" if role == "seller" else "/admin"
            ) or not url_has_allowed_host_and_scheme(
                target, allowed_hosts={r.get_host()}
            ):
                target = "/seller/orders" if role == "seller" else "/admin"
            return redirect(target)
        except PermissionDenied:
            return render(
                r,
                "orders/login.html",
                {"role": role, "error": "계정 정보 또는 접근 권한을 확인하세요."},
                status=400,
            )
    return render(r, "orders/login.html", {"role": role})


@require_POST
def signout(r):
    logout(r)
    return redirect("/")


@api
def me(r):
    if not r.user.is_authenticated:
        return {"authenticated": False}
    p = s.profile(r.user)
    from allauth.socialaccount.models import SocialAccount

    account = SocialAccount.objects.filter(user=r.user, provider="kakao").first()
    linked = None
    if account and p.role == "organizer":
        extra = account.extra_data
        kakao = extra.get("kakao_account", {})
        display = kakao.get("profile", {}).get("nickname") or extra.get(
            "properties", {}
        ).get("nickname", "")
        linked = {
            "account_id": account.uid,
            "name": display,
            "email": (
                kakao.get("email", "") if kakao.get("is_email_verified") is True else ""
            ),
        }
    return {
        "authenticated": True,
        "role": p.role,
        "nickname": p.nickname,
        "account_name": r.user.username,
        "kakao_account": linked,
    }


@require_POST
@api
def nickname(r):
    s.profile(r.user, "organizer")
    s.policies()
    data = body(r)
    with transaction.atomic():
        p = s.profile(r.user, "organizer")
        if p.nickname:
            raise s.RuleError("닉네임은 변경할 수 없습니다.")
        name = unicodedata.normalize(
            "NFC", s.text(data.get("nickname"), 2, 20, "닉네임")
        )
        if not re.fullmatch(r"[가-힣A-Za-z0-9_]+", name):
            raise s.RuleError("한글·영문·숫자·밑줄만 사용할 수 있습니다.", 400)
        p.nickname = name
        p.nickname_key = name.casefold()
        p.save()
    return {"nickname": name}


@api
def cafes(r, cid=None):
    qs = Cafe.objects.filter(
        active=True,
        demo=settings.DEMO_MODE,
        profile__role="seller",
        profile__active=True,
        profile__user__is_active=True,
    ).distinct()
    if cid:
        qs = qs.filter(pk=cid)
    return {
        "cafes": [
            {
                "id": c.pk,
                "name": c.name,
                "description": c.description,
                "location": c.location,
                "demo": c.demo,
                "menus": [
                    {
                        "id": m.pk,
                        "name": m.name,
                        "description": m.description,
                        "price": m.price,
                        "options": m.options,
                    }
                    for m in c.menus.filter(active=True)
                ],
            }
            for c in qs
        ]
    }


@api
def orders(r):
    if r.method == "POST":
        return s.create_order(r.user, body(r), key(r))
    qs = s.visible(r.user).order_by("-created_at")
    for f in ["status", "cafe"]:
        if r.GET.get(f):
            qs = qs.filter(**{f if f == "status" else "cafe_id": r.GET[f]})
    if r.GET.get("from"):
        qs = qs.filter(created_at__date__gte=r.GET["from"])
    if r.GET.get("to"):
        qs = qs.filter(created_at__date__lte=r.GET["to"])
    if r.GET.get("number"):
        v = r.GET["number"].replace("CF-", "").replace("-", "")
        qs = qs.filter(id__startswith=v)
    page = max(1, min(int(r.GET.get("page", "1")), 100000))
    count = qs.count()
    with transaction.atomic():
        result = []
        for o in qs[(page - 1) * 20 : page * 20]:
            s.expire(o)
            result.append(s.serialize(o))
    return {
        "orders": result,
        "page": page,
        "total": count,
        "has_next": count > page * 20,
    }


@api
def order(r, oid):
    if r.method == "POST":
        return s.change(r.user, oid, body(r), key(r))
    with transaction.atomic():
        o = s.get_order(r.user, oid)
        s.expire(o)
        d = s.serialize(o)
    if s.profile(r.user).role == "organizer":
        d["join_url"] = "/join/" + o.token
    return {"order": d}


@api
def join(r, token):
    if r.method == "POST":
        return s.submit(token, body(r), key(r))
    try:
        o = Order.objects.get(token=token)
    except Order.DoesNotExist:
        raise s.RuleError("유효하지 않은 참여 링크입니다.", 404)
    return {
        "number": o.number,
        "status": o.status,
        "cafe": o.cafe_snapshot,
        "menus": o.menu_snapshot,
        "demo": o.demo,
    }


@api
def receipt(r, token):
    try:
        sub = Submission.objects.get(receipt=token)
    except Submission.DoesNotExist:
        raise s.RuleError("제출 결과를 찾을 수 없습니다.", 404)
    return {
        "name": sub.name,
        "number": sub.order.number,
        "items": [
            {
                "menu": i.snapshot["name"],
                "options": i.snapshot["options"],
                "quantity": i.original_quantity,
                "amount": i.original_quantity * i.unit_price,
            }
            for i in sub.items.all()
        ],
    }


@api
def administration(r):
    s.profile(r.user, "admin")
    if r.method == "GET":
        return {
            "cafes": [
                {
                    "id": c.pk,
                    "name": c.name,
                    "description": c.description,
                    "location": c.location,
                    "active": c.active,
                    "demo": c.demo,
                    "menus": [
                        {
                            "id": m.pk,
                            "name": m.name,
                            "description": m.description,
                            "price": m.price,
                            "options": m.options,
                            "active": m.active,
                        }
                        for m in c.menus.all()
                    ],
                }
                for c in Cafe.objects.all()
            ],
            "sellers": [
                {
                    "id": p.pk,
                    "username": p.user.username,
                    "cafe": p.cafe_id,
                    "active": p.active,
                }
                for p in Profile.objects.filter(role="seller").select_related("user")
            ],
        }
    data = body(r)

    def work():
        s.profile(r.user, "admin")
        action = data.get("action")
        if action == "cafe":
            cid = data.get("id")
            c = Cafe.objects.get(pk=cid) if cid else Cafe(demo=settings.DEMO_MODE)
            c.name = s.text(data.get("name"), 1, 80, "매장명")
            c.description = s.text(data.get("description", ""), 0, 2000, "소개")
            c.location = s.text(data.get("location"), 1, 200, "위치")
            c.save()
            return {"id": c.pk}
        if action == "menu":
            mid = data.get("id")
            m = (
                Menu.objects.get(pk=mid)
                if mid
                else Menu(cafe=Cafe.objects.get(pk=data.get("cafe")))
            )
            m.name = s.text(data.get("name"), 1, 80, "메뉴명")
            m.description = s.text(data.get("description", ""), 0, 2000, "설명")
            m.price = s.integer(data.get("price"), 0, 1000000, "가격")
            opts = data.get("options", [])
            if not isinstance(opts, list) or len(opts) > 50:
                raise ValueError
            ids = set()
            for opt in opts:
                if not isinstance(opt, dict):
                    raise ValueError
                opt["id"] = s.text(opt.get("id"), 1, 40, "옵션 ID")
                opt["name"] = s.text(opt.get("name"), 1, 60, "옵션명")
                opt["price"] = s.integer(opt.get("price"), 0, 1000000, "옵션 가격")
                if opt.get("group"):
                    opt["group"] = s.text(opt["group"], 1, 40, "옵션 그룹")
                if opt["id"] in ids:
                    raise ValueError
                ids.add(opt["id"])
            m.options = opts
            if "active" in data:
                if type(data["active"]) is not bool:
                    raise ValueError
                m.active = data["active"]
            m.save()
            return {"id": m.pk}
        if action == "seller":
            cafe = Cafe.objects.get(pk=data.get("cafe"))
            if not cafe.active:
                raise s.RuleError("비활성 매장입니다.")
            username = s.text(data.get("username"), 3, 100, "계정명")
            password = data.get("password")
            if not isinstance(password, str):
                raise ValueError
            user = User(username=username)
            validate_password(password, user)
            user.set_password(password)
            user.save()
            p = Profile.objects.create(user=user, role="seller", cafe=cafe)
            return {"id": p.pk}
        if action == "delete-seller":
            p = Profile.objects.select_related("user", "cafe").get(
                pk=data.get("id"), role="seller"
            )
            if not p.active:
                return {"deleted": True}
            p.active = False
            p.save(update_fields=["active"])
            User.objects.filter(pk=p.user_id).update(is_active=False)
            p.cafe.active = False
            p.cafe.save(update_fields=["active"])
            for o in Order.objects.filter(
                cafe=p.cafe, status__in=["PENDING", "ACCEPTED"]
            ):
                if s.expire(o):
                    continue
                before = o.status
                o.status = "SELLER_DELETED"
                o.version += 1
                o.save(update_fields=["status", "version"])
                s.event(o, "seller_deleted", before, r.user, {"seller": p.pk})
            return {"deleted": True}
        raise s.RuleError("허용되지 않은 관리 작업입니다.", 400)

    return s.idempotent(f"admin:{r.user.pk}", key(r), data, work)


@never_cache
def health(r):
    import time
    from pathlib import Path
    from django.db import DatabaseError

    try:
        # Query a real application table: SELECT 1 alone would accept an unmigrated DB.
        Order.objects.exists()
        if settings.REQUIRE_WORKER_HEARTBEAT:
            if not settings.WORKER_HEARTBEAT_PATH:
                raise OSError("No worker heartbeat path configured")
            age = time.time() - Path(settings.WORKER_HEARTBEAT_PATH).stat().st_mtime
            if not 0 <= age <= 15:
                raise OSError("Worker heartbeat is stale")
        return JsonResponse({"status": "ok"})
    except (DatabaseError, OSError):
        return JsonResponse({"status": "unavailable"}, status=503)
