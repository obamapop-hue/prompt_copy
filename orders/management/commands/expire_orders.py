import time
import os
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from orders.models import Order
from orders.services import expire, db_now


class Command(BaseCommand):
    help = "Browser-independent expiry worker. Supervise this process in production."

    def add_arguments(self, p):
        p.add_argument("--once", action="store_true")

    def handle(self, *args, **opts):
        while True:
            with transaction.atomic():
                for o in Order.objects.filter(
                    status="PENDING", deadline__lte=db_now()
                ).order_by("deadline")[:100]:
                    expire(o)
            if settings.WORKER_HEARTBEAT_PATH:
                target = Path(settings.WORKER_HEARTBEAT_PATH)
                fd = os.open(target, os.O_CREAT | os.O_WRONLY, 0o600)
                os.close(fd)
                os.utime(target, None)
            if opts["once"]:
                return
            time.sleep(1)
