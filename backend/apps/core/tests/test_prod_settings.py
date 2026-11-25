import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
BASE_ENV = {
    "PATH": os.environ["PATH"], "DJANGO_SECRET_KEY": "x" * 50, "DB_NAME": "n", "DB_USER": "u",
    "DB_PASSWORD": "p", "DB_HOST": "h", "REDIS_URL": "redis://h/0", "S3_BUCKET": "b",
    "S3_ACCESS_KEY_ID": "k", "S3_SECRET_ACCESS_KEY": "s",
    "DJANGO_SETTINGS_MODULE": "vayu.settings.prod",
}


def load_prod(**extra):
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=BACKEND, env={**BASE_ENV, **extra}, capture_output=True, text=True,
    )


def test_prod_refuses_to_start_without_sentry_dsn():
    r = load_prod()
    assert r.returncode != 0 and "SENTRY_DSN is required" in r.stderr


def test_prod_starts_with_dsn_and_enables_hsts():
    r = load_prod(SENTRY_DSN="https://k@o0.ingest.sentry.io/1", PUBLIC_BASE_URL="https://x.in")
    assert r.returncode == 0, r.stderr


def test_prod_refuses_to_start_without_its_public_address():
    """F-216: webhook links would point at localhost."""
    r = load_prod(SENTRY_DSN="https://k@o0.ingest.sentry.io/1")
    assert r.returncode != 0 and "PUBLIC_BASE_URL" in r.stderr


def test_the_access_log_drops_query_strings_and_token_paths():
    """F-074 / F-211."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("gconf", BACKEND / "gunicorn.conf.py")
    assert spec and spec.loader
    conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conf)
    assert "%(q)s" not in conf.access_log_format and "%(r)s" not in conf.access_log_format
    assert conf.TOKEN.sub(r"/\1/<token>", "/api/v1/verify/AbC-123/photos") == \
        "/api/v1/verify/<token>/photos"
    assert conf.TOKEN.sub(r"/\1/<token>", "/api/v1/zips/x.y:z") == "/api/v1/zips/<token>"
    assert conf.TOKEN.sub(r"/\1/<token>", "/api/v1/bookings") == "/api/v1/bookings"


def test_coded_error_payload_keeps_json_types():
    from apps.core.errors import CodedError

    e = CodedError("X", "msg", 409, row_version=3, items=[1, {"a": 2}])
    assert e.detail == {"code": "X", "detail": "msg", "row_version": 3, "items": [1, {"a": 2}]}
    assert e.status_code == 409


def test_prod_requires_storage_settings():
    env = {k: v for k, v in BASE_ENV.items() if k != "S3_BUCKET"}
    r = subprocess.run([sys.executable, "-c", "import django; django.setup()"], cwd=BACKEND,
                       env={**env, "SENTRY_DSN": "https://k@o0.ingest.sentry.io/1",
                            "PUBLIC_BASE_URL": "https://x.in"},
                       capture_output=True, text=True)
    assert r.returncode != 0 and "S3_BUCKET" in r.stderr
