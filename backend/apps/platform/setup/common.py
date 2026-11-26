"""What the PDI, Used Car and EV forms share, kept once in the library (owner, 2026-11-26; the
review page and every decision: docs/common-sections).

- A section the forms share becomes one library section holding only the questions all its forms
  have. A form's own questions sit in a properly named section of its own right after it
  (`parent` names the shared one: the report prints them on its page).
- What only the two fuel-car forms (PDI, Used Car) share goes in library sections of their own.
- Sections that stay separate (Engine, Car Documents, CNG: its rule looks at Fuel Type, outside
  it) share their matching rule-free questions as library fields.
- Where the Clappia apps disagreed the owner picked one answer list or name (ANSWERS, NAMES);
  typing-only differences follow one style (STYLE).

`share` takes the three converted specs and returns the library and the specs rebuilt on it."""
import copy
import json
import re
from typing import Any

from . import clappia

FORMS = ("pdi", "used_car", "ev")
FUEL = ("pdi", "used_car")
SEPARATE = ("Ratings", "Car Documents", "Engine")     # a title or its start: never in the library
ALWAYS_OWN = {"chassis_no": "Chassis Number"}              # built into every form, not library

# the same question under two names
ALIAS = {"driver orvm controls": "driver orvm control",
         "passenger orvm controls": "passenger orvm control",
         "car variant": "variant", "bi fuel certification": "bi fuel certificate",
         "engine noise recording": "engine noise video", "wiring image": "wiring photo"}
# asked only on Used Car in Clappia; now on every form that has the section
PROMOTE = {"air condition video at fan max speed", "axle rotating video",
           "driver side front shocker photo", "passenger side front shocker photo",
           "driver side rear shocker photo", "passenger side rear shocker photo",
           "glass serial numbers photos", "radiator core support remark",
           "chassis remark"}
# ---- the customer-view review (owner, 2026-11-27): the label names the part or thing, the answer
# says the result. old question (normalised) → (new label, new answers or None to keep them)
W, NW, NA = "Working", "Not Working", "Not Applicable"
REVIEW: dict[str, tuple[str, list[str] | None]] = {
    "central lock working": ("Central Lock", [W, NW, NA]),
    "air conditioning turning on": ("AC Switching On", [W, NW]),
    "de fogger front vent working": ("Front Defogger Vent", [W, NW]),
    "de fogger rear vent working": ("Rear Defogger Vent", [W, NW, NA]),
    "air conditioning direction mode working": ("AC Air Direction Modes", [W, NW]),
    "air conditioning all vents": ("AC Vents", [W, NW]),
    "engine damage underbody": ("Engine Underbody", None),
    "smoke emission": ("Exhaust Smoke", ["Not Present", "Present"]),
    "smoke emission video": ("Exhaust Smoke Video", None),
    "engine noise": ("Abnormal Engine Noise", None),
    "exhaust sound": ("Abnormal Exhaust Sound", None),
    "steering weird noise": ("Abnormal Steering Noise", None),
    "abnormal noise": ("Abnormal Axle Noise", None),
    "any fault codes present": ("OBD Fault Codes",
                                ["Not Present", "Present", "Port Not Working", "Not Checked"]),
    "match all glasses serial number": ("Glass Serial Numbers", None),
    "match all glasses serial number photos": ("Glass Serial Numbers Photos", None),
    "match glasses serial number remark": ("Glass Serial Numbers Remark", None),
    "match chassis no plate with the real body": ("Chassis Number on Body", None),
    "check gear box transmission shifting": ("Gear Shifting", None),
    "check 4x4 shifting": ("4x4 Shifting", None),
    "check engine": ("Check Engine Light", None),
    "any other lights found": ("Other Warning Lights", None),
    "any fluid leaks under body": ("Fluid Leaks Under Body", None),
    "check for oil leaks near engine": ("Oil Leaks Near Engine", None),
    "check onboard computer adblue level diesel cars": ("AdBlue Level Display (Diesel)", None),
    "signs of camber issue": ("Camber Issue", None),
    "steering coming back while driving": ("Steering Self-Centring", None),
    "rear side floor 7 seater": ("Third Row Floor", None),
    "rear seat condition 7 seater": ("Third Row Seat Condition", None),
    "rear seat belt 7 seater": ("Third Row Seat Belt", None),
    "car height": ("Ride Height", None),
    "generator state": ("Generator / Alternator State", ["Good", "High Voltage", "Faulty"]),
    "generator state photo": ("Generator / Alternator State Photo", None),
    # capitals only
    "smoke from dipstick point": ("Smoke From Dipstick Point", None),
    "transmission oil leakage": ("Transmission Oil Leakage", None),
    "radiator fan": ("Radiator Fan", None), "under trays": ("Under Trays", None),
    "fuel tank": ("Fuel Tank", None), "bank finance noc": ("Bank Finance NOC", None),
    "extended warranty": ("Extended Warranty", None), "trunk open": ("Trunk Open", None),
    "engine work done": ("Engine Work Done", None),
    "transmission work done": ("Transmission Work Done", None)}
# the colour (and how serious) of answers the usual word lists get wrong for these questions
TONES: dict[tuple[str, str], tuple[str | None, str | None]] = {
    ("battery state", "Full"): ("ok", None), ("battery state", "Medium"): ("warn", None),
    ("battery state", "Low"): ("bad", "minor"), ("battery state", "Empty"): ("bad", "major"),
    ("generator alternator state", "Good"): ("ok", None),
    ("generator alternator state", "High Voltage"): ("warn", None),
    ("generator alternator state", "Faulty"): ("bad", "major"),
    ("cng fitting", "Outside Fitted (Conventional)"): ("warn", None)}
# checks the converter left without colours (it took "seat" / "state" for a plain fact)
COLOURED = re.compile(r"seat|third row|battery state|generator|cng fitting", re.I)
UNITS = {"ac cool temperature": "°C", "ac hot temperature": "°C"}


def reviewed(f: dict) -> None:
    """One question as the review wants it: its new name, answers, colours and unit."""
    old = re.sub(r"[^a-z0-9]+", " ", f["label"].lower()).strip()
    label, answers = REVIEW.get(old, (f["label"], None))
    f["label"] = label
    if old in UNITS and f["type"] == "number":
        f["config"] = {**f["config"], "unit": UNITS[old]}
    opts = _options(f)
    if not opts or not (answers or COLOURED.search(label)):
        return
    n = re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()
    was = {o["label"]: o for o in opts}
    built = []
    for a in answers or [o["label"] for o in opts]:
        tone, sev = TONES.get((n, a)) or clappia.tone_of(a, label)
        o = {"key": was[a]["key"] if a in was else clappia.slug(a), "label": a}
        if tone:
            o["tone"] = tone
        if sev:
            o.update(is_defect=True, severity=sev)
        built.append(o)
    f["config"] = {**f["config"], "options": built}


# ---- added by the owner (second round, 2026-11-26)
# a paint gauge reading photo right after each painted panel's check (always, 1 needed, 2 allowed)
GAUGE = {"driver front door", "driver back door", "passenger back door", "passenger front door",
         "front bonnet top", "car roof outside", "boot space door backdoor", "driver front fender",
         "passenger front fender", "driver back quarter panel", "passenger back quarter panel"}
# section → question it comes after → the new questions (label, type, answers / photo limit)
ADDED: dict[str, dict[str, list[tuple[str, str, Any]]]] = {
    "Electrical and Interior": {"wiper": [
        ("Wiper Washer Spray", "single_choice", ["Working", "Not Working"]),
        ("Rear Wiper", "single_choice", ["Working", "Not Working", "Not Applicable"])]},
    "Engine and Fuel Details": {"transmission type": [("Gear Shifting Panel", "photo", 1)]},
    # the gauge's reading beside each Good / Average / Bad (review, 2026-11-27)
    "Tyres": {f"{tyre} tyre depth check": [
        (f"{tyre.title()} Tyre Tread Depth (mm)", "number",
         {"unit": "mm", "min": 0, "max": 20, "decimals": 1})]
        for tyre in ("driver front", "driver back", "passenger back", "passenger front",
                     "stepney")}}
# asked only when its tyre is there: the same rule as this sibling question
SAME_RULE_AS = {"stepney_tyre_tread_depth_mm": "Stepney Tyre Shape"}
# the body frame photos: always on a Used Car, on PDI and EV only when their check finds a problem
FRAME = "Body Frame"
USED_CAR = {"==": [{"var": "booking.inspection_type"}, "used_car"]}

# Clappia shows "Chasis Remark" on Radiator Core Support answers that check does not have, so it
# never shows: it is the remark of the chassis plate check (shown when that finds a problem)
RULE_FIX = {"chassis remark": "chassis number on body"}
# section → the name of what PDI + Used Car share beyond it / what EV / Used Car alone have
FUEL_NAME = {"Car Details": "Engine and Fuel Details", "Exterior Body": "Fuel Filler Flap",
             "Electrical and Interior": "Ignition and Fuel Controls",
             "Warning Lights": "Engine Warning Lights",
             "UnderBody": "Engine, Exhaust and Fuel Tank"}
OWN_NAME = {("ev", "Exterior Body"): "Charger Flap",
            ("ev", "Electrical and Interior"): "Start and Charging Controls",
            ("ev", "Warning Lights"): "Charging Warning Light",
            ("ev", "UnderBody"): "Underbody Cables",
            ("ev", "Car Images From All Directions"): "Battery, Charger and Hood",
            ("used_car", "Car Details"): "Registration Details",
            ("used_car", "Car Images From All Directions"): "Odometer After Test Drive"}
# the form whose wording and settings a shared question takes (photos of the body frame are
# always asked, as on Used Car)
SOURCE_ORDER = ("pdi", "used_car", "ev")
USED_FIRST = {(FRAME, "photo")}

# ---- the owner's choices (pop-ups, 2026-11-26): answers by question
ANSWERS: dict[str, Any] = {
    "car company": "all", "driver side view mirror housing": "pdi",
    "front grill": ["Ok", "Repainted", "Minor Scratches", "Minor Dents", "Panel Gaps",
                    "Major Scratches", "Major Dents", "Damaged", "Replaced"],
    "driver side strut tower apron": "pdi", "passenger strut tower apron": "pdi",
    "boot floor": "used_car", "cruise control": "pdi",
    "window driver side": "pdi", "window passenger side": "pdi",
    "window passenger rear side": "pdi", "window driver rear side": "pdi",
    "steering self centring": "pdi", "alignment": "pdi", "bubbling": "pdi",
    "steering vibration": "pdi",
    "stepney tyre shape": ["Ok", "Damaged", "Not Applicable", "Not Able to Check"],
    "front protection cover": "pdi", "multi function display": "pdi",
    "passenger side view mirror housing": ["Ok", "Scratches", "Not Ok", "Damaged"]}
NAMES: dict[Any, str] = {
         "variant": "Car Variant",
         # the working check only: Exterior Body keeps "Driver - Back Indicator" for the body part
         ("Electrical and Interior", "driver front indicator"): "Driver - Front Indicator Light",
         ("Electrical and Interior", "passenger front indicator"):
             "Passenger - Front Indicator Light",
         ("Electrical and Interior", "driver back indicator"): "Driver - Back Indicator Light",
         ("Electrical and Interior", "passenger back indicator"):
             "Passenger - Back Indicator Light",
         "driver orvm control": "Driver ORVM Control",
         "passenger orvm control": "Passenger ORVM Control",
         "corner front driver": "Corner Front - Driver",
         "corner back driver": "Corner Back - Driver",
         "corner back passenger": "Corner Back - Passenger",
         "corner front passenger": "Corner Front - Passenger", "wiring photo": "Wiring Image",
         "engine noise video": "Engine Noise Recording",
         "bi fuel certificate": "Bi-Fuel Certificate"}
# Used Car's Registration Certificate has "Expired": it keeps its own; PDI and EV share one
NOT_SHARED = {("registration certificate", "used_car")}
STYLE = [(r"\s*/\s*", " / "), (r"Mud flap", "Mud Flap"), (r"WindShield", "Windshield"),
         (r"plate\b", "Plate"), (r"\bside\b", "Side"),
         (r"^Driver-? Front Door$", "Driver - Front Door"),
         (r" photo$", " Photo"), (r"^Passenger - (Rear Wheel .* Photos)$", r"Passenger \1"),
         (r"not working", "Not Working"), (r"Running Board Board", "Running Board"),
         (r"Back (Passenger|Driver)Side", r"Back \1 Side")]


def norm(label: str) -> str:
    s = re.sub(r"\((before|after) test drive\)|\(electrical and interior\)", "", label.lower())
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return ALIAS.get(s, s)


def style(text: str) -> str:
    for a, b in STYLE:
        text = re.sub(a, b, text)
    return text


def _options(f: dict) -> list[dict]:
    return f.get("config", {}).get("options") or []


def _separate(title: str) -> bool:
    return any(title == t or title.startswith(t) for t in SEPARATE)


def _base(title: str) -> str:
    return re.sub(r"\s*\((before|after) test drive\)", "", title)


def _sections(spec: dict) -> list[tuple[dict, dict]]:
    return [(p, s) for p in spec["pages"] for s in p["sections"]]


def _vars(rule: Any) -> set[str]:
    return set(re.findall(r'"var": "inspection\.([a-z0-9_]+)"', json.dumps(rule or {})))


def _rekey(rule: Any, keys: dict[str, str]) -> Any:
    if rule is None:
        return None
    text = json.dumps(rule)
    for old in sorted(_vars(rule), key=len, reverse=True):
        text = text.replace(f'"inspection.{old}"', f'"inspection.{keys.get(old, old)}"')
    return json.loads(text)


Dest = tuple[str, tuple[str, ...]]        # (section name, the forms that share it)


class Sharing:
    def __init__(self, specs: dict[str, dict]):
        for spec in specs.values():                  # the review's names, answers and colours
            for _, sec in _sections(spec):
                for f in sec["fields"]:
                    before = clappia._problem_rule(f, "inspection") if _options(f) else None
                    reviewed(f)
                    after = clappia._problem_rule(f, "inspection") if _options(f) else None
                    if before is not None and after != before:     # its problem photos follow
                        for g in sec["fields"]:
                            if g.get("show_if") == before:
                                g["show_if"] = after
        self.specs = specs
        self.by_title = {k: {s["title"]: s for _, s in _sections(specs[k])} for k in FORMS}
        self.pool = {o["label"]: o for k in FORMS for _, s in _sections(specs[k])
                     for f in s["fields"] for o in _options(f)}
        self.sections: dict[str, dict] = {}          # library key → {name, forms, definition}
        self.fields: dict[str, dict] = {}            # library key → {forms, definition}
        self.keys: dict[str, dict[str, str]] = {k: {} for k in FORMS}     # old field key → new
        self.notes: list[str] = []

    # ------------------------------------------------------------ one question, one wording

    def label(self, title: str, n: str, by: dict[str, dict]) -> str:
        return NAMES.get((title, n)) or NAMES.get(n) or style(
            (by.get("pdi") or next(iter(by.values())))["label"])

    def options(self, n: str, by: dict[str, dict]) -> list[dict] | None:
        lists = {k: _options(f) for k, f in by.items()}
        if not any(lists.values()):
            return None
        rule = ANSWERS.get(n)
        if isinstance(rule, list):
            labels = rule
        elif rule == "all":
            labels = []
            for k in ("used_car", "pdi", "ev"):
                labels += [o["label"] for o in lists.get(k, []) if o["label"] not in labels
                           and o["label"] != "Others"]
            labels.append("Others")
        else:
            labels = [style(o["label"]) for o in lists.get(rule or "pdi") or next(
                v for v in lists.values() if v)]
        own = {style(o["label"]): o for v in lists.values() for o in v}
        out = []
        for lb in labels:
            src = own.get(lb) or self.pool.get(lb)
            if src is None:
                raise ValueError(f"No such answer anywhere: {lb!r} ({n})")
            out.append({**src, "label": lb})
        return out

    def source(self, title: str, by: dict[str, dict]) -> str:
        kind = next(iter(by.values()))["type"]
        order = ("used_car", "pdi", "ev") if (title, kind) in USED_FIRST else SOURCE_ORDER
        return next(k for k in order if k in by)

    def question(self, title: str, n: str, by: dict[str, dict], taken: set[str]) -> dict:
        """The one shared form of a question the forms in `by` ask (its key from its source)."""
        src = self.source(title, by)
        f = copy.deepcopy(by[src])
        f.pop("clappia", None)
        f["label"] = self.label(title, n, by)
        opts = self.options(n, by)
        if opts is not None:
            f["config"] = {**f["config"], "options": opts}
        key = f["key"]
        while key in taken:
            key = f"{key[:60]}_s"
        f["key"] = key
        taken.add(key)
        f["_src"], f["_n"] = src, n
        return f

    # ------------------------------------------------------------ shared sections

    def where(self, k: str, title: str, f: dict, have: list[str], asked: dict[str, list[str]]
              ) -> Dest:
        """(section name, the forms that share it) for one question of form `k`."""
        if f["key"] in ALWAYS_OWN:
            return ALWAYS_OWN[f["key"]], (k,)
        n = norm(f["label"])
        forms = have if n in PROMOTE else asked[n]
        if forms == have:
            return title, tuple(have)
        if tuple(forms) == FUEL and title in FUEL_NAME:
            return FUEL_NAME[title], FUEL
        if forms == [k] and (k, title) in OWN_NAME:
            return OWN_NAME[(k, title)], (k,)
        self.notes.append(f"{k}: {title} / {f['label']} (asked on {forms}) stays the form's own")
        return f"{title} ({k})", (k,)

    def split(self) -> dict[str, list[dict]]:
        """Each form's new section list (page title kept), shared ones marked `library`."""
        plan: dict[str, list[dict]] = {k: [] for k in FORMS}
        self._groups: dict[Dest, dict[str, dict[str, dict]]] = {}
        self._order: dict[Dest, list[str]] = {}
        self._parent: dict[Dest, str | None] = {}
        for k in FORMS:
            for page, s in _sections(self.specs[k]):
                self._split_section(k, page, s, plan[k])
        for dest, by_n in self._groups.items():
            self.master(dest, self._order[dest], by_n, self._parent[dest])
        for k in FORMS:
            for row in plan[k]:
                dest = row.pop("_dest", None)
                if dest is not None:
                    row["library"] = clappia.slug(dest[0])
                    row["fields"] = copy.deepcopy(
                        self.sections[row["library"]]["definition"]["fields"])
        return plan

    def _split_section(self, k: str, page: dict, s: dict, rows: list[dict]) -> None:
        t = s["title"]
        have = [x for x in FORMS if t in self.by_title[x]]
        at = {"page": page["title"], "gate": page.get("gate", False)}
        if _separate(t) or len(have) < 2 or s.get("show_if"):
            rows.append({**at, "title": t, "show_if": s.get("show_if"),
                         "fields": copy.deepcopy(s["fields"])})
            return
        asked: dict[str, list[str]] = {}
        for x in have:
            for g in self.by_title[x][t]["fields"]:
                asked.setdefault(norm(g["label"]), []).append(x)
        mine: dict[Dest, list[dict]] = {}
        for f in s["fields"]:
            mine.setdefault(self.where(k, t, f, have, asked), []).append(f)
        for dest in sorted(mine, key=lambda d: d[0] != t):
            name, forms = dest
            row = {**at, "title": name, "parent": None if name == t else t, "show_if": None}
            if len(forms) > 1:
                row["_dest"] = dest
                self._parent[dest] = row["parent"]
                for f in mine[dest]:
                    n = norm(f["label"])
                    self._groups.setdefault(dest, {}).setdefault(n, {})[k] = f
                    if n not in self._order.setdefault(dest, []):
                        self._order[dest].append(n)
            else:
                row["fields"] = copy.deepcopy(mine[dest])
                same = next((r for r in rows if r["title"] == name and "fields" in r), None)
                if same is not None:              # e.g. Bonnet Open joins an EV section
                    same["fields"] += row["fields"]
                    continue
            rows.append(row)

    def master(self, dest: Dest, order: list[str],
               by_n: dict[str, dict[str, dict]], parent: str | None) -> None:
        name, forms = dest
        title = parent or name
        taken: set[str] = set()
        fields = [self.question(title, n, by_n[n], taken) for n in order]
        added = self._added(name, fields, taken)
        for f in fields:                              # every form's old key → the shared key
            for k, old in by_n[f["_n"]].items():
                self.keys[k][old["key"]] = f["key"]
        by_key = {f["key"]: f for f in fields}
        by_norm = {f["_n"]: f for f in fields}
        for f in fields:
            src, n = f.pop("_src"), f.pop("_n")
            old = by_n[n][src]
            rule = old.get("show_if")
            if n in RULE_FIX:                         # Clappia's rule looks at the wrong check
                f["show_if"] = clappia._problem_rule(by_norm[RULE_FIX[n]], "inspection")
                continue
            if rule is None:
                continue
            refs = _vars(rule)
            src_fields = {g["key"]: g for g in self.by_title[src][title]["fields"]}
            ref = next(iter(refs)) if len(refs) == 1 else None
            check = src_fields.get(ref) if ref else None
            new = by_key.get(self.keys[src].get(ref or "", ""))
            if check is not None and new is not None and rule == clappia._problem_rule(
                    check, "inspection"):
                f["show_if"] = clappia._problem_rule(new, "inspection")   # its final answers
            else:
                f["show_if"] = _rekey(rule, self.keys[src])
            outside = _vars(f["show_if"]) - set(by_key) - set(ALWAYS_OWN)
            if outside:
                raise ValueError(f"{name}: {f['label']} depends on {outside}, outside the section")
        if name == FRAME:
            self._frame_photos(fields)
        for after, new in reversed(added):            # each right after its own question
            like = next((f for f in fields if f["label"] == SAME_RULE_AS.get(new["key"])), None)
            if like is not None and like.get("show_if"):
                new["show_if"] = like["show_if"]
            fields.insert(fields.index(after) + 1, new)
        self.sections[clappia.slug(name)] = {
            "name": name, "forms": list(forms), "parent": parent,
            "definition": {"title": name, "fields": fields}}

    def _added(self, name: str, fields: list[dict], taken: set[str]) -> list[tuple[dict, dict]]:
        """(the question it follows, the new question) for what the owner added to a section."""
        out = []
        for f in fields:
            n = f["_n"]
            new = list(ADDED.get(name, {}).get(n, []))
            if name == "Exterior Body" and n in GAUGE:
                new.append((f"{f['label']} Paint Gauge Reading", "photo", 2))
            for label, kind, more in new:
                q = {"key": clappia.slug(label), "label": label, "type": kind, "required": True,
                     "helper_text": "", "config": (
                         {"max_count": more, "capture": "camera"} if kind == "photo"
                         else more if kind == "number"
                         else {"options": [{**self.pool[x], "label": x} for x in more]})}
                if q["key"] in taken:
                    raise ValueError(f"{name}: the key {q['key']} is taken")
                taken.add(str(q["key"]))
                out.append((f, q))
        return out

    @staticmethod
    def _frame_photos(fields: list[dict]) -> None:
        """Each body frame photo is shown (and then required) on a Used Car always, on the other
        forms only when the check it belongs to finds a problem."""
        checks = [f for f in fields if f["type"] in ("single_choice", "multi_choice")]
        for f in fields:
            if f["type"] != "photo":
                continue
            mine = [c for c in checks if norm(f["label"]).startswith(norm(c["label"]))]
            problem = clappia._problem_rule(max(mine, key=lambda c: len(c["label"])),
                                            "inspection") if mine else None
            f["required"] = True
            f["show_if"] = {"or": [USED_CAR, problem]} if problem else None
            if f["show_if"] is None:
                f.pop("show_if")

    # ------------------------------------------------------------ shared fields

    def share_fields(self, plan: dict[str, list[dict]]) -> None:
        """In sections that stay a form's own, a rule-free question two or three forms ask the
        same way is one library field."""
        groups: dict[str, dict[str, dict[str, list[dict]]]] = {}
        for k in FORMS:
            for row in plan[k]:
                if "library" in row or row.get("parent") or row["title"] in ALWAYS_OWN.values() \
                        or row["title"] == "Ratings":
                    continue
                for f in row["fields"]:
                    groups.setdefault(_base(row["title"]), {}).setdefault(
                        norm(f["label"]), {}).setdefault(k, []).append(f)
        for base, by_n in groups.items():
            for n, found in by_n.items():
                by = {k: fs[0] for k, fs in found.items()
                      if len(fs) == 1 and (n, k) not in NOT_SHARED}
                if len(by) < 2 or any(f.get("show_if") or f["key"] in ALWAYS_OWN
                                      for f in by.values()):
                    continue
                if len({f["type"] for f in by.values()}) > 1:
                    continue
                if n not in NAMES and len({style(_base(f["label"])) for f in by.values()}) > 1:
                    continue                           # e.g. a "(after test drive)" reading
                taken = set(self.fields) | {key for k in by for key in self._keys(plan[k])
                                            if key != by[k]["key"]}
                shared = self.question(base, n, by, taken)
                shared.pop("_src"), shared.pop("_n")
                for k, f in by.items():
                    self.keys[k][f["key"]] = shared["key"]
                    f.clear()
                    f.update(copy.deepcopy(shared), library=shared["key"])
                self.fields[shared["key"]] = {"forms": list(by), "group": base,
                                              "definition": shared}

    @staticmethod
    def _keys(rows: list[dict]) -> set[str]:
        return {f["key"] for r in rows for f in r["fields"]}

    # ------------------------------------------------------------ the forms again

    def rebuild(self, plan: dict[str, list[dict]]) -> dict[str, dict]:
        out = {}
        for k in FORMS:
            seen: set[str] = set()
            pages: list[dict] = []
            for row in plan[k]:
                if not pages or pages[-1]["title"] != row["page"]:
                    pages.append({"title": row["page"], "sections": [],
                                  **({"gate": True} if row["gate"] else {})})
                if "library" not in row:
                    self._tidy_own(k, row["fields"], seen)
                for f in row["fields"]:
                    if f["key"] in seen:
                        raise ValueError(f"{k}: two questions share the key {f['key']}")
                    seen.add(f["key"])
                sec = {"title": row["title"], "fields": row["fields"],
                       **{a: row[a] for a in ("library", "parent") if row.get(a)}}
                rule = _rekey(row.get("show_if"), self.keys[k])
                if rule is not None:
                    sec["show_if"] = rule
                pages[-1]["sections"].append(sec)
            out[k] = {"pages": pages}
        return out

    def _tidy_own(self, k: str, fields: list[dict], seen: set[str]) -> None:
        """A form's own questions: the house style, rules pointing at the shared keys."""
        for f in fields:
            if "library" in f:
                continue
            if f["key"] not in ALWAYS_OWN:
                f["label"] = style(f["label"])
            f["show_if"] = _rekey(f.get("show_if"), self.keys[k])
            if f["show_if"] is None:
                f.pop("show_if")
            while f["key"] in seen:
                f["key"] = f"{f['key'][:60]}_o"


# ---- the Ops-only first page (owner, 2026-11-26): the comment the report prints and up to five
# key checks Ops name themselves (Clappia's "KeyCheck1" + "KeyCheck1 - Value" pairs)
OPS_PAGE = "Additional Checks"
OWN_CHECKS = 5
STAGES = ("draft", "assigned", "in_progress", "submitted", "completed", "cancelled")
NOT_FOR_EXPERTS = {"expert": {stage: "hidden" for stage in STAGES}}


def _text(key: str, label: str, kind: str = "short_text") -> dict:
    return {"key": key, "label": label, "type": kind, "config": {}, "required": False,
            "helper_text": ""}


NOT_USED_CAR = {"!=": [{"var": "booking.inspection_type"}, "used_car"]}
# Used Car only, Ops only: what the authorised service centre's records say (Clappia's Key Checks)
SERVICE_PAGE = "Service History Details"
AT_CENTRE = "at Authorized Service Center"
SERVICE_HISTORY = [("Last Service Date", AT_CENTRE), ("Accidental History Reported", AT_CENTRE),
                   ("Total Services", AT_CENTRE), ("Indication of Odometer Rollback", ""),
                   ("Engine work done", ""), ("Transmission work done", ""),
                   ("Last Odometer Reading", AT_CENTRE)]


def ops_sections() -> dict[str, dict]:
    """The three library sections of the Ops-only page, hidden from experts at every stage."""
    pairs = [f for n in range(1, OWN_CHECKS + 1) for f in (
        _text(f"key_check_{n}_label", f"Key Check {n} Label"),
        _text(f"key_check_{n}_value", f"Key Check {n} Value"))]
    made = {"Expert Comments": [_text("expert_comments", "Expert Comments", "long_text")],
            # one section for every form: each detail shows on the inspections it belongs to
            "Additional Details": [
                {**_text("manufacturing_date", "Manufacturing Date"), "show_if": NOT_USED_CAR},
                {**_text("price_estimate", "Price Estimate"), "show_if": USED_CAR}],
            "Key Checks": pairs}
    return {clappia.slug(name): {
        "name": name, "forms": list(FORMS), "parent": None,
        "definition": {"title": name, "access": NOT_FOR_EXPERTS, "fields": fields}}
        for name, fields in made.items()}


def service_page() -> dict:
    """Used Car's own Ops-only page of service history (not shared: only Used Car has it)."""
    fields = [{**_text(clappia.slug(label), label), "helper_text": hint}
              for label, hint in SERVICE_HISTORY]
    fields.append(_text("service_history_analysis", "Service History Analysis", "long_text"))
    return {"title": SERVICE_PAGE, "sections": [
        {"title": SERVICE_PAGE, "access": NOT_FOR_EXPERTS, "fields": fields}]}


DELAY_PAGE = "Inspection Delay"


def share(specs: dict[str, dict], delay: list[dict]) -> tuple[dict, dict[str, dict], list[str]]:
    """(library, the three specs rebuilt on it, notes). `specs`: form key → converted spec;
    `delay`: the questions of the late-start page (convert.delay)."""
    sh = Sharing(specs)
    plan = sh.split()
    sh.share_fields(plan)
    forms = sh.rebuild(plan)
    ops = ops_sections()
    for spec in forms.values():                       # Ops' page comes first
        spec["pages"].insert(0, {"title": OPS_PAGE, "sections": [
            {"title": item["name"], "library": key,
             "fields": copy.deepcopy(item["definition"]["fields"])} for key, item in ops.items()]})
    # a late start and its payment: the expert's first page, after Ops' (owner, 2026-11-26)
    late = {clappia.slug(DELAY_PAGE): {"name": DELAY_PAGE, "forms": list(FORMS), "parent": None,
                                       "definition": {"title": DELAY_PAGE, "fields": delay}}}
    for spec in forms.values():
        spec["pages"].insert(1, {"title": DELAY_PAGE, "sections": [
            {"title": DELAY_PAGE, "library": clappia.slug(DELAY_PAGE),
             "fields": copy.deepcopy(delay)}]})
    forms["used_car"]["pages"].insert(1, service_page())
    library = {"sections": {**ops, **late, **sh.sections}, "fields": sh.fields}
    return library, forms, sh.notes


def with_children(titles: list[str], spec: dict) -> list[str]:
    """A rating category's sections plus the ones split off from them (their checks count)."""
    out = list(titles)
    for _, s in _sections(spec):
        if s.get("parent") in titles and s["title"] not in out:
            out.append(s["title"])
    return out
