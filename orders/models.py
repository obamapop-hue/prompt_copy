import secrets, uuid
from django.conf import settings
from django.db import models


def token():
    return secrets.token_urlsafe(32)


class Cafe(models.Model):
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200)
    active = models.BooleanField(default=True)
    demo = models.BooleanField(default=False)


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(
        max_length=12,
        choices=[("organizer", "총무"), ("seller", "판매자"), ("admin", "운영자")],
    )
    nickname = models.CharField(max_length=20, blank=True)
    nickname_key = models.CharField(max_length=20, unique=True, null=True)
    cafe = models.ForeignKey(Cafe, null=True, blank=True, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)


class Menu(models.Model):
    cafe = models.ForeignKey(Cafe, on_delete=models.PROTECT, related_name="menus")
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    price = models.PositiveIntegerField()
    options = models.JSONField(default=list)
    active = models.BooleanField(default=True)


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organizer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    cafe = models.ForeignKey(Cafe, on_delete=models.PROTECT)
    token = models.CharField(max_length=64, default=token, unique=True)
    cafe_snapshot = models.JSONField(default=dict)
    menu_snapshot = models.JSONField(default=list)
    nickname_snapshot = models.CharField(max_length=20)
    status = models.CharField(max_length=20, default="COLLECTING")
    version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True)
    sent_at = models.DateTimeField(null=True)
    deadline = models.DateTimeField(null=True, db_index=True)
    expected_at = models.DateTimeField(null=True)
    final_snapshot = models.JSONField(default=dict)
    demo = models.BooleanField(default=False)

    @property
    def number(self):
        return "CF-" + self.id.hex[:12].upper()


class Submission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name="submissions"
    )
    name = models.CharField(max_length=30)
    receipt = models.CharField(max_length=64, default=token, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Item(models.Model):
    submission = models.ForeignKey(
        Submission, on_delete=models.PROTECT, related_name="items"
    )
    snapshot = models.JSONField()
    original_quantity = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveIntegerField()
    deleted = models.BooleanField(default=False)


class Event(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=30)
    before = models.CharField(max_length=20)
    after = models.CharField(max_length=20)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT
    )
    details = models.JSONField(default=dict)
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)


class RequestRecord(models.Model):
    scope = models.CharField(max_length=160)
    key = models.CharField(max_length=80)
    digest = models.CharField(max_length=64)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "key"], name="unique_request")
        ]


class LoginAttempt(models.Model):
    subject = models.CharField(max_length=64, db_index=True)
    at = models.DateTimeField(auto_now_add=True)
