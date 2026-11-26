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
    "pdi": [("exterior", "Exterior", ["Exterior Body", "Body Frame"]),
            ("ac", "AC", ["Air Conditioning"]),
            ("electronics", "Electronics", ["Electrical and Interior", "Warning Lights"]),
            ("engine", "Engine", ["Engine", "Battery and Charging", "CNG", "OBD Scan",
                                  "Transmission and Clutch Pedal"]),
            ("tires", "Tyres", ["Tyres", "Brakes", "Brakes and Steering", "Axle", "Suspension",
                                "UnderBody"])],
    "used_car": [("exterior", "Exterior", ["Exterior Body", "Body Frame"]),
                 ("ac", "AC", ["Air Conditioning"]),
                 ("drive_train", "Drive Train", ["Transmission and Clutch Pedal", "Axle",
                                                 "Brakes and Steering", "Brakes", "Suspension"]),
                 ("engine", "Engine", ["Engine (before test drive)",
                                       "Engine (after test drive)", "Battery and Charging",
                                       "CNG", "OBD Scan", "Electrical and Interior",
                                       "Warning Lights"]),
                 ("tires", "Tyres", ["Tyres", "UnderBody"])],
    "ev": [("exterior", "Exterior", ["Exterior Body", "Body Frame"]),
           ("ac", "AC", ["Air Conditioning"]),
           ("electronics", "Electronics", ["Electrical and Interior", "Warning Lights"]),
           ("battery", "Battery", ["Battery, Charger and Hood", "Auxiliary Battery"]),
           ("tires", "Tyres", ["Tyres", "Brakes", "Brakes and Steering", "Axle", "Suspension",
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


DELAY_PAGE = "Inspection Delay"


def start() -> dict:
    """The check-in (selfie, place, time), then a page of its own for a late start: "Inspection
    45 Minutes Delayed?" and, on Yes, the payment taken there, asked as on the wrap-up (owner,
    2026-11-26). Both pages are finished before the inspection opens."""
    spec = clappia.convert("new_car_3_0", ns="start", only={"Expert Details"},
                           system=START_SYSTEM)
    fields = {f["key"]: f for p in spec["pages"] for s in p["sections"] for f in s["fields"]}
    late = {"==": [{"var": "start.inspection_45_minutes_delayed"}, "yes"]}
    by_upi = {"and": [late, {"==": [{"var": "start.payment_mode"}, "upi"]}]}
    asked = fields.pop("inspection_45_minutes_delayed")
    amount = {**fields.pop("amount"), "label": "Amount (Pending + 500)", "show_if": late}
    mode = {**fields.pop("payment_mode"), "show_if": late, "config": {"options": [
        {"key": "cash", "label": "Cash"}, {"key": "upi", "label": "UPI"}]}}
    qr = {"key": "pay_qr", "label": "CarCID QR Code", "type": "image",
          "config": {"asset": "@pay_qr"}, "required": False, "show_if": by_upi}
    shot = {**fields.pop("payment_screenshot"), "show_if": by_upi}
    spec["pages"] = [
        {"title": "Check-in", "gate": True,
         "sections": [{"title": "Check-in", "fields": list(fields.values())}]},
        {"title": DELAY_PAGE, "gate": True,
         "sections": [{"title": DELAY_PAGE, "fields": [asked, amount, mode, qr, shot]}]}]
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


SECTION_NAMES = {"Body Frame Accidental Checklist": "Body Frame", "Equipments": "Tool Kit"}


def inspection(form_key: str) -> tuple[dict, dict]:
    """(spec, version settings: Key Checks and rating config) of one inspection form."""
    app = dict((k, a) for k, _, _, a in INSPECTIONS)[form_key]
    spec = clappia.convert(app, system=INSPECTION_SYSTEM)
    for page in spec["pages"]:            # our names for Clappia's sections (owner, 2026-11-26)
        page["title"] = SECTION_NAMES.get(page["title"], page["title"])
        for sec in page["sections"]:
            sec["title"] = SECTION_NAMES.get(sec["title"], sec["title"])
    if form_key != "used_car":      # only Used Car has a test drive (owner, 2026-11-26): the
        # "During Test Drive" left on Axle in the PDI and EV apps is not a page of its own
        spec["pages"] = [q for p in spec["pages"] for q in (
            [{"title": s["title"], "sections": [s]} for s in p["sections"]]
            if p["title"] in clappia.PHASE_PAGES.values() else [p])]
    spec["pages"][0]["gate"] = True             # the car's details come first
    titles = {s["title"] for p in spec["pages"] for s in p["sections"]}
    cats = [{"key": k, "label": lb, "sections": [t for t in secs if t in titles]}
            for k, lb, secs in CATEGORIES[form_key]]
    from .reports import ratings_section

    spec["pages"].append(ratings_section(cats))     # Ops-only: the report prints these
    return spec, {"key_checks": key_checks(app), "rating_config": {"categories": cats}}


# the Key Checks Ops type on the booking (owner, 2026-11-26): these and no others
KEY_CHECKS = [("Tyre Manufacturing Year", "2026"), ("Scratches And Dents", "Not Found"),
              ("Repainted Panels", "Not Found"), ("Rusting in Body", "Not Found")]
USED_CAR_CHECKS = [("Accidental History", "Not Found")]


def key_checks(app: str) -> list[dict]:
    """Our Key Checks of one app (text, typed by Ops, each with its starting value). What else
    Clappia had under "Key Checks" / "Report First Page" lives elsewhere now: Ops' own named
    checks, the manufacturing date, the price estimate and the service history are form fields
    on Ops-only pages (common.py); the 1-5 ratings are our rating categories."""
    items = (USED_CAR_CHECKS if app == "used_car_3_0" else []) + KEY_CHECKS
    return [{"key": clappia.slug(label), "label": label, "type": "text", "default": default}
            for label, default in items]
