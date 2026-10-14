import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL = BASE_DIR / ".local"
LOCAL.mkdir(mode=0o700, exist_ok=True)
LOCAL.chmod(0o700)
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY; never commit it.")
ALLOWED_HOSTS = os.getenv(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
).split(",")
# The hosting platform supplies its assigned public hostname.
render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname:
    ALLOWED_HOSTS.append(render_hostname)
CSRF_TRUSTED_ORIGINS = [
    x.strip() for x in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()
]
if render_hostname:
    CSRF_TRUSTED_ORIGINS.append("https://" + render_hostname)
WORKER_HEARTBEAT_PATH = os.getenv("WORKER_HEARTBEAT_PATH", "")
REQUIRE_WORKER_HEARTBEAT = os.getenv("REQUIRE_WORKER_HEARTBEAT", "0") == "1"
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.kakao",
    "orders",
]
SITE_ID = 1
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "coffee.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "coffee.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("DATABASE_PATH", str(LOCAL / "coffee.sqlite3")),
        "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 20},
    }
}
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login"
LOGIN_REDIRECT_URL = "/my/orders"
ACCOUNT_ADAPTER = "orders.adapters.ClosedAccountAdapter"
SOCIALACCOUNT_ADAPTER = "orders.adapters.KakaoAdapter"
SOCIALACCOUNT_AUTO_SIGNUP = True
ACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_PROVIDERS = {
    "kakao": {
        "APPS": [
            {
                "client_id": os.getenv("KAKAO_CLIENT_ID", ""),
                "secret": os.getenv("KAKAO_CLIENT_SECRET", ""),
                "key": "",
            }
        ]
    }
}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# Unapproved operating policies must remain gated.
POLICIES_APPROVED = os.getenv("POLICIES_APPROVED", "1") == "1"
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"
DATABASES["default"]["TEST"] = {"NAME": str(LOCAL / "test.sqlite3")}
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"capabilities": {"()": "orders.logging.RedactCapabilities"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "filters": ["capabilities"]}
    },
    "loggers": {
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 3600
# Trust this only behind a verified proxy that strips incoming X-Forwarded-Proto.
if os.getenv("TRUST_HTTPS_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
