"""Load test: ~200 mixed users (REQUIREMENTS: p95 < 500 ms). Run on STAGING, never in CI.

    uvx locust -f perf/locustfile.py --host https://staging.carcid.in \
        --users 200 --spawn-rate 10 --run-time 10m --headless

Credentials come from the environment (never from this file):
    LOAD_OPS_USER / LOAD_OPS_PASSWORD, LOAD_EXPERT_USER / LOAD_EXPERT_PASSWORD

Mix: 25 Ops (board, search, booking, dashboards) and 175 experts (job list, one job) - the
expert phones mostly sync lists and upload, which the API only signs, so they stay light."""
import os
import random

from locust import HttpUser, between, task


def login(client, user_env: str, pass_env: str) -> None:
    r = client.post("/api/v1/auth/login", json={"username": os.environ[user_env], "password": os.environ[pass_env], "client": "web"})
    r.raise_for_status()
    client.headers["X-CSRFToken"] = client.cookies.get("csrftoken", "")


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
        login(self.client, "LOAD_EXPERT_USER", "LOAD_EXPERT_PASSWORD")
        self.ids: list[str] = []

    @task(4)
    def my_jobs(self):
        r = self.client.get("/api/v1/bookings", name="/bookings (expert)")
        if r.ok:
            self.ids = [b["id"] for b in r.json().get("results", [])]

    @task(2)
    def one_job(self):
        if self.ids:
            self.client.get(f"/api/v1/bookings/{random.choice(self.ids)}", name="/bookings/[id] (expert)")

    @task(1)
    def me(self):
        self.client.get("/api/v1/auth/me", name="/auth/me")
