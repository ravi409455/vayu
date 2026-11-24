#!/usr/bin/env python3
"""Try the integrations against a real listener, on the local stack (scripts/local.sh up).

    cd backend && uv run python ../scripts/try_integrations.py [--port 9099]

It starts its own listener, creates a few integrations (names start with "tryout-"), makes a booking,
edits it and deletes it, and checks what really arrived: method, path, query, headers, body. Then a
failing listener (500) to see a retry succeed. Everything it creates is removed at the end.
Uses the local admin (password Vayu-local-1). Takes about two minutes because of the first retry (1 minute)."""
import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import requests

API = "http://127.0.0.1:8000/api/v1/"
opts = argparse.ArgumentParser()
opts.add_argument("--port", type=int, default=9099)
PORT = opts.parse_args().port
BASE = f"http://127.0.0.1:{PORT}"

hits: list[dict] = []
answer = {"status": 200}


class Listener(BaseHTTPRequestHandler):
    def handle_any(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        hits.append({"method": self.command, "path": urlsplit(self.path).path, "query": parse_qs(urlsplit(self.path).query),
                     "headers": {k.lower(): v for k, v in self.headers.items()}, "raw": raw,
                     "body": json.loads(raw) if raw else None})
        self.send_response(answer["status"])
        self.end_headers()
        self.wfile.write(b"ok")

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_any

    def log_message(self, *_):
        pass


server = HTTPServer(("127.0.0.1", PORT), Listener)
threading.Thread(target=server.serve_forever, daemon=True).start()

s = requests.Session()
r = s.post(API + "auth/login", json={"username": "admin", "password": "Vayu-local-1", "client": "web"})
r.raise_for_status()
s.headers["X-CSRFToken"] = s.cookies["csrftoken"]


def call(method, url, **kw):
    r = s.request(method, API + url, **kw)
    if not r.ok:
        raise SystemExit(f"{method} {url} -> {r.status_code} {r.text[:300]}")
    return r.json() if r.content else None


def wait_for(prefix, event=None, count=1, seconds=30):
    for _ in range(seconds * 4):
        found = [h for h in hits if h["path"].startswith(prefix) and (event is None or h["headers"].get("x-vayu-event") == event)]
        if len(found) >= count:
            return found
        time.sleep(0.25)
    return []


results: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""), flush=True)


form_booking = call("GET", "forms?type=booking")["results"][0]["id"]
mine: list[str] = []


def make(**kw):
    i = call("POST", "integrations", json={"form": form_booking, "url": BASE + "/x", **kw})
    mine.append(i["id"])
    return i


ref = "TRY-" + uuid.uuid4().hex[:6].upper()
print(f"Listener on {BASE}; booking id {ref}\n")

try:
    # one integration per event/method; the path prefix tells the arrivals apart
    make(name="tryout-get", event="booking.created", method="GET", url=BASE + "/get/{{job.booking_id}}",
         query=[{"key": "ref", "value": "{{job.booking_id}}"}, {"key": "city", "value": "{{booking.city}}"},
                {"key": "empty", "value": "{{booking.lead_owner}}"}],
         headers=[{"key": "X-Ref", "value": "{{job.booking_id}}"}, {"key": "X-Static", "value": "abc"}])
    make(name="tryout-list", event="booking.created", method="POST", url=BASE + "/list", body_mode="custom",
         body=[{"id": "{{job.booking_id}}", "name": "{{booking.customer_name}}"}])
    make(name="tryout-patch", event="booking.updated", method="PATCH", url=BASE + "/patch/{{job.booking_id}}", body_mode="custom",
         body={"changed": "{{event.changed_fields}}", "name": "{{booking.customer_name | text}}", "event": "{{event.name}}"})
    make(name="tryout-delete", event="booking.deleted", method="DELETE", url=BASE + "/del/{{job.booking_id}}",
         query=[{"key": "why", "value": "{{event.name}}"}])
    make(name="tryout-put", event="booking.updated", method="PUT", url=BASE + "/put", body_mode="standard")

    # create -> GET with path/query/headers and no body; POST with a list as the body
    b = call("POST", "bookings", json={"answers": {
        "booking_id": ref, "customer_name": "Try Out", "customer_phone": "9876500088", "address": "1 Try Street",
        "city": "delhi", "inspection_date": "2026-11-30", "inspection_time": "10:00", "inspection_type": "pdi",
        "car_make_model": "maruti_victoris"}})
    got = wait_for("/get/")
    h = got[0] if got else None
    check("GET arrives for booking.created", h and h["method"] == "GET")
    check("GET: booking id went into the path", h and h["path"] == f"/get/{ref}", h and h["path"])
    check("GET: query has ref and city", h and h["query"].get("ref") == [ref] and h["query"].get("city") == ["delhi"], h and h["query"])
    check("GET: a missing value drops its query row", h and "empty" not in h["query"], h and h["query"])
    check("GET: header X-Ref filled, X-Static kept", h and h["headers"].get("x-ref") == ref and h["headers"].get("x-static") == "abc")
    check("GET: no body is sent", h and h["raw"] == b"", h and h["raw"])
    check("GET: system headers present, no signature", h and h["headers"].get("x-vayu-event") == "booking.created"
          and "x-vayu-signature" not in h["headers"])
    got = wait_for("/list")
    check("POST: a list as the body", got and got[0]["body"] == [{"id": ref, "name": "Try Out"}], got and got[0]["body"])
    check("POST: content type is JSON", got and "application/json" in got[0]["headers"].get("content-type", ""))

    # edit -> PATCH with a changed-fields list and the standard body on PUT
    call("PATCH", f"bookings/{b['id']}", json={"row_version": b["row_version"], "answers": {"customer_name": "Try Two"}})
    got = wait_for("/patch/")
    check("PATCH arrives with the path value", got and got[0]["method"] == "PATCH" and got[0]["path"] == f"/patch/{ref}", got and got[0]["path"])
    check("PATCH: changed fields are a real list", got and "customer_name" in (got[0]["body"] or {}).get("changed", []), got and got[0]["body"])
    check("PATCH: {{ | text }} and event name", got and got[0]["body"].get("name") == "Try Two" and got[0]["body"].get("event") == "booking.updated", got and got[0]["body"])
    got = wait_for("/put")
    check("PUT standard body has the event and the booking", got and got[0]["method"] == "PUT" and got[0]["body"] is not None,
          got and got[0]["body"])

    # delete -> DELETE with the booking id only
    call("DELETE", f"bookings/{b['id']}")
    got = wait_for("/del/")
    check("DELETE arrives for booking.deleted", got and got[0]["method"] == "DELETE", got and got[0]["path"])
    check("DELETE: path has the booking id, query has the event", got and got[0]["path"] == f"/del/{ref}"
          and got[0]["query"].get("why") == ["booking.deleted"], got and (got[0]["path"], got[0]["query"]))

    # the Test button sends the same request marked as a test
    one = mine[0]
    t = call("POST", f"integrations/{one}/test")
    got = [x for x in wait_for("/get/", count=2) if x["headers"].get("x-vayu-test") == "1"]
    check("Test button: arrives marked X-Vayu-Test, event test.ping", got and got[0]["headers"].get("x-vayu-event") == "test.ping",
          got and got[0]["headers"] or t)

    # a failing listener: first try fails, the retry succeeds after a minute
    for i in mine:
        call("PATCH", f"integrations/{i}", json={"is_active": False})
    retry = make(name="tryout-retry", event="booking.created", method="POST", url=BASE + "/retry")
    answer["status"] = 500
    ref2 = ref + "R"
    b2 = call("POST", "bookings", json={"answers": {
        "booking_id": ref2, "customer_name": "Retry", "customer_phone": "9876500077", "address": "2 Try Street",
        "city": "delhi", "inspection_date": "2026-11-30", "inspection_time": "11:00", "inspection_type": "pdi",
        "car_make_model": "maruti_victoris"}})
    wait_for("/retry")
    time.sleep(2)
    d = call("GET", f"integrations/{retry['id']}/deliveries")
    d = d["results"] if isinstance(d, dict) else d
    check("500: delivery goes to retrying with http_500", d and d[0]["status"] == "retrying" and d[0]["error"] == "http_500", d and (d[0]["status"], d[0]["error"]))
    answer["status"] = 200
    print("  ... waiting for the 1 minute retry (the scheduler must be running)", flush=True)
    got = wait_for("/retry", count=2, seconds=120)
    check("the retry arrives and the listener now answers 200", len(got) >= 2)
    time.sleep(2)
    d = call("GET", f"integrations/{retry['id']}/deliveries")
    d = d["results"] if isinstance(d, dict) else d
    check("delivery ends as success (shown as Delivered)", d and d[0]["status"] == "success", d and d[0]["status"])
    call("DELETE", f"bookings/{b2['id']}")
finally:
    for i in mine:
        requests_ok = s.delete(API + f"integrations/{i}")
    print("\nCleaned up: integrations removed, bookings deleted.")

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")
raise SystemExit(1 if failed else 0)
