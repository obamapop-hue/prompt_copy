import hashlib, json, unicodedata
from datetime import timedelta
from django.conf import settings
from django.db import connection, transaction
from django.core.exceptions import PermissionDenied
from .models import *


class RuleError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status


def db_now():
    from datetime import datetime, timezone

    with connection.cursor() as c:
        c.execute("SELECT STRFTIME('%Y-%m-%dT%H:%M:%f', 'now')")
        return datetime.fromisoformat(c.fetchone()[0]).replace(tzinfo=timezone.utc)


def profile(user, role=None):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    try:
        p = Profile.objects.select_related("cafe").get(user=user, active=True)
    except Profile.DoesNotExist:
        raise PermissionDenied
    if role and p.role != role:
        raise PermissionDenied
    if p.role == "seller" and not p.cafe:
        raise PermissionDenied
    return p


def visible(user):
    p = profile(user)
    qs = Order.objects.all()
    if p.role == "organizer":
        return qs.filter(organizer=user)
    if p.role == "seller":
        return qs.filter(cafe=p.cafe, sent_at__isnull=False)
    return qs


def get_order(user, oid):
    try:
        return visible(user).get(pk=oid)
    except (Order.DoesNotExist, ValueError):
        raise PermissionDenied


def policies():
    if not settings.POLICIES_APPROVED:
        raise RuleError("미확정 운영 정책 승인 후 이용할 수 있습니다.", 503)


def integer(value, lo, hi, label):
    if type(value) is not int or not lo <= value <= hi:
        raise RuleError(f"{label}: {lo}~{hi} 정수를 입력하세요.", 400)
    return value


def text(value, lo, hi, label):
    if not isinstance(value, str):
        raise RuleError(f"{label} 형식 오류", 400)
    value = unicodedata.normalize("NFC", value).strip()
    if not lo <= len(value) <= hi:
        raise RuleError(f"{label}: {lo}~{hi}자로 입력하세요.", 400)
    return value


def idempotent(scope, key, data, work):
    if not isinstance(key, str) or not 8 <= len(key) <= 80:
        raise RuleError("요청 식별자가 필요합니다.", 400)
    digest = hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    with transaction.atomic():
        old = RequestRecord.objects.filter(scope=scope, key=key).first()
        if old:
            if old.digest != digest:
                raise RuleError("같은 요청 식별자로 내용을 변경할 수 없습니다.")
            return old.result
        result = work()
        RequestRecord.objects.create(scope=scope, key=key, digest=digest, result=result)
        return result


def event(o, kind, before, actor, details=None, when=None):
    Event.objects.create(
        order=o,
        kind=kind,
        before=before,
        after=o.status,
        actor=actor,
        details=details or {},
        occurred_at=when or db_now(),
    )


def expire(o):
    now = db_now()
    if o.status == "PENDING" and now >= o.deadline:
        o.status = "AUTO_CANCELLED"
        o.version += 1
        o.save(update_fields=["status", "version"])
        event(
            o,
            "auto_cancel",
            "PENDING",
            None,
            {"deadline": o.deadline.isoformat()},
            o.deadline,
        )
        return True
    return False


def totals(o):
    groups = {}
    items = []
    total = 0
    count = 0
    for i in (
        Item.objects.filter(submission__order=o)
        .select_related("submission")
        .order_by("pk")
    ):
        q = 0 if i.deleted else i.quantity
        row = {
            "id": i.pk,
            "name": i.submission.name,
            "menu": i.snapshot["name"],
            "options": i.snapshot["options"],
            "quantity": q,
            "original_quantity": i.original_quantity,
            "unit_price": i.unit_price,
            "amount": q * i.unit_price,
            "deleted": i.deleted,
        }
        items.append(row)
        if q:
            key = json.dumps(i.snapshot, sort_keys=True, ensure_ascii=False)
            g = groups.setdefault(
                key,
                {
                    "menu": row["menu"],
                    "options": row["options"],
                    "quantity": 0,
                    "amount": 0,
                },
            )
            g["quantity"] += q
            g["amount"] += q * i.unit_price
            total += q * i.unit_price
            count += q
    return {
        "items": items,
        "groups": list(groups.values()),
        "total": total,
        "count": count,
    }


def serialize(o):
    d = {
        "id": str(o.id),
        "number": o.number,
        "status": o.status,
        "version": o.version,
        "cafe": o.cafe_snapshot,
        "nickname": o.nickname_snapshot,
        "demo": o.demo,
        "summary": o.final_snapshot if o.sent_at else totals(o),
    }
    for f in ["created_at", "closed_at", "sent_at", "deadline", "expected_at"]:
        d[f] = getattr(o, f).isoformat() if getattr(o, f) else None
    d["events"] = [
        {
            "kind": e.kind,
            "before": e.before,
            "after": e.after,
            "actor": e.actor_id or "system",
            "details": e.details,
            "occurred_at": e.occurred_at.isoformat(),
            "recorded_at": e.recorded_at.isoformat(),
        }
        for e in o.events.order_by("pk")
    ]
    return d


def create_order(user, data, key):
    profile(user, "organizer")
    policies()

    def work():
        p = profile(user, "organizer")
        if not p.nickname:
            raise RuleError("최초 닉네임을 설정하세요.", 400)
        try:
            c = Cafe.objects.get(
                pk=data.get("cafe"), active=True, demo=settings.DEMO_MODE
            )
        except Cafe.DoesNotExist:
            raise RuleError("선택 가능한 매장이 아닙니다.", 400)
        if not Profile.objects.filter(
            cafe=c, role="seller", active=True, user__is_active=True
        ).exists():
            raise RuleError("판매자가 없는 매장입니다.")
        menus = [
            {
                "id": m.pk,
                "name": m.name,
                "description": m.description,
                "price": m.price,
                "options": m.options,
            }
            for m in c.menus.filter(active=True)
        ]
        o = Order.objects.create(
            organizer=user,
            cafe=c,
            cafe_snapshot={
                "name": c.name,
                "description": c.description,
                "location": c.location,
            },
            menu_snapshot=menus,
            nickname_snapshot=p.nickname,
            demo=c.demo,
        )
        event(o, "create", "", user)
        return {"id": str(o.id)}

    return idempotent(f"create:{user.pk}", key, data, work)


def submit(token_value, data, key):
    policies()

    def work():
        try:
            o = Order.objects.get(token=token_value)
        except Order.DoesNotExist:
            raise RuleError("유효하지 않은 참여 링크입니다.", 404)
        if o.status != "COLLECTING":
            raise RuleError("모집이 마감된 주문입니다.")
        name = text(data.get("name"), 1, 30, "이름")
        rows = data.get("items")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise RuleError("음료를 담아주세요.", 400)
        s = Submission.objects.create(order=o, name=name)
        for row in rows:
            if not isinstance(row, dict):
                raise RuleError("항목 형식 오류", 400)
            m = next((m for m in o.menu_snapshot if m["id"] == row.get("menu")), None)
            if not m:
                raise RuleError("메뉴가 유효하지 않습니다.", 400)
            options = row.get("options", [])
            if (
                not isinstance(options, list)
                or any(type(x) is not str for x in options)
                or len(options) != len(set(options))
            ):
                raise RuleError("옵션 형식 오류", 400)
            valid = {x["id"]: x for x in m["options"]}
            if any(x not in valid for x in options):
                raise RuleError("옵션이 유효하지 않습니다.", 400)
            selected = [valid[x] for x in sorted(options)]
            # Each group represents one required choice, such as temperature.
            for group in {x.get("group") for x in m["options"] if x.get("group")}:
                if sum(x.get("group") == group for x in selected) != 1:
                    raise RuleError(f"{group} 옵션을 하나 선택하세요.", 400)
            q = integer(row.get("quantity"), 1, 99, "수량")
            price = m["price"] + sum(x["price"] for x in selected)
            Item.objects.create(
                submission=s,
                snapshot={
                    "menu_id": m["id"],
                    "name": m["name"],
                    "base_price": m["price"],
                    "options": selected,
                },
                original_quantity=q,
                quantity=q,
                unit_price=price,
            )
        o.version += 1
        o.save(update_fields=["version"])
        event(o, "submit", o.status, None, {"submission": str(s.pk)})
        return {"receipt": s.receipt, "number": o.number, "name": s.name}

    return idempotent(f"submit:{token_value}", key, data, work)


def change(user, oid, data, key):
    p = profile(user)
    get_order(user, oid)

    def work():
        p = profile(user)
        o = get_order(user, oid)
        if expire(o):
            return {
                "order": serialize(o),
                "error": "접수 기한이 지나 자동 취소되었습니다.",
            }
        action = data.get("action")
        before = o.status
        if p.role == "organizer":
            if action not in ["close", "edit", "send", "cancel"]:
                raise PermissionDenied
            if action in ["close", "edit", "send"] and data.get("version") != o.version:
                raise RuleError("내용이 변경되었습니다. 최신 내역을 확인하세요.")
            if action == "close":
                if o.status != "COLLECTING":
                    raise RuleError("모집 중에만 마감할 수 있습니다.")
                o.status = "CLOSED"
                o.closed_at = db_now()
            elif action == "edit":
                if o.status not in ["COLLECTING", "CLOSED"]:
                    raise RuleError("전송 전만 수정할 수 있습니다.")
                try:
                    i = Item.objects.get(pk=data.get("item"), submission__order=o)
                except Item.DoesNotExist:
                    raise PermissionDenied
                policies()
                q = integer(data.get("quantity"), 0, 99, "수량")
                old = i.quantity
                i.quantity = q
                i.deleted = q == 0
                i.save()
                event(
                    o,
                    "item_change",
                    before,
                    user,
                    {"item": i.pk, "before": old, "after": q},
                )
            elif action == "send":
                policies()
                if o.status != "CLOSED":
                    raise RuleError("마감 후 전송하세요.")
                if (
                    not Cafe.objects.filter(pk=o.cafe_id, active=True).exists()
                    or not Profile.objects.filter(
                        cafe=o.cafe, role="seller", active=True, user__is_active=True
                    ).exists()
                ):
                    raise RuleError("매장 주문 접수가 중단되었습니다.")
                summary = totals(o)
                if not summary["count"]:
                    raise RuleError("빈 주문은 전송할 수 없습니다.", 400)
                o.final_snapshot = summary
                o.status = "PENDING"
                o.sent_at = db_now()
                o.deadline = o.sent_at + timedelta(minutes=5)
            else:
                if o.status != "PENDING":
                    raise RuleError("접수 대기 중에만 취소할 수 있습니다.")
                o.status = "CANCELLED"
        elif p.role == "seller":
            if action == "accept":
                policies()
                if o.status != "PENDING":
                    raise RuleError("접수 대기 주문만 수락할 수 있습니다.")
                minutes = integer(data.get("minutes"), 1, 180, "준비 시간")
                o.status = "ACCEPTED"
                o.expected_at = db_now() + timedelta(minutes=minutes)
            elif action == "reject":
                if o.status != "PENDING":
                    raise RuleError("접수 대기 주문만 거절할 수 있습니다.")
                data["reason"] = text(data.get("reason"), 10, 50, "거절 사유")
                o.status = "REJECTED"
            elif action == "ready":
                if o.status != "ACCEPTED":
                    raise RuleError("준비 중 주문만 완료할 수 있습니다.")
                o.status = "READY"
            else:
                raise PermissionDenied
        else:
            raise PermissionDenied
        o.version += 1
        o.save()
        if action != "edit":
            event(
                o,
                action,
                before,
                user,
                {"reason": data["reason"]} if action == "reject" else {},
            )
        return {"order": serialize(o)}

    return idempotent(f"change:{user.pk}:{oid}", key, data, work)
