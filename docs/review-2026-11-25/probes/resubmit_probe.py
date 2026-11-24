"""Probe: can an expert submit a second inspection on their own completed booking (REVIEW- data)?"""
import hashlib
import io
import sys
import time
import uuid
from datetime import date

import requests
from PIL import Image

API = "http://localhost:8000/api/v1"
PW = "Vayu-local-1"


def login(user):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"username": user, "password": PW, "client": "web"})
    r.raise_for_status()
    s.headers["X-CSRFToken"] = s.cookies["csrftoken"]
    return s


def ok(r):
    if r.status_code >= 400:
        print("FAIL", r.request.method, r.url, r.status_code, r.text[:500])
        sys.exit(1)
    return r.json() if r.content else None


ops, exp = login("ops"), login("expert")
tag = uuid.uuid4().hex[:6]
b = ok(ops.post(f"{API}/bookings", json={"answers": {
    "booking_id": f"REVIEW-SEC-{tag}", "customer_name": "REVIEW-Security probe",
    "customer_phone": "9876500000", "address": "REVIEW lane", "city": "delhi",
    "inspection_date": date.today().isoformat(), "inspection_time": "23:30",
    "inspection_type": "tour", "car_make_model": "hyundai_creta", "assigned_expert": 3}}))
bid = b["id"]
print("booking", b["booking_id"], bid, b["stage"])

# selfie for the check-in form
buf = io.BytesIO()
Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, "JPEG")
data = buf.getvalue()
m = ok(exp.post(f"{API}/media/initiate", json={
    "booking": bid, "field_key": "selfie", "kind": "photo", "content_type": "image/jpeg",
    "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
    "client_uuid": str(uuid.uuid4())}))
put = requests.put(m["parts"][0]["url"], data=data)
put.raise_for_status()
ok(exp.post(f"{API}/media/{m['id']}/complete",
            json={"parts": [{"part_number": 1, "etag": put.headers["ETag"]}]}))
for _ in range(30):
    if ok(exp.get(f"{API}/media/{m['id']}"))["status"] == "verified":
        break
    time.sleep(1)
start = ok(exp.post(f"{API}/bookings/{bid}/start", json={
    "client_uuid": str(uuid.uuid4()), "start_answers": {"selfie": [m["id"]]}}))
form_version = start["inspection"]["form_version"]


def submit(chassis):
    return exp.post(f"{API}/bookings/{bid}/submit", json={
        "client_submission_uuid": str(uuid.uuid4()), "form_version": form_version,
        "answers": {"start": {"selfie": [m["id"]]},
                    "inspection": {"chassis_no": chassis, "registration_no": "DL01REVIEW",
                                   "odometer": 1000, "bonnet": "ok"},
                    "end": {"taking_payment": False}}})


s1 = ok(submit("REVIEW-GENUINE"))
print("first submit -> stage", s1["booking"]["stage"], "inspection", s1["inspection"]["id"])
time.sleep(3)
print("stage now", ok(ops.get(f"{API}/bookings/{bid}"))["stage"])

r2 = submit("REVIEW-TAMPERED")
print("second submit by expert ->", r2.status_code, r2.text[:200])
time.sleep(3)
insps = ok(ops.get(f"{API}/bookings/{bid}/inspections"))
for i in insps:
    print("inspection", i["id"], i["status"], i["submitted_at"], i["answers"]["inspection"].get("chassis_no"))
print("booking chassis_no seen by Ops:", ok(ops.get(f"{API}/bookings/{bid}"))["stage"])
