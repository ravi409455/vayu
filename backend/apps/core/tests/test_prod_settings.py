import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
BASE_ENV = {
    "PATH": os.environ["PATH"], "DJANGO_SECRET_KEY": "x" * 50, "DB_NAME": "n", "DB_USER": "u",
    "DB_PASSWORD": "p", "DB_HOST": "h", "REDIS_URL": "redis://h/0",
    "DJANGO_SETTINGS_MODULE": "inspex.settings.prod",
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
    r = load_prod(SENTRY_DSN="https://k@o0.ingest.sentry.io/1")
    assert r.returncode == 0, r.stderr
