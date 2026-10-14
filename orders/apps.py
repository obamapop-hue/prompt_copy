from pathlib import Path
from django.apps import AppConfig
from django.db.backends.signals import connection_created


def protect_database(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    name = str(connection.settings_dict["NAME"])
    if name == ":memory:" or name.startswith("file:"):
        return
    path = Path(name)
    if path.exists():
        path.chmod(0o600)


class OrdersConfig(AppConfig):
    name = "orders"

    def ready(self):
        connection_created.connect(protect_database, dispatch_uid="protect-coffee-db")
