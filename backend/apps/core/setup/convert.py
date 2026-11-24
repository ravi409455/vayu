"""One-time conversion (used by `manage.py freeze_forms` only): turns the Clappia read-out into our
six form files in setup/frozen/, which the setup then reads. Each form from its own app
(docs/clappia/README.md):
booking ← BookingCreation 3.0; start (check-in) and end (wrap-up) ← the sections every inspection
app shares; PDI ← New Car 3.0; Used Car ← Used Car 3.0; EV ← EV 3.0. Never mix: an inspection
form takes questions, choices and rules only from its own app."""
from . import clappia

# (form key, name, inspection type, Clappia app)
INSPECTIONS = [("pdi", "PDI", "pdi", "new_car_3_0"),
               ("used_car", "Used Car", "used_car", "used_car_3_0"),
               ("ev", "EV", "ev", "ev_3_0")]
TYPE_VALUES = {"PDI": "pdi", "Used Car": "used_car", "EV": "ev"}

# Clappia fields that become our locked system fields (None: a double of one, left out)
BOOKING_SYSTEM = {
    "bookingid": {"key": "booking_id", "type": "short_text"},
    "customer_n": {"key": "customer_name", "type": "short_text"},
    "customer_p": {"key": "customer_phone", "type": "phone"},
    "inspection": {"key": "address", "type": "long_text"},
    "dateddmmyy": {"key": "inspection_date", "type": "date"},
    "timehhmm_a": {"key": "inspection_time", "type": "time"},
    "type_of_in": {"key": "inspection_type", "type": "form_choice", "values": TYPE_VALUES},
    "car": {"key": "car_make_model", "type": "master_list"},
    "car_inspec": {"key": "city", "type": "master_list"},
    "assignedexpert_id": {"key": "assigned_expert", "type": "user_picker"},
    "extra_conveyance": None,           # hidden on Clappia (shown only for booking "XYZ")
}
START_SYSTEM = {"inspector__1": {"key": "selfie", "type": "photo"},
                "current_lo": {"key": "checkin_gps", "type": "gps"},
                "date": {"key": "checkin_time", "type": "datetime"},
                "time": None}           # Clappia's date + time are our one "date and time"
END_SYSTEM = {"taking_pay": {"key": "taking_payment", "type": "yes_no"},
              "payment_am": {"key": "payment_amount", "type": "currency"},
              "payment_mo": {"key": "payment_mode", "type": "single_choice"},
              "payment_sc": {"key": "payment_screenshot", "type": "photo"}}
INSPECTION_SYSTEM = {"chassis_nu": {"key": "chassis_no", "type": "short_text"}}

# Ops-typed ratings on Clappia's "Report First Page" → our rating categories (the sections whose
# defects lower each one, from that app's own sections)
CATEGORIES = {
    "pdi": [("exterior", "Exterior", ["Exterior Body", "Body Frame Accidental Checklist"]),
            ("ac", "AC", ["Air Conditioning"]),
            ("electronics", "Electronics", ["Electrical and Interior", "Warning Lights"]),
            ("engine", "Engine", ["Engine", "Battery and Charging", "CNG", "OBD Scan",
                                  "Transmission and Clutch Pedal"]),
            ("tires", "Tires", ["Tyres", "Brakes", "Brakes and Steering", "Axle", "Suspension",
                                "UnderBody"])],
    "used_car": [("exterior", "Exterior", ["Exterior Body", "Body Frame Accidental Checklist"]),
                 ("ac", "AC", ["Air Conditioning"]),
                 ("drive_train", "Drive Train", ["Transmission and Clutch Pedal", "Axle",
                                                 "Brakes and Steering", "Brakes", "Suspension"]),
                 ("engine", "Engine", ["Engine (before test drive)",
                                       "Engine (after test drive)", "Battery and Charging",
                                       "CNG", "OBD Scan", "Electrical and Interior",
                                       "Warning Lights"]),
                 ("tires", "Tires", ["Tyres", "UnderBody"])],
    "ev": [("exterior", "Exterior", ["Exterior Body", "Body Frame Accidental Checklist"]),
           ("ac", "AC", ["Air Conditioning"]),
           ("electronics", "Electronics", ["Electrical and Interior", "Warning Lights"]),
           ("battery", "Battery", ["Battery, Charger and Hood", "Auxiliary Battery"]),
           ("tires", "Tires", ["Tyres", "Brakes", "Brakes and Steering", "Axle", "Suspension",
                               "UnderBody"])],
}


MONEY = {"final_amount", "advance_amount"}   # typed boxes on Clappia: money here


def booking() -> dict:
    spec = clappia.convert("booking_creation_3_0", ns="booking", system=BOOKING_SYSTEM)
    spec["pages"][0]["title"] = "Booking"
    for f in spec["pages"][0]["sections"][0]["fields"]:
        if f["key"] in MONEY:
            f["type"], f["config"] = "currency", {}
    return spec


def start() -> dict:
    spec = clappia.convert("new_car_3_0", ns="start", only={"Expert Details"},
                           system=START_SYSTEM)
    for p in spec["pages"]:
        p["title"], p["gate"] = "Check-in", True
        for s in p["sections"]:
            s["title"] = "Check-in"
    return spec


def end() -> dict:
    spec = clappia.convert("new_car_3_0", ns="end",
                           only={"Payment Details", "Google Review", "Car Perfume"},
                           system=END_SYSTEM)
    pages = spec["pages"]
    spec["pages"] = [{"title": "Wrap-up", "sections": [s for p in pages for s in p["sections"]]}]
    # owner, 2026-11-24 (the local wrap-up draft): Cash or UPI, not Clappia's Online / Cash; on
    # UPI the expert shows the QR to scan and takes the screenshot
    upi = {"and": [{"==": [{"var": "end.taking_payment"}, True]},
                   {"==": [{"var": "end.payment_mode"}, "upi"]}]}
    for sec in spec["pages"][0]["sections"]:
        fields = sec["fields"]
        for n, f in enumerate(list(fields)):
            if f["key"] == "payment_mode":
                f["config"]["options"] = [{"key": "cash", "label": "Cash"},
                                          {"key": "upi", "label": "UPI"}]
                fields.insert(n + 1, {"key": "pay_qr", "label": "CarCID QR Code", "type": "image",
                                      "config": {"asset": "@pay_qr"}, "required": False,
                                      "show_if": upi})
            if f["key"] == "payment_screenshot":
                f["show_if"] = upi
            if f["key"] == "taking_google_review":      # Clappia's "Google Review QR" picture
                fields.insert(n + 1, {"key": "review_qr", "label": "Google Review QR",
                                      "type": "image", "config": {"asset": "@review_qr"},
                                      "required": False, "show_if": {
                                          "==": [{"var": "end.taking_google_review"}, True]}})
    return spec


def inspection(form_key: str) -> tuple[dict, dict]:
    """(spec, version settings: Key Checks and rating config) of one inspection form."""
    app = dict((k, a) for k, _, _, a in INSPECTIONS)[form_key]
    spec = clappia.convert(app, system=INSPECTION_SYSTEM)
    spec["pages"][0]["gate"] = True             # the car's details come first
    titles = {s["title"] for p in spec["pages"] for s in p["sections"]}
    cats = [{"key": k, "label": lb, "sections": [t for t in secs if t in titles]}
            for k, lb, secs in CATEGORIES[form_key]]
    from .reports import ratings_section

    spec["pages"].append(ratings_section(cats))     # Ops-only: the report prints these
    return spec, {"key_checks": key_checks(app), "rating_config": {"categories": cats}}


def key_checks(app: str) -> list[dict]:
    """The app's Ops-only facts as our Key Checks (text, with Clappia's defaults): its "Key
    Checks" section, plus the facts on "Report First Page" that are not ratings."""
    data = clappia.load(app)
    out: list[dict] = []
    seen: set[str] = set()
    for s in data["sections"]:
        if s["title"] not in ("Report First Page", "Key Checks"):
            continue
        for f in s["fields"]:
            label, st = " ".join(f["label"].split()), clappia.settings(f)
            if f["kind"] in ("app-file", "app-formula") or "do not touch" in (
                    f.get("desc") or "").lower():
                continue
            if s["title"] == "Report First Page" and f["kind"] != "ng:input:text":
                continue                         # the Expert Rating word is our overall word
            if s["title"] == "Report First Page" and "Minimum Value" in st:
                continue                         # 1–5 ratings: our rating categories
            if label.endswith("- Value"):
                continue                         # KeyCheckN + its value: one text box here
            key = clappia.slug(label)
            if key in seen:
                continue
            seen.add(key)
            default = st.get("Default value", "")
            item = {"key": key, "label": label.replace("KeyCheck", "Key check "), "type": "text",
                    "default": "" if default in ("NA", "null") else default}
            if "Year" in label:
                item["type"] = "number"
            if "Date" in label:
                item["type"] = "date"
            out.append(item)
    return out
