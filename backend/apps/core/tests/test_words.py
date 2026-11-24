"""Words people read (docs/plan-leads-bookings-words.md): experts say "lead", Ops and Admin say
"booking", and "job" is never shown. Reads every text the server can send (messages, notification
titles, labels), not code names, docstrings or log lines, and fails on a slip."""
import ast
import re
from pathlib import Path

APPS = Path(__file__).resolve().parents[2]
# a word on its own: not a code name (job_id), a path (/jobs) or a value name (job.booking_id)
JOB = re.compile(r"(?<![\w\-/.:{$])jobs?(?![\w\-/}]|[.:]\w)", re.I)
SKIP_CALLS = {"debug", "info", "warning", "error", "exception", "getLogger"}   # log lines


def _texts(tree: ast.AST):
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and n.body and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)}
    logged = {id(a) for n in ast.walk(tree) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute) and n.func.attr in SKIP_CALLS
              for arg in n.args for a in ast.walk(arg)}
    for n in ast.walk(tree):
        if (isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
                and id(n) not in logged):
            t = n.value.strip()
            # one lowercase word with nothing around it is a code key; " job" in an f-string is not
            if t and (re.search(r"\s", n.value) or t[:1].isupper()):
                yield n.lineno, t


def test_server_texts_never_say_job():
    slips = []
    for f in APPS.rglob("*.py"):
        rel = f.relative_to(APPS).as_posix()
        if "/tests/" in rel or "/migrations/" in rel or "/management/" in rel:
            continue
        for line, text in _texts(ast.parse(f.read_text())):
            if JOB.search(text):
                slips.append(f"{rel}:{line}: {text}")
    assert slips == []


def test_old_new_job_notifications_are_rewritten(db):
    from importlib import import_module

    from django.apps import apps as django_apps

    from apps.accounts.models import User
    from apps.notify.models import Notification

    u = User.objects.create_user(username="ex1", password="x", role="expert")
    old = Notification.objects.create(user=u, kind="assigned", title="New job: DEMO-1")
    other = Notification.objects.create(user=u, kind="changed", title="New job: is a phrase")
    import_module("apps.notify.migrations.0002_new_lead_titles").rename(django_apps, None)
    old.refresh_from_db()
    other.refresh_from_db()
    assert old.title == "New lead: DEMO-1" and other.title == "New job: is a phrase"
