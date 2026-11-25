"""Large, realistic demo forms for local review: PDI, Used car and EV, each with many pages,
sections and fields, Key Checks, rating categories and a PDF template. Built from a compact table
so a form is a few lines of data. Never used outside local, test and e2e settings."""
from typing import Any

from apps.forms import library
from apps.forms import services as form_services
from apps.forms.models import Field, Page, Section

CONDITION = {"options": [
    {"key": "ok", "label": "OK"},
    {"key": "minor", "label": "Minor", "is_defect": True, "severity": "minor"},
    {"key": "major", "label": "Major", "is_defect": True, "severity": "major"},
    {"key": "critical", "label": "Critical", "is_defect": True, "severity": "critical"}]}
FUEL = [("petrol", "Petrol"), ("diesel", "Diesel"), ("cng", "CNG"), ("hybrid", "Hybrid")]
GEAR = [("manual", "Manual"), ("automatic", "Automatic"), ("amt", "AMT"), ("cvt", "CVT")]

# item kinds: c condition (+photo when bad), n number, s choice, y yes/no, t text, l long text,
# p photos, v video, g signature, f file
BODY = [("c", "bonnet", "Bonnet"), ("c", "front_bumper", "Front bumper"),
        ("c", "rear_bumper", "Rear bumper"), ("c", "roof", "Roof"), ("c", "boot_lid", "Boot lid"),
        ("c", "door_fl", "Front left door"), ("c", "door_fr", "Front right door"),
        ("c", "door_rl", "Rear left door"), ("c", "door_rr", "Rear right door"),
        ("c", "fender_fl", "Front left fender"), ("c", "fender_fr", "Front right fender"),
        ("c", "fender_rl", "Rear left quarter panel"), ("c", "fender_rr", "Rear right quarter panel")]
PAINT = [("c", "windshield", "Windshield"), ("c", "rear_glass", "Rear glass"),
         ("c", "side_glass", "Side glass"), ("n", "paint_thickness", "Paint thickness", "µm", 0, 1000),
         ("y", "repaint", "Signs of repainting"), ("c", "mirrors", "Mirrors")]
LIGHTS = [("c", "headlight_l", "Left headlight"), ("c", "headlight_r", "Right headlight"),
          ("c", "taillight_l", "Left tail light"), ("c", "taillight_r", "Right tail light"),
          ("c", "indicators", "Indicators"), ("c", "fog_lights", "Fog lights")]
SEATS = [("c", "seat_driver", "Driver seat"), ("c", "seat_passenger", "Front passenger seat"),
         ("c", "seat_rear", "Rear seat"), ("c", "headliner", "Headliner"), ("c", "carpets", "Carpets and mats"),
         ("c", "steering_wheel", "Steering wheel"), ("y", "odour", "Bad smell or damp")]
CONTROLS = [("c", "infotainment", "Infotainment"), ("c", "power_windows", "Power windows"),
            ("c", "central_lock", "Central locking"), ("c", "sunroof", "Sunroof"),
            ("c", "horn", "Horn"), ("c", "wipers", "Wipers and washers")]
ENGINE = [("c", "oil_leak", "Oil leaks"), ("c", "coolant", "Coolant level and hoses"),
          ("c", "battery_12v", "12 V battery"), ("c", "belts", "Belts"),
          ("c", "engine_noise", "Engine noise"), ("c", "exhaust_smoke", "Exhaust smoke")]
GEARBOX = [("c", "gearbox", "Gearbox"), ("c", "clutch", "Clutch"), ("c", "axle", "Axle and CV joints")]
OBD = [("y", "fault_codes", "Fault codes present"), ("t", "fault_code_list", "Codes found")]
ELECTRICAL = [("c", "wiring", "Wiring and fuses"), ("c", "alternator", "Alternator"),
              ("c", "starter", "Starter motor"), ("c", "sensors", "Sensors"),
              ("c", "camera", "Reverse camera"), ("c", "airbag_light", "Airbag system")]
WARNING = [("c", "warn_engine", "Engine light"), ("c", "warn_abs", "ABS light"),
           ("c", "warn_oil", "Oil pressure light"), ("c", "warn_battery", "Battery light"),
           ("c", "warn_tpms", "Tyre pressure light")]
AC = [("c", "ac_cooling", "Cooling"), ("c", "ac_vents", "Vents and fan speeds"),
      ("c", "ac_compressor", "Compressor noise"), ("n", "ac_temp", "Vent temperature", "°C", -10, 40)]
BRAKES = [("c", "brake_pads_f", "Front brake pads"), ("c", "brake_pads_r", "Rear brake pads"),
          ("c", "brake_discs", "Discs and drums"), ("c", "handbrake", "Handbrake"),
          ("c", "shock_f", "Front suspension"), ("c", "shock_r", "Rear suspension"),
          ("c", "steering_play", "Steering play")]
UNDERBODY = [("c", "frame", "Chassis frame"), ("c", "underbody_rust", "Rust"),
             ("c", "exhaust_system", "Exhaust system"), ("c", "fluid_leaks", "Fluid leaks"),
             ("c", "floor_pan", "Floor pan")]
DOCS = [("y", "rc_book", "RC book seen"), ("y", "insurance", "Insurance valid"),
        ("y", "puc", "Pollution certificate"), ("f", "service_history", "Service history copy"),
        ("n", "owners", "Number of owners", "", 0, 10)]
ROAD = [("y", "pulls_to_side", "Pulls to one side"), ("y", "vibration", "Vibration at speed"),
        ("c", "gear_shift", "Gear shifts"), ("l", "road_notes", "Road test notes")]
BATTERY = [("n", "soh", "Battery health", "%", 0, 100), ("c", "battery_pack", "Battery pack housing"),
           ("c", "charge_port", "Charge port"), ("c", "charge_cable", "Charging cable"),
           ("n", "range_claim", "Range shown at full charge", "km", 0, 1000),
           ("y", "fast_charge_ok", "Fast charging works"), ("c", "hv_cables", "High-voltage cables"),
           ("c", "motor_noise", "Motor noise"), ("c", "aux_battery", "Auxiliary battery")]
PHOTOS = [("p", "photo_front", "Front view", 1), ("p", "photo_rear", "Rear view", 1),
          ("p", "photo_left", "Left side", 1), ("p", "photo_right", "Right side", 1),
          ("p", "photo_dash", "Dashboard and odometer", 1), ("p", "photo_vin", "Chassis plate", 1),
          ("p", "photo_engine", "Engine bay", 2), ("v", "video_walkaround", "Walk-around video")]


def vehicle(extra=()):
    return [("t", "registration_no", "Registration number"), ("n", "odometer", "Odometer", "km", 0, 999999),
            ("s", "fuel", "Fuel", FUEL), ("s", "transmission", "Transmission", GEAR),
            ("t", "colour", "Colour"), ("n", "make_year", "Year of manufacture", "", 1990, 2030),
            ("n", "keys", "Number of keys", "", 0, 5), ("y", "service_book", "Service book present"),
            *extra]


def base_pages():
    """A generic car inspection (Used car and EV start from it; the PDI has its own: demo_pdi)."""
    return [("Vehicle", [("Vehicle details", vehicle())]),
            ("Exterior", [("Body panels", BODY), ("Paint and glass", PAINT), ("Lights", LIGHTS)]),
            ("Interior", [("Seats and trim", SEATS), ("Controls", CONTROLS)]),
            ("Engine", [("Engine bay", ENGINE), ("Transmission and clutch", GEARBOX), ("OBD", OBD)]),
            ("Electrical", [("Electrical", ELECTRICAL), ("Warning lights", WARNING)]),
            ("Air conditioning", [("Air conditioning", AC)]),
            ("Tyres and brakes", [("Tyres", "LIBRARY:tyres_standard"),
                                  ("Brakes and suspension", BRAKES)]),
            ("Underbody", [("Underbody", UNDERBODY)]),
            ("Documents and drive", [("Documents", DOCS), ("Road test", ROAD)]),
            ("Photos", [("Photos", PHOTOS)]),
            ("Summary", [("Summary", [("l", "remarks", "Overall remarks"), ("g", "customer_sign", "Customer signature")])])]


def used_pages():
    pages = base_pages()
    pages[0] = ("Vehicle", [("Vehicle details", vehicle([
        ("n", "owner_count", "Previous owners", "", 0, 10),
        ("y", "accident_history", "Accident history declared"),
        ("y", "loan", "Loan or hypothecation"), ("t", "city_used", "City used in")]))])
    return pages


def ev_pages():
    return [("Vehicle", [("Vehicle details", vehicle())]),
            ("Battery and charging", [("Battery and charging", BATTERY)]),
            ("Exterior", [("Body panels", BODY), ("Paint and glass", PAINT), ("Lights", LIGHTS)]),
            ("Interior", [("Seats and trim", SEATS), ("Controls", CONTROLS)]),
            ("Electrical", [("Electrical", ELECTRICAL), ("Warning lights", WARNING)]),
            ("Air conditioning", [("Air conditioning", AC)]),
            ("Tyres and brakes", [("Tyres", "LIBRARY:tyres_standard"),
                                  ("Brakes and suspension", BRAKES)]),
            ("Photos", [("Photos", PHOTOS)]),
            ("Summary", [("Summary", [("l", "remarks", "Overall remarks"), ("g", "customer_sign", "Customer signature")])])]


CATEGORIES = {
    "pdi": [("engine", "Engine", ["Engine bay", "Transmission and clutch", "OBD"]),
            ("ac", "A.C.", ["Air conditioning"]),
            ("electronics", "Electronics", ["Controls", "Electrical", "Warning lights"]),
            ("exterior", "Exterior", ["Body panels", "Paint and glass", "Lights", "Underbody"]),
            ("tyres", "Tyres", ["Tyres", "Brakes and suspension"])],
    "ev": [("battery", "Battery & Charging", ["Battery and charging"]),
           ("ac", "A.C.", ["Air conditioning"]),
           ("electronics", "Electronics", ["Controls", "Electrical", "Warning lights"]),
           ("exterior", "Exterior", ["Body panels", "Paint and glass", "Lights"]),
           ("tyres", "Tyres", ["Tyres", "Brakes and suspension"])],
}
CATEGORIES["used_car"] = CATEGORIES["pdi"]


def _add(version, section, item) -> list[str]:
    """Create the fields of one table row; returns the keys made (for the PDF)."""
    kind, key, label, *rest = item
    order = section.fields.count()

    def make(k, lbl, type_, **kw):
        cfg = kw.pop("config", {})
        Field.objects.create(version=version, section=section, key=k, label=lbl, type=type_,
                             order=order + len(made), config=cfg, **kw)
        made.append(k)

    made: list[str] = []
    if kind == "c":
        make(key, label, "single_choice", config=CONDITION)
        bad = {"in": [{"var": f"inspection.{key}"}, ["major", "critical"]]}
        make(f"{key}_photo", f"{label}: photo", "photo", required_if=bad, show_if=bad,
             config={"max_count": 3, "min_count": 0, "photo_of": key})
    elif kind == "n":
        unit, lo, hi = rest
        make(key, label, "number", config={k: v for k, v in
                                           (("unit", unit), ("min", lo), ("max", hi)) if v != ""})
    elif kind == "s":
        make(key, label, "single_choice", config={"options": [{"key": k, "label": lb} for k, lb in rest[0]],
                                                  "display": "dropdown"})
    elif kind == "y":
        make(key, label, "yes_no")
    elif kind == "t":
        make(key, label, "short_text")
    elif kind == "l":
        make(key, label, "long_text")
    elif kind == "p":
        make(key, label, "photo", config={"max_count": rest[0]})
    elif kind == "v":
        make(key, label, "video", config={"max_count": 1})
    elif kind == "g":
        make(key, label, "signature")
    elif kind == "f":
        make(key, label, "file", config={"max_count": 3})
    return made


def library_items(admin):
    """Shared building blocks (the Library screen is otherwise empty)."""
    def field(key, name, d):
        return library.create_item(admin, kind="field", key=key, name=name, definition=d)

    field("std_condition", "Condition (OK / Minor / Major / Critical)", {
        "key": "std_condition", "label": "Condition", "type": "single_choice", "config": CONDITION})
    field("odometer_reading", "Odometer reading", {"key": "odometer_reading", "label": "Odometer",
                                               "type": "number", "config": {"unit": "km", "min": 0}})
    field("inspector_remarks", "Inspector remarks", {"key": "inspector_remarks", "label": "Remarks",
                                               "type": "long_text", "config": {"max_length": 2000}})
    field("customer_signature", "Customer signature", {"key": "customer_signature",
                                                  "label": "Customer signature", "type": "signature"})

    def tyre(key, label):
        return {"key": key, "label": label, "type": "number",
                "config": {"unit": "mm", "min": 0, "max": 12, "decimals": 1}}

    library.create_item(admin, kind="section", key="tyres_standard", name="Tyres (four depths and spare)",
                        definition={"title": "Tyres", "fields": [
                            tyre("tyre_fl", "Front left tread"), tyre("tyre_fr", "Front right tread"),
                            tyre("tyre_rl", "Rear left tread"), tyre("tyre_rr", "Rear right tread"),
                            {"key": "spare_tyre", "label": "Spare tyre", "type": "single_choice",
                             "config": CONDITION}]})
    library.create_item(admin, kind="section", key="documents_standard", name="Documents check",
                        definition={"title": "Documents", "fields": [
                            {"key": "rc_seen", "label": "RC book seen", "type": "yes_no"},
                            {"key": "insurance_valid", "label": "Insurance valid", "type": "yes_no"},
                            {"key": "puc_valid", "label": "Pollution certificate", "type": "yes_no"}]})
    library.create_item(admin, kind="section", key="lights_standard", name="Lights",
                        definition={"title": "Lights", "fields": [
                            {"key": "head_l", "label": "Left headlight", "type": "single_choice", "config": CONDITION},
                            {"key": "head_r", "label": "Right headlight", "type": "single_choice", "config": CONDITION},
                            {"key": "tail_l", "label": "Left tail light", "type": "single_choice", "config": CONDITION},
                            {"key": "tail_r", "label": "Right tail light", "type": "single_choice", "config": CONDITION}]})


def build_inspection(admin, *, key, name, itype, pages):
    """Create, fill and publish one inspection form; returns (form, {section: [field keys]})."""
    from apps.forms.models import LibraryItem

    form = form_services.create_form(admin, key=key, name=name, inspection_type=itype)
    v = form.versions.get(status="draft")
    first = Page.objects.get(version=v)
    chassis = Field.objects.get(version=v, key="chassis_no")
    section_keys: dict[str, list[str]] = {}
    for n, (title, sections) in enumerate(pages):
        page = first if n == 0 else Page.objects.create(version=v, title=title, order=n)
        page.title = title
        page.gate = n == 0
        page.save()
        for m, (stitle, items) in enumerate(sections):
            if isinstance(items, str):                            # linked from the library
                item = LibraryItem.objects.get(key=items.split(":")[1])
                sec = library.add_section(admin, page, item, link=True)
                section_keys[stitle] = [f.key for f in sec.fields.all()]
                continue
            if n == 0 and m == 0:
                sec = Section.objects.get(page=page)
                sec.title = stitle
                sec.save()
                chassis.order = 0
                chassis.save()
            else:
                sec = Section.objects.create(version=v, page=page, title=stitle, order=m)
            keys: list[str] = []
            for item in items:
                keys += _add(v, sec, item)
            section_keys[stitle] = keys
    summary = Section.objects.get(version=v, title="Summary")
    cats = CATEGORIES[itype]
    for ckey, clabel, _ in cats:
        Field.objects.create(version=v, section=summary, key=f"rating_{ckey}", label=f"{clabel} rating",
                             type="rating", order=summary.fields.count(), config={"category": ckey})
    frame = [f"inspection.{k}" for k in ("frame", "underbody_rust") if k in
             {f for ks in section_keys.values() for f in ks}]
    v.key_checks = [
        {"key": "accident_suspected", "label": "Accident suspected", "type": "rule",
         "rule": {"some": [{"var": "_defects"}, {"in": [{"var": ""}, frame or ["inspection.x"]]}]},
         "true_label": "Yes: check the underbody", "false_label": "No"},
        {"key": "any_critical", "label": "Any critical defect", "type": "rule",
         "rule": {"!!": [{"var": "_defects"}]}, "true_label": "Defects found", "false_label": "No defects"},
    ]
    for k in ("odometer", "registration_no"):                     # keep the demo easy to complete
        Field.objects.filter(version=v, key=k).update(required=True)
    v.rating_config = {"categories": [{"key": c, "label": lb, "sections": secs} for c, lb, secs in cats]}
    v.save()
    from apps.forms.models import VersionCheck

    VersionCheck.objects.create(version=v, rule={">": [{"var": "inspection.odometer"}, 0]},
                                message="The odometer cannot be zero.", fields=["odometer"], order=0)
    v.refresh_from_db()
    form_services.publish_version(admin, v.id, v.row_version)
    return form, section_keys


# last page: the QR code that proves the report, and the photos and videos in one tap each
VERIFY_PAGE: dict[str, Any] = {"title": "Verify this report", "parts": [
    {"type": "spacer", "height": 18},
    {"type": "text", "align": "center",
     "html": "<h2>Verify this report</h2><p>Scan the code or open the link to see this report as "
             "Car C.I.D. issued it.</p>"},
    {"type": "verify", "size": 60},
    {"type": "spacer", "height": 8},
    {"type": "button", "link": "photos", "label": "Download photos"},
    {"type": "button", "link": "videos", "label": "Download videos"}]}


def pdf_definition(code, title, form) -> dict:
    """A plain report: a page per form page, a table of each section, then its photos."""
    version = form.versions.get(status="published")
    pages = []
    for page in Page.objects.filter(version=version).order_by("order", "id"):
        parts: list[dict] = [{"type": "text", "html": f"<h2>{page.title}</h2>"}]
        for sec in Section.objects.filter(page=page).order_by("order", "id"):
            parts.append({"type": "table", "title": sec.title,
                          "source": {"kind": "section", "section": f"inspection.{sec.key}"}})
            parts.append({"type": "photos", "per_row": 3, "caption": "label",
                          "source": {"kind": "section", "section": f"inspection.{sec.key}"}})
        pages.append({"title": page.title, "parts": parts})
    pages.append(VERIFY_PAGE)
    header = {"left": [{"text": "<strong>CAR C.I.D.</strong>"}],
              "right": [{"text": f"<strong>{title}</strong>"}, {"text": "{{ sys.booking_id }}"}],
              "background": "brand", "height": 16}
    footer = {"right": [{"text": "Page {{ sys.page }} of {{ sys.pages }}"}], "height": 8}
    return {"schema": 2, "filename": "{{ sys.booking_id }}" + code + ".pdf",
            "bands": {"normal": {"header": header, "footer": footer}}, "pages": pages}


def build_field_tour(admin, picture_id: str):
    """A short inspection with every field type once (and each choice layout), for trying the app
    without filling a 200-question form: 4 pages, a gate page, a follow-up on a defect, the
    check-in and the wrap-up."""
    form = form_services.create_form(admin, key="tour", name="Field tour", inspection_type="tour")
    v = form.versions.get(status="draft")
    order = {"n": 0}

    def page(title, n, gate=False):
        p = Page.objects.get(version=v) if n == 0 else Page.objects.create(version=v, title=title, order=n)
        p.title, p.gate = title, gate
        p.save()
        return p

    def section(p, title, first=False):
        if first:
            s = Section.objects.get(page=p)
            s.title = title
            s.save()
            return s
        return Section.objects.create(version=v, page=p, title=title, order=p.sections.count())

    def field(s, key, label, type_, **kw):
        order["n"] += 1
        return Field.objects.create(version=v, section=s, key=key, label=label, type=type_,
                                    order=order["n"], config=kw.pop("config", {}), **kw)

    opts = lambda *labels: [{"key": lb.lower().replace(" ", "_").replace(",", "")[:40], "label": lb} for lb in labels]  # noqa: E731

    car = section(page("Car", 0, gate=True), "Identity", first=True)
    Field.objects.filter(version=v, key="chassis_no").update(config={"scan": True}, order=0)
    field(car, "registration_no", "Registration number", "short_text", required=True,
          helper_text="Tap the scan button to read the number plate.", config={"scan": True})
    field(car, "odometer", "Odometer", "number", required=True, config={"unit": "km", "min": 0, "max": 999999})

    text = section(page("Text and time", 1), "Details", first=False)
    field(text, "remarks", "Remarks", "long_text", helper_text="Anything the customer should know.")
    field(text, "quoted_price", "Quoted price", "currency")
    field(text, "owner_phone", "Owner's phone", "phone")
    field(text, "purchase_date", "Purchase date", "date")
    field(text, "service_time", "Usual service time", "time")
    field(text, "last_service", "Last service", "datetime")
    field(text, "visit_date", "Visit date", "date", config={"auto": True})

    body = section(page("Choices", 2), "Body")
    field(body, "bonnet", "Bonnet", "single_choice", required=True, config=CONDITION)
    bad = {"in": [{"var": "inspection.bonnet"}, ["minor", "major", "critical"]]}
    field(body, "bonnet_photo", "Bonnet photo", "photo", show_if=bad, required_if=bad, config={"max_count": 2})
    field(body, "paint", "Paint condition", "single_choice", config={"options": [
        {"key": "original", "label": "Original paint"},
        {"key": "repainted", "label": "Repainted", "is_defect": True, "severity": "minor"},
        {"key": "mismatch", "label": "Repainted, colour does not match the rest of the car", "is_defect": True, "severity": "major"},
        {"key": "putty", "label": "Putty or filler work visible", "is_defect": True, "severity": "major"},
        {"key": "rust", "label": "Rust through the paint", "is_defect": True, "severity": "critical"},
        {"key": "replaced", "label": "Panel replaced", "is_defect": True, "severity": "major"},
        {"key": "not_checked", "label": "Could not check"}]})
    field(body, "tyre_brand", "Tyre brand", "single_choice", config={"options": opts(
        "Apollo", "Bridgestone", "CEAT", "Continental", "Goodyear", "JK Tyre", "Michelin", "MRF", "Pirelli", "Yokohama")})
    field(body, "accident", "Accident history", "yes_no")
    field(body, "scratches", "Scratches found on", "multi_choice", config={"options": opts(
        "Front bumper", "Rear bumper", "Roof", "Boot")})
    field(body, "features", "Features present", "multi_choice", config={"options": opts(
        "Sunroof", "Cruise control", "Rear camera", "Parking sensors", "Alloy wheels", "Fog lamps",
        "Wireless charging", "Ventilated seats", "Air purifier", "Surround camera")})
    field(body, "registered_city", "Registered in", "master_list", config={"list": "city"})
    field(body, "second_opinion", "Second opinion by", "user_picker", config={"role": "expert"})

    media = section(page("Photos and more", 3), "Evidence")
    field(media, "how_to", "Where to stand for the front photo", "image", config={"asset": picture_id})
    field(media, "front_photo", "Front photos", "photo", config={"max_count": 3})
    field(media, "odometer_photo", "Odometer photo (camera only)", "photo", config={"max_count": 1, "capture": "camera"})
    field(media, "engine_video", "Engine running video", "video", config={"max_count": 1})
    field(media, "documents", "Documents", "file", config={"max_count": 3})
    field(media, "car_location", "Where the car is parked", "gps", config={"auto": False})
    field(media, "customer_sign", "Customer signature", "signature")
    field(media, "rating_body", "Body rating", "rating", config={"category": "body"})

    v.rating_config = {"categories": [{"key": "body", "label": "Body", "sections": ["Body"]}]}
    v.key_checks = [{"key": "any_defect", "label": "Any defect found", "type": "rule",
                     "rule": {"!!": [{"var": "_defects"}]}, "true_label": "Defects found",
                     "false_label": "No defects"}]
    v.save()
    v.refresh_from_db()
    form_services.publish_version(admin, v.id, v.row_version)
    return form
