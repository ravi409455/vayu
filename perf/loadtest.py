"""Load test (docs/plan-load-test.md): the owner's real day, run against a test server.

    uv run --with locust --with pillow locust -f perf/loadtest.py --headless \
        --host https://localhost -u 58 -r 2 --run-time 90m

Needs LT_DATA (the JSON `loadtest_prepare` wrote: logins, API key, today's bookings, answer
templates) and LT_OUT (a folder for the logs). LT_TLS_VERIFY=0 for a local server's own
certificate. LT_MULT (default 1) multiplies every rate. LT_STEPS (e.g. "1,2,3,4,6,8") makes it the
capacity test: one continuous run that steps the load up; each step lasts until its new users have
signed in, its new work has settled (LT_UPLOAD_MINUTES + LT_REVIEW_MINUTES) and LT_STEP_MINUTES
(default 15) have been measured; the measured windows go to run.csv ("step" rows).

Who does what (at 1x; every number is the owner's unless marked "assumed"):
- 50 phones: sign in once (before the clock: the sign-in limit is 20 a minute), register a push
  token (a fake one: Firebase answers "invalid", nobody receives anything), sync (assumed: every
  2 minutes, as an open app does) and send a heartbeat.
- 9 inspections an hour (one every 400 s, from the clock; a dispatcher gives each lead to its
  phone, or, for an unassigned lead, Ops assign it to a free phone): the phone starts it, uploads
  100 photos and 5 videos (15 on the test form) over LT_UPLOAD_MINUTES (default 25, assumed), then
  submits. Files go straight to the file store through the upload links, as from the app.
  LT_PHOTOS: a folder of real car photos (never in the repo); each is shrunk as the app does
  (2048 px, JPEG ~500-700 KB) and uploads pick one at random. Without it, one made-up photo.
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
from gevent.queue import Empty, Queue
from locust import HttpUser, LoadTestShape, between, constant, constant_pacing, events, task

DATA = json.load(open(os.environ["LT_DATA"]))   # noqa: SIM115
OUT = os.environ["LT_OUT"]
VERIFY = os.environ.get("LT_TLS_VERIFY", "1") != "0"
MULT = float(os.environ.get("LT_MULT", "1"))
STEPS = [float(x) for x in os.environ.get("LT_STEPS", "").split(",") if x.strip()]
STEP_MINUTES = float(os.environ.get("LT_STEP_MINUTES", 15))
CUR = [STEPS[0] if STEPS else MULT]    # the multiplier now (the capacity steps change it)
SIGNIN_RATE = 0.3                      # users a second: the server's 20-a-minute sign-in limit
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
    """The clock starts once everyone has signed in (at the real limit of 20 a minute); the
    capacity steps' later sign-ins do not move it."""
    if T0[0]:
        return
    T0[0] = time.time()
    log("run", f"{T0[0]:.3f}", "start", CUR[0])
    gevent.spawn(_dispatch)
    if STEPS:
        settle = (UPLOAD_MINUTES + REVIEW_MINUTES) * 60
        log("run", f"{T0[0]:.3f}", "step", STEPS[0], f"{T0[0] + settle:.3f}",
            f"{T0[0] + settle + STEP_MINUTES * 60:.3f}")


# ------------------------------------------------------------------ the dispatcher

PHONES: dict = {}            # username → its PhoneUser (signed in)
IDLE: Queue = Queue()        # usernames of phones with no lead
OPS_CLIENTS: list = []       # signed-in Ops users (one assigns the unassigned leads)


def _dispatch() -> None:
    """One lead every 400 s at 1× (9 an hour), at the rate of the moment. A lead already assigned
    goes to its expert's phone; an unassigned one is assigned by Ops to the first free phone."""
    ids = dict(zip(DATA["experts"], DATA["expert_ids"], strict=False))
    due = T0[0]
    for n, job in enumerate(DATA["today"]):
        gevent.sleep(max(0.0, due - time.time()))
        due = max(due, time.time()) + 400 / CUR[0]
        name = job.get("expert")
        if not name or name not in PHONES:
            try:
                name = IDLE.get(timeout=600)
            except Empty:
                log("inspections", f"{time.time():.3f}", job["id"], "failed: no free phone")
                continue
            ops = OPS_CLIENTS[n % len(OPS_CLIENTS)] if OPS_CLIENTS else None
            if ops is None or not ops.api("POST", f"bookings/{job['id']}/assign",
                                          "bookings/[id]/assign",
                                          json={"expert": ids[name]}).ok:
                IDLE.put(name)
                log("inspections", f"{time.time():.3f}", job["id"], "failed: could not assign")
                continue
        PHONES[name].jobs.put({**job, "n": n})


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


def _real_photos(folder: str) -> list[bytes]:
    """Real photos as the app sends them (Media.kt stampPhoto): upright, at most 2048 px,
    JPEG quality 85, 75 or 65, the first that fits 700 KB."""
    from PIL import Image, ImageOps

    out = []
    for name in sorted(os.listdir(folder)):
        if name.startswith(".") or not name.lower().endswith((".jpg", ".jpeg")):  # "._x.jpg": macOS
            continue
        img = ImageOps.exif_transpose(Image.open(os.path.join(folder, name))).convert("RGB")
        img.thumbnail((2048, 2048))
        for q in (85, 75, 65):
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=q)
            if buf.tell() <= 700_000:
                break
        out.append(buf.getvalue())
    if not out:
        raise SystemExit(f"LT_PHOTOS={folder} has no .jpg/.jpeg files")
    return out


PHOTOS = _real_photos(os.environ["LT_PHOTOS"]) if os.environ.get("LT_PHOTOS") else [_photo_base()]
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
        data = unique(random.choice(PHOTOS) if kind == "photo" else VIDEO)  # noqa: S311
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
            for attempt in range(4):           # a busy file store (503): retried, as the app does
                t = time.time()
                put = requests.put(p["url"], data=chunk, timeout=120, verify=VERIFY)
                events.request.fire(request_type="PUT", name="file store PUT (not the server)",
                                    response_time=(time.time() - t) * 1000,
                                    response_length=len(chunk),
                                    exception=None if put.ok else Exception(put.status_code))
                if put.ok or put.status_code < 500:
                    break
                time.sleep(2 ** attempt)
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
        self.jobs: Queue = Queue()
        PHONES[self.phone.name] = self
        gevent.spawn(self._work)
        IDLE.put(self.phone.name)

    def _work(self) -> None:
        """The leads the dispatcher gives this phone, one at a time."""
        while True:
            job = self.jobs.get()
            try:
                self.phone.inspect(job)
            except Exception as e:  # noqa: BLE001 - counted, the test goes on
                log("inspections", f"{time.time():.3f}", job["id"], f"failed: {e}")
            if self.jobs.empty():
                IDLE.put(self.phone.name)

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
        OPS_CLIENTS.append(self)

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
    """100 calls a minute from 3 of these (one call every 1.8 s each, at 1×; the rate of the
    moment in the capacity steps); ~200 writes an hour."""
    weight = 3
    fixed_count = 3
    wait_time = constant(0)
    _n = iter(range(1_000_000))

    def on_start(self):
        self.client.verify = VERIFY
        self.client.headers["X-API-Key"] = DATA["api_key"]
        self.live = [j["ref"] for j in DATA["today"]]        # changes only to live bookings
        self.refs = self.live + DATA["done_refs"][:100]
        self.done = DATA["done_refs"] or self.refs
        self.due = time.time()

    @task
    def call(self):
        gevent.sleep(max(0.0, self.due - time.time()))
        self.due = max(self.due, time.time() - 1.8) + 1.8 / CUR[0]
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


# ------------------------------------------------------------------ the capacity steps

if STEPS:
    class CapacitySteps(LoadTestShape):
        """LT_STEPS: 58 users per 1× (50 phones, 5 Ops, 3 external-system users), stepped up
        through one run. A step lasts while its new users sign in (at the real limit), its new
        work settles (an inspection's uploads and review) and LT_STEP_MINUTES are measured; the
        windows go to run.csv as ("step", k, from, to)."""

        def __init__(self):
            super().__init__()
            self.i = 0
            self.end = 0.0
            self.at_start = (0, 0)                     # requests, failures when the step began

        def _failing(self) -> bool:
            """More than 1% of the step's requests failed: a real failure, the climb stops."""
            s = self.runner.stats.total
            n, f = s.num_requests - self.at_start[0], s.num_failures - self.at_start[1]
            return n >= 200 and f / n > 0.01

        def tick(self):
            if not T0[0]:                              # before the clock: the first step's users
                return round(58 * STEPS[0]), SIGNIN_RATE
            settle = (UPLOAD_MINUTES + REVIEW_MINUTES) * 60
            if not self.end:
                self.end = T0[0] + settle + STEP_MINUTES * 60
            now = time.time()
            if now >= self.end:
                if self._failing():
                    log("run", f"{now:.3f}", "stopped", STEPS[self.i], "errors above 1%")
                    return None                        # a real failure: no higher step
                s = self.runner.stats.total
                self.at_start = (s.num_requests, s.num_failures)
                self.i += 1
                if self.i >= len(STEPS):
                    return None                        # the last step is measured: stop
                k, prev = STEPS[self.i], STEPS[self.i - 1]
                CUR[0] = k
                start = now + 58 * (k - prev) / SIGNIN_RATE + settle
                self.end = start + STEP_MINUTES * 60
                log("run", f"{now:.3f}", "step", k, f"{start:.3f}", f"{self.end:.3f}")
            return round(58 * STEPS[self.i]), SIGNIN_RATE

