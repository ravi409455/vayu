"""Load test: ~200 mixed users (REQUIREMENTS: p95 < 500 ms). Run on STAGING, never in CI.

    uvx locust -f perf/locustfile.py --host https://vayu-staging.carcid.in \
        --users 200 --spawn-rate 10 --run-time 10m --headless

Credentials come from the environment (never from this file):
    LOAD_OPS_USER / LOAD_OPS_PASSWORD, LOAD_EXPERT_USER / LOAD_EXPERT_PASSWORD

Sign-in allows 20 tries a minute from one address, and every simulated user comes from this one
laptop: so each kind signs in ONCE and all its users share that session (web) or token (phone,
valid 30 minutes: keep runs shorter). Otherwise the test would fail on the sign-in limit, not on
speed (docs/plan-deploy.md 1.17).

Mix: 25 Ops (board, search, booking, dashboards) and 175 experts (job list, one job) - the
expert phones mostly sync lists and upload, which the API only signs, so they stay light."""
import os
import random

from gevent.lock import Semaphore
from locust import HttpUser, between, task

_signed_in: dict[str, tuple[dict, dict]] = {}   # kind -> (cookies, headers), shared by its users
_one_at_a_time = Semaphore()


def login(client, user_env: str, pass_env: str, client_kind: str = "web") -> None:
    with _one_at_a_time:
        if client_kind not in _signed_in:
            r = client.post("/api/v1/auth/login", json={"username": os.environ[user_env], "password": os.environ[pass_env], "client": client_kind})
            r.raise_for_status()
            if client_kind == "web":
                headers = {"X-CSRFToken": client.cookies.get("csrftoken", "")}
            else:  # the phone: a bearer token, as the app sends it
                headers = {"Authorization": f"Bearer {r.json()['access']}"}
            _signed_in[client_kind] = (client.cookies.get_dict(), headers)
    cookies, headers = _signed_in[client_kind]
    client.cookies.update(cookies)
    client.headers.update(headers)


class OpsUser(HttpUser):
    weight = 25
    wait_time = between(2, 6)

    def on_start(self):
        login(self.client, "LOAD_OPS_USER", "LOAD_OPS_PASSWORD")
        self.ids: list[str] = []

    @task(5)
    def board(self):
        r = self.client.get("/api/v1/bookings", name="/bookings")
        if r.ok:
            self.ids = [b["id"] for b in r.json().get("results", [])]

    @task(3)
    def open_booking(self):
        if self.ids:
            i = random.choice(self.ids)
            self.client.get(f"/api/v1/bookings/{i}", name="/bookings/[id]")
            self.client.get(f"/api/v1/bookings/{i}/inspections", name="/bookings/[id]/inspections")

    @task(2)
    def search(self):
        self.client.get("/api/v1/bookings", params={"search": random.choice(["SA", "VI", "Asha", "9876"])}, name="/bookings?search")

    @task(1)
    def dashboard(self):
        self.client.get("/api/v1/dashboards/volume", params={"group": "day", "by": "type"}, name="/dashboards/volume")


class ExpertUser(HttpUser):
    weight = 175
    wait_time = between(5, 15)

    def on_start(self):
        # the expert's real path is the phone (F-083): it signs in as the app and syncs
        login(self.client, "LOAD_EXPERT_USER", "LOAD_EXPERT_PASSWORD", client_kind="mobile")
        self.ids: list[str] = []

    @task(4)
    def sync(self):
        r = self.client.get("/api/v1/sync/jobs", name="/sync/jobs")
        if r.ok:
            self.ids = [j["id"] for j in r.json().get("jobs", [])]

    @task(2)
    def one_job(self):
        if self.ids:
            self.client.get(f"/api/v1/bookings/{random.choice(self.ids)}", name="/bookings/[id] (expert)")

    @task(1)
    def me(self):
        self.client.get("/api/v1/auth/me", name="/auth/me")
