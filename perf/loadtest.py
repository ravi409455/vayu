"""Load test (docs/plan-load-test.md): the owner's real day, run against a test server.

    uv run --with locust --with pillow locust -f perf/loadtest.py --headless \
        --host https://localhost -u 58 -r 2 --run-time 90m

Needs LT_DATA (the JSON `loadtest_prepare` wrote: logins, API key, today's bookings, answer
templates) and LT_OUT (a folder for the logs). LT_TLS_VERIFY=0 for a local server's own
certificate. LT_MULT (default 1) multiplies every rate (the capacity test's steps).

Who does what (at 1x; every number is the owner's unless marked "assumed"):
- 50 phones: sign in once (before the clock: the sign-in limit is 20 a minute), register a push
  token (a fake one: Firebase answers "invalid", nobody receives anything), sync (assumed: every
  2 minutes, as an open app does) and send a heartbeat.
- 9 inspections an hour (one every 400 s, from the start): the phone starts the lead, uploads 100
  photos and 5 videos over 25 minutes (assumed pace), then submits. Files go straight to the file
  store through the upload links, as from the app.
- 5 Ops: Today, bookings, search, open a booking (assumed: one page every 5-15 s each), assign
  every booking the external system creates, and for each finished inspection 20 Key Check
  changes with 5 Regenerates over 30 minutes (assumed spread).
- The external system: 100 calls a minute, ~200 writes an hour (18 new bookings, the rest changes
  to bookings), the rest reads.
- Webhooks: the server sends them to perf/receiver.py, which times them.
Logs in LT_OUT: requests.csv (every call), pdf.csv (time to a ready PDF), uploads.csv (when each
file was sent, to time its check), inspections.csv. perf/report.py turns them into the results."""
import csv
import hashlib
import io
import json
import os
import random
import threading
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import gevent
import requests
import urllib3
from locust import HttpUser, between, constant_pacing, events, task

DATA = json.load(open(os.environ["LT_DATA"]))   # noqa: SIM115
OUT = os.environ["LT_OUT"]
VERIFY = os.environ.get("LT_TLS_VERIFY", "1") != "0"
MULT = float(os.environ.get("LT_MULT", "1"))
INSPECTION_EVERY = 400 / MULT          # 9 an hour at 1x
UPLOAD_MINUTES = float(os.environ.get("LT_UPLOAD_MINUTES", 25))   # assumed; smoke runs shorten it
REVIEW_MINUTES = float(os.environ.get("LT_REVIEW_MINUTES", 30))   # assumed; smoke runs shorten it
if not VERIFY:
    urllib3.disable_warnings()
os.makedirs(OUT, exist_ok=True)
_lock = threading.Lock()
_files: dict = {}
T0 = [0.0]


def log(name: str, *row) -> None:
    with _lock:
        if name not in _files:
            _files[name] = open(os.path.join(OUT, f"{name}.csv"), "a", newline="")  # noqa: SIM115
        csv.writer(_files[name]).writerow(row)
        _files[name].flush()


@events.request.add_listener
def _every_call(request_type, name, response_time, response_length, exception, response=None,
                **_):
    status = getattr(response, "status_code", "")
    log("requests", f"{time.time():.3f}", request_type, name, f"{response_time:.1f}",
        0 if exception else 1, status)


def today() -> str:
    """Today in India (bookings are dated in India time; the load server's clock is UTC)."""
    return datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()


@events.spawning_complete.add_listener
def _start(**_):
    """The clock starts once everyone has signed in (at the real limit of 20 a minute)."""
    T0[0] = time.time()
    log("run", f"{T0[0]:.3f}", "start", MULT)


# ------------------------------------------------------------------ files as the phone sends them

def _photo_base() -> bytes:
    """A 2048 px JPEG of about 500 KB (texture, so it does not compress to nothing)."""
    from PIL import Image

    rnd = random.Random(1)  # noqa: S311
    img = Image.blend(Image.effect_noise((2048, 1536), 40).convert("RGB"),
                      Image.new("RGB", (2048, 1536), tuple(rnd.randrange(256) for _ in range(3))),
                      0.6)
    buf = io.BytesIO()
    for q in (70, 60, 50, 40, 30):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q)
        if buf.tell() <= 560_000:
            break
    return buf.getvalue()


PHOTO = _photo_base()
VIDEO = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + os.urandom(10 * 1024 * 1024)


def unique(data: bytes) -> bytes:
    """Each file different (its own checksum), as real photos are: a few bytes after the end."""
    return data + uuid.uuid4().bytes


# ------------------------------------------------------------------ one phone

class Phone:
    def __init__(self, user: HttpUser, username: str):
        self.u, self.name = user, username
        self.have: set[str] = set()
        self.since = None
        r = user.client.post("/api/v1/auth/login", name="auth/login (phone)", json={
            "username": username, "password": DATA["password"], "client": "mobile",
            "device_name": f"loadtest {username}"})
        r.raise_for_status()
        self.h = {"Authorization": f"Bearer {r.json()['access']}"}
        self.refresh = r.json().get("refresh")
        self.post("devices/push-token", {"token": f"fake-{uuid.uuid4().hex}"}, "devices/push-token")

    def call(self, method, path, name, **kw):
        url = f"/api/v1/{path}"
        with self.u.client.request(method, url, headers=self.h, name=name, catch_response=True,
                                   **kw) as r:
            if r.status_code != 401 or not self.refresh:
                if not r.ok:
                    r.failure(f"HTTP {r.status_code}")
                return r
            # the 30-minute access token ran out: the app renews it and asks again, so this
            # answer is expected, not an error (the renewal and the retry are counted)
            r.success()
        t = self.u.client.post("/api/v1/auth/refresh", json={"refresh": self.refresh},
                               name="auth/refresh")
        if t.ok:
            self.h = {"Authorization": f"Bearer {t.json()['access']}"}
            self.refresh = t.json().get("refresh", self.refresh)
        return self.u.client.request(method, url, headers=self.h, name=name, **kw)

    def get(self, path, name, **kw):
        return self.call("GET", path, name, **kw)

    def post(self, path, body, name):
        return self.call("POST", path, name, json=body)

    def sync(self):
        q = {"have": ",".join(sorted(self.have))}
        if self.since:
            q["since"] = self.since
        r = self.get("sync/jobs", "sync/jobs", params=q)
        if r.ok:
            j = r.json()
            self.since = j["server_time"]
            self.have |= set(j.get("forms", {}))
        self.post("devices/heartbeat", {"app_version": 3, "drafts": 0, "files": 0},
                  "devices/heartbeat")

    def upload(self, booking: str, field: str, kind: str) -> str:
        data = unique(PHOTO if kind == "photo" else VIDEO)
        r = self.post("media/initiate", {
            "booking": booking, "client_uuid": str(uuid.uuid4()), "field_key": field, "kind": kind,
            "content_type": "image/jpeg" if kind == "photo" else "video/mp4", "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "source": "camera"}, "media/initiate")
        r.raise_for_status()
        init = r.json()
        parts = []
        for p in init["parts"]:                       # straight to the file store, as the app does
            size = init["part_size"]
            chunk = data[(p["part_number"] - 1) * size:p["part_number"] * size]
            t = time.time()
            put = requests.put(p["url"], data=chunk, timeout=120, verify=VERIFY)
            events.request.fire(request_type="PUT", name="file store PUT (not the server)",
                                response_time=(time.time() - t) * 1000, response_length=len(chunk),
                                exception=None if put.ok else Exception(put.status_code))
            parts.append({"part_number": p["part_number"], "etag": put.headers.get("ETag", "")})
        r = self.post(f"media/{init['id']}/complete", {"parts": parts}, "media/[id]/complete")
        r.raise_for_status()
        log("uploads", f"{time.time():.3f}", init["id"], kind, len(data))
        return init["id"]

    def files_for(self, booking: str, part: str) -> dict:
        tpl = DATA["templates"][part]
        answers = json.loads(json.dumps(tpl["answers"]))
        for field, n in tpl["files"].items():
            asked = answers.get(field, [])
            kind = "video" if any(str(x).startswith("@video") for x in asked) else "photo"
            answers[field] = [self.upload(booking, field, kind) for _ in range(n)]
        return answers

    def inspect(self, job: dict) -> None:
        """One lead: start, files over UPLOAD_MINUTES, submit."""
        b = job["id"]
        log("inspections", f"{time.time():.3f}", b, "begin")
        start = self.files_for(b, "start")
        r = self.post(f"bookings/{b}/start", {"client_uuid": str(uuid.uuid4()),
                                              "inspection_type": DATA.get("inspection_type", "pdi"),
                                              "start_answers": start},
                      "bookings/[id]/start")
        r.raise_for_status()
        # 2 of every 9 inspections are 150-photo reports (the old requirement's worst case)
        big = job.get("n", 0) % 9 in (3, 7) and "inspection_big" in DATA["templates"]
        tpl = DATA["templates"]["inspection_big" if big else "inspection"]
        answers = json.loads(json.dumps(tpl["answers"]))
        todo = [(f, "video" if str(answers[f][0]).startswith("@video") else "photo")
                for f, n in tpl["files"].items() for _ in range(n)]
        pause = UPLOAD_MINUTES * 60 / max(len(todo), 1)
        ids: dict[str, list] = {}
        for field, kind in todo:
            ids.setdefault(field, []).append(self.upload(b, field, kind))
            gevent.sleep(pause)
        answers.update(ids)
        end = self.files_for(b, "end")
        r = self.post(f"bookings/{b}/submit", {"client_submission_uuid": str(uuid.uuid4()),
                                               "answers": {"inspection": answers, "start": start,
                                                           "end": end}},
                      "bookings/[id]/submit")
        r.raise_for_status()
        log("inspections", f"{time.time():.3f}", b, "submitted", len(todo), "big" if big else "")
        REVIEWS.append((b, time.time()))


REVIEWS: list = []           # (booking, submitted at): the Ops pick them up


class PhoneUser(HttpUser):
    weight = 50
    wait_time = constant_pacing(120)          # assumed: an open app syncs about every 2 minutes
    _n = iter(range(10_000))

    def on_start(self):
        self.verify = VERIFY
        self.client.verify = VERIFY
        i = next(self._n)
        if i >= len(DATA["experts"]):   # never two phones on one login (it signs the other out)
            self.phone = None
            return
        self.phone = Phone(self, DATA["experts"][i])
        mine = [(k, j) for k, j in enumerate(DATA["today"]) if j["expert"] == self.phone.name]
        for k, job in mine:
            gevent.spawn(self._later, k * INSPECTION_EVERY, {**job, "n": k})

    def _later(self, delay: float, job: dict) -> None:
        while not T0[0]:
            gevent.sleep(1)
        gevent.sleep(max(0.0, T0[0] + delay - time.time()))
        try:
            self.phone.inspect(job)
        except Exception as e:  # noqa: BLE001 - counted, the test goes on
            log("inspections", f"{time.time():.3f}", job["id"], f"failed: {e}")

    @task
    def sync(self):
        if self.phone:
            self.phone.sync()


# ------------------------------------------------------------------ Ops

class OpsUser(HttpUser):
    weight = 5
    wait_time = between(5, 15)                 # assumed: a page every 5-15 s per person
    _n = iter(range(10_000))

    def on_start(self):
        self.client.verify = VERIFY
        name = DATA["ops"][next(self._n) % len(DATA["ops"])]
        r = self.client.post("/api/v1/auth/login", name="auth/login (web)",
                             json={"username": name, "password": DATA["password"], "client": "web"})
        r.raise_for_status()
        self.client.headers["X-CSRFToken"] = self.client.cookies.get("csrftoken", "")
        # a browser says which page a change comes from; Django refuses https changes without it
        self.client.headers["Referer"] = f"{self.host}/"
        self.client.headers["Origin"] = self.host
        self.ids: list[str] = [j["id"] for j in DATA["today"]]

    def api(self, method, path, name, **kw):
        return self.client.request(method, f"/api/v1/{path}", name=name, **kw)

    @task(4)
    def today(self):
        self.api("GET", "dashboards/summary", "dashboards/summary")
        # what the Today page asks (web/src/pages/ops/Today.tsx): today's bookings by schedule
        r = self.api("GET", "bookings", "bookings (Today)",
                     params={"date_from": today(), "date_to": today(), "order": "schedule",
                             "page_size": 200})
        if r.ok:
            self.ids = [b["id"] for b in r.json().get("results", [])] or self.ids

    @task(2)
    def search(self):
        self.api("GET", "bookings", "bookings?search",
                 params={"search": random.choice(["LT-H00", "Asha", "98765", "MH12"])})  # noqa: S311

    @task(3)
    def open_booking(self):
        if self.ids:
            b = random.choice(self.ids)  # noqa: S311
            self.api("GET", f"bookings/{b}", "bookings/[id]")
            self.api("GET", f"bookings/{b}/inspections", "bookings/[id]/inspections")

    @task(2)
    def duties(self):
        """Assign what the external system created; review what the phones finished."""
        while NEW_BOOKINGS:
            ref = NEW_BOOKINGS.pop(0)
            expert = random.choice(DATA["expert_ids"])  # noqa: S311
            self.api("POST", f"bookings/{ref}/assign", "bookings/[id]/assign",
                     json={"expert": expert})
        while REVIEWS:
            b, submitted = REVIEWS.pop(0)
            gevent.spawn(self.review, b, submitted)

    def report(self, b):
        r = self.api("GET", f"bookings/{b}/report", "bookings/[id]/report")
        return r.json() if r.ok else None

    def wait_pdf(self, b, after_revision: int, since: float, what: str) -> None:
        while time.time() - since < 600:
            rep = self.report(b)
            if rep and rep.get("status") == "ready" and rep.get("revision", 0) > after_revision:
                log("pdf", f"{time.time():.3f}", b, what, f"{time.time() - since:.1f}")
                return
            gevent.sleep(2)
        log("pdf", f"{time.time():.3f}", b, what, "timeout")

    def review(self, b: str, submitted: float) -> None:
        """The first PDF (made by itself), then 20 Key Check changes with a Regenerate after every
        4th, over REVIEW_MINUTES."""
        self.wait_pdf(b, 0, submitted, "first")
        r = self.api("GET", f"bookings/{b}/inspections", "bookings/[id]/inspections")
        rows = r.json() if r.ok else []
        rows = rows.get("results", []) if isinstance(rows, dict) else rows
        insp = next((i for i in rows if i.get("status") == "submitted"), None)
        if insp is None:
            return
        checks = list(((insp.get("scores") or {}).get("key_checks") or {}).keys())
        rv = insp.get("row_version", 0)
        pause = REVIEW_MINUTES * 60 / 20
        for n in range(1, 21):
            gevent.sleep(pause)
            body = {"row_version": rv}
            if checks:
                body["key_checks"] = {random.choice(checks): f"Checked by Ops ({n})"}  # noqa: S311
            else:
                body["overall"] = random.choice(["excellent", "good"])  # noqa: S311
            r = self.api("PATCH", f"inspections/{insp['id']}/overrides",
                         "inspections/[id]/overrides",
                         json=body)
            if r.ok:
                rv = r.json().get("row_version", rv + 1)
            if n % 4 == 0:
                before = (self.report(b) or {}).get("revision", 0)
                t = time.time()
                self.api("POST", f"bookings/{b}/report/regenerate",
                         "bookings/[id]/report/regenerate")
                self.wait_pdf(b, before, t, "regenerate")


# ------------------------------------------------------------------ the external system

NEW_BOOKINGS: list = []


class ExternalSystem(HttpUser):
    """100 calls a minute from 3 of these (one call every 1.8 s each); ~200 writes an hour."""
    weight = 3
    fixed_count = 3
    wait_time = constant_pacing(1.8 / MULT)
    _n = iter(range(1_000_000))

    def on_start(self):
        self.client.verify = VERIFY
        self.client.headers["X-API-Key"] = DATA["api_key"]
        self.live = [j["ref"] for j in DATA["today"]]        # changes only to live bookings
        self.refs = self.live + DATA["done_refs"][:100]
        self.done = DATA["done_refs"] or self.refs

    @task
    def call(self):
        n = next(self._n)
        if n % 333 == 0:                                       # 6000 calls an hour: 18 creates
            self.create()
        elif random.random() < 182 / 6000:                    # noqa: S311 - ~182 changes an hour
            self.change()
        else:
            self.read()

    def create(self):
        ref = f"LT-X{uuid.uuid4().hex[:10].upper()}"
        answers = {**DATA["booking_answers"], "booking_id": ref,
                   "inspection_date": today(), "inspection_time": "18:00"}
        r = self.client.post("/api/v1/ext/bookings", name="ext/bookings (create)",
                             json={"answers": answers})
        if r.ok:
            self.refs.append(ref)
            self.live.append(ref)
            NEW_BOOKINGS.append(r.json()["id"])

    def change(self):
        ref = random.choice(self.live)  # noqa: S311
        self.client.patch(f"/api/v1/ext/bookings/{ref}", name="ext/bookings/[ref] (change)",
                          json={"answers": {"address": f"{random.randint(1, 99)} Test Road"}})  # noqa: S311

    def read(self):
        pick = random.random()  # noqa: S311
        if pick < 0.4:
            self.client.get("/api/v1/ext/bookings", name="ext/bookings (list)",
                            params={"page_size": 50})
        elif pick < 0.8:
            self.client.get(f"/api/v1/ext/bookings/{random.choice(self.refs)}",  # noqa: S311
                            name="ext/bookings/[ref]")
        else:
            self.client.get(f"/api/v1/ext/bookings/{random.choice(self.done)}/inspection",  # noqa: S311
                            name="ext/bookings/[ref]/inspection")
