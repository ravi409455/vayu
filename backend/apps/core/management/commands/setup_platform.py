"""Puts the Car C.I.D. setup on a server: master lists, the booking / check-in / wrap-up forms, the
PDI, Used Car and EV inspection forms (each from its own Clappia app, docs/clappia/README.md),
their Key Checks, ratings and PDF reports, and the staff from a users file.

Safe on any server, production included: it never deletes anything and never adds test data.
Running it again changes nothing unless the setup itself changed (then it publishes a new
version; inspections already started keep theirs). Users already there are left as they are.

    python manage.py setup_platform --users staff.csv

staff.csv (see apps/core/setup/users.example.csv): username,name,role,phone,password
(role: admin | ops | expert; an empty password gets a random one, printed once, to be changed at
first sign-in)."""
import csv
import os
import secrets
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, User
from apps.core.setup import build, forms, lists, reports

ROLES = {r.value for r in Role}


def read_users(path: str) -> list[dict]:
    rows = list(csv.DictReader(Path(path).read_text(encoding="utf-8-sig").splitlines()))
    out = []
    for n, row in enumerate(rows, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        if not row.get("username"):
            continue
        if row.get("role") not in ROLES:
            raise CommandError(f"{path} line {n}: role must be one of {', '.join(sorted(ROLES))}.")
        out.append(row)
    return out


def add_users(rows: list[dict]) -> tuple[list[str], list[tuple[str, str]]]:
    """Creates the users not there yet. Returns (created usernames, [(username, password)] for
    the ones given a random password)."""
    made, printed = [], []
    for row in rows:
        if User.objects.filter(username__iexact=row["username"]).exists():
            continue
        password = row.get("password") or secrets.token_urlsafe(9)
        if not row.get("password"):
            printed.append((row["username"], password))
        User.objects.create_user(username=row["username"], password=password, role=row["role"],
                                 name=row.get("name", ""), phone=row.get("phone", ""),
                                 must_change_password=True)
        made.append(row["username"])
    return made, printed


class Command(BaseCommand):
    help = "Set up forms, reports, master lists and staff (safe on production; no test data)."

    def add_arguments(self, parser):
        parser.add_argument("--users", help="CSV of staff to create (username,name,role,phone,"
                                            "password)")

    def handle(self, *args, users=None, **options):
        rows = read_users(users) if users else []
        from apps.core.setup.testdata import remember_kind

        with transaction.atomic():
            remember_kind()                  # the database says what server it is (F-213)
            made, printed = add_users(rows)
            admin = User.objects.filter(role=Role.ADMIN, is_active=True).order_by("id").first()
            if admin is None:
                raise CommandError("No Admin yet: give a users file with at least one admin.")
            report = {"users added": len(made), "list items added": lists.apply()}
            report["booking"] = build.apply(admin, build.system_form("booking"), forms.booking())
            report["start"] = build.apply(admin, build.system_form("start"), forms.start())
            report["end"] = build.apply(admin, build.system_form("end"), forms.end(admin))
            for key, name, itype, _ in forms.INSPECTIONS:
                spec, extra = forms.inspection(key)
                form = build.ensure_form(admin, key=key, name=name, itype=itype)
                report[key] = build.apply(admin, form, spec, extra)
                report[f"{key} report"] = reports.apply(admin, key)
        for k, v in report.items():
            self.stdout.write(f"  {k}: {v}")
        if printed:                  # never into logs (F-233): a file only the operator can read
            path = f"{users}.passwords"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.writelines(f"{username}  {password}\n" for username, password in printed)
            self.stdout.write(self.style.WARNING(
                f"Passwords made for {len(printed)} user(s) are in {path} (readable by you only; "
                "they change them at first sign-in). Delete the file once handed out."))
        self.stdout.write(self.style.SUCCESS("Setup done."))
