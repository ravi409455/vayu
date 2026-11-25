"""Turns one Clappia app read-out (setup/data/*.json, read from garuda.clappia.com's designer, see
docs/clappia/README.md) into our form spec. Each form comes only from its own app: questions,
order, choices, required flags and show-rules are that app's (Used Car → PPI, New Car → PDI,
EV → EV). Our structure: readable keys, no Clappia score helpers, check-in / payment / review /
perfume in the shared Start / End forms, Ops-only ratings and Key Checks elsewhere.

A spec is plain data: {"pages": [{"title", "sections": [{"title", "fields": [field]}]}]}, a field
being {"key", "label", "type", "config", "required", "show_if", "helper_text", "clappia"}.
`problems` lists what could not be carried over (rules that point at nothing, unknown choices).
"""
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "data"

# Clappia sections that are not inspection checks, and where they go instead
NOT_INSPECTION = {
    "Report First Page": "ratings",       # Ops-typed ratings → our scoring + Key Checks
    "Key Checks": "key_checks",           # Ops-typed facts → our Key Checks
    "Inspection Details": "booking",      # copied from the booking
    "Expert Details": "start",            # check-in
    "Payment Details": "end",             # wrap-up
    "Google Review": "end",
    "Car Perfume": "end",
}
DROP_KINDS = {"app-formula", "app-dependency-app"}            # score helpers, booking lookup
SHOWN_ONLY = {"app-image-viewer", "app-read-only-file"}       # a picture shown to the expert


def load(app: str) -> dict:
    return json.loads((DATA / f"{app}.json").read_text())


def settings(f: dict) -> dict[str, str]:
    """The field's settings panel (Basic + Advanced tabs) as {label: value}."""
    return {k: v for k, v in [*f.get("basic", []), *f.get("advanced", [])]}


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower().replace("&", " and ")).strip("_")
    if not s or not s[0].isalpha():
        s = "q_" + s
    return s[:60]


def choices(f: dict) -> list[str]:
    """The answers a choice field offers, as Clappia shows them (in its order)."""
    opts = f["opts"] or [o for o in settings(f).get("Options", "").split("\n") if o.strip()]
    return [o.strip() for o in opts if o.strip()]


# ---------------------------------------------------------------- answer colours and severity
# Only the colour and severity of an answer's wording; the set of answers always comes from the
# question itself. bad = a problem (severity), warn = worth a look, ok = fine, muted = no answer.
BAD_MAJOR = {"not ok", "damaged", "major scratches", "major dents", "rusted", "replaced", "bent",
             "not working", "not opening", "present", "found", "port not working", "loose", "bad",
             "not matching", "leakage", "sludge present", "smoke", "noise", "vibration",
             "not working properly", "not charging", "acid leakage", "faulty", "empty",
             "not ok - battery", "corroded", "cracked", "torn", "worn out",
             "original wiring changed", "tar found", "oil present", "water mixed (no color)",
             "rusted/dissolved battery tray", "not smooth"}
BAD_MINOR = {"minor scratches", "minor dents", "repainted", "panel gaps", "scratches",
             "not opening comfortably", "yellowish", "average", "black particles present",
             "slightly loose", "hard", "low level", "oil change needed"}
CRITICAL = {"accidental"}
WARN = {"not able to check", "not checked", "not able to locate", "not matching but original",
        "expired", "covered - not able to see", "not available"}
MUTED = {"not applicable", "na", "not required", "stepney not available"}
OK = {"ok", "working", "available", "not present", "not found", "matching", "good", "clean",
      "yes", "smooth", "normal", "full", "high", "medium", "low", "clean and complete"}
# answers whose meaning flips with the question: "Yes" is bad for "any fault codes?", fine for
# "is the car starting?"; decided by these words in the question
YES_IS_BAD = re.compile(r"fault|leak|smoke|noise|vibrat|problem|warning|issue|damage|delay",
                        re.I)
PRESENT_IS_OK = re.compile(r"tool ?kit|spare|stepney|jack|equipment", re.I)


def tone_of(answer: str, question: str) -> tuple[str | None, str | None]:
    """(tone, severity or None) of one answer of one question."""
    a = answer.strip().lower()
    if a in ("yes", "no"):
        bad = (a == "yes") == bool(YES_IS_BAD.search(question))
        return ("bad", "major") if bad else ("ok", None)
    if a in ("present", "not present") and PRESENT_IS_OK.search(question):
        return ("ok", None) if a == "present" else ("bad", "major")
    if a in CRITICAL:
        return "bad", "critical"
    if a in BAD_MAJOR:
        return "bad", "major"
    if a in BAD_MINOR:
        return "warn", "minor"
    if a in WARN:
        return "warn", None
    if a in MUTED:
        return "muted", None
    if a in OK:
        return "ok", None
    return None, None


# ---------------------------------------------------------------- show-rules
class RuleError(ValueError):
    pass


def translate(rule: str, ns: str, fields: dict[str, dict]) -> Any:
    """A Clappia "Display this field if" formula as JsonLogic over our keys. `fields`: Clappia
    key → our field (key, type, options). Raises RuleError when it points at no known field."""
    tokens = re.findall(r"\{[^}]+\}|'[^']*'|\"[^\"]*\"|<>|>=|<=|[=<>(),]|[A-Za-z_]+|\d+", rule)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take(expect=None):
        nonlocal pos
        t = peek()
        if expect is not None and t != expect:
            raise RuleError(f"expected {expect} at {t!r} in {rule!r}")
        pos += 1
        return t

    def field(tok):
        f = fields.get(tok.strip("{}"))
        if f is None:
            raise RuleError(f"{tok} is not a field of this form")
        return f

    def var(f):
        return {"var": f"{ns}.{f['key']}"}

    def keys_of(f, text, exact):
        opts = f["config"].get("options", [])
        t = spell(text).lower() if exact else text.lower()
        hit = [o["key"] for o in opts if (o["label"].lower() == t if exact else t in
                                          o["label"].lower())]
        return hit

    def equals(f, text):
        if text == "":
            return {"!": var(f)}
        if f["type"] == "yes_no":
            return {"==": [var(f), text.lower() in ("true", "yes")]}
        if text in f.get("values", {}):                    # a system field's stored value
            return {"==": [var(f), f["values"][text]]}
        hit = keys_of(f, text, exact=True)
        if not hit:
            return {"==": [var(f), text]}
        if f["type"] == "multi_choice":
            return {"in": [hit[0], var(f)]}
        return {"==": [var(f), hit[0]]}

    def contains(f, text):
        hit = keys_of(f, text, exact=False)
        if f["type"] == "multi_choice":
            return {"some": [var(f), {"in": [{"var": ""}, hit]}]}
        return {"in": [var(f), hit]}

    def expr():
        t = peek()
        if t in ("AND", "OR"):
            take()
            take("(")
            parts = [expr()]
            while peek() == ",":
                take()
                parts.append(expr())
            take(")")
            return {"and" if t == "AND" else "or": parts} if len(parts) > 1 else parts[0]
        if t == "NOT":
            take()
            take("(")
            e = expr()
            take(")")
            return {"!": e}
        if t == "SEARCH":
            take()
            take("(")
            text = take().strip("'\"")
            take(",")
            f = field(take())
            take(")")
            op = take()
            num = take()
            found = contains(f, text)
            if (op, num) in ((">", "0"), ("<>", "0")):
                return found
            if (op, num) == ("=", "0"):
                return {"!": found}
            raise RuleError(f"unsupported SEARCH comparison in {rule!r}")
        if t and t.startswith("{"):
            f = field(take())
            op = take()
            text = take().strip("'\"")
            if op == "=":
                return equals(f, text)
            if op == "<>":
                return {"!": equals(f, text)}
            raise RuleError(f"unsupported operator {op} in {rule!r}")
        raise RuleError(f"cannot read {t!r} in {rule!r}")

    out = expr()
    if peek() is not None:
        raise RuleError(f"left over {tokens[pos:]} in {rule!r}")
    return out


# ---------------------------------------------------------------- clean-ups (agreed 2026-11-24)
# one spelling per answer
SPELLING = {"not able to check": "Not Able to Check", "na": "Not Applicable",
            "not applicable": "Not Applicable", "not available": "Not Available",
            "not working": "Not Working"}
# label typos
TYPOS = [(r"\bChasis\b", "Chassis"), (r"Code Support", "Core Support"),
         (r"\bBi-Fuel Certification\b", "Bi-Fuel Certificate")]
# typed boxes that hold a number: (label pattern, unit, min, max)
NUMBERS = [(r"km (current )?reading", "km", 0, 999999), (r"number of (car )?keys", "", 0, 10),
           (r"registration year", "", 1990, 2100), (r"charger output", "kW", 0, 400)]
# answer order: fine first, then problems mild to serious, then the neutral ones
RANK: dict[tuple[str | None, str | None], int] = {
    ("ok", None): 0, ("warn", "minor"): 1, ("bad", "major"): 2, ("bad", "critical"): 3,
    ("warn", None): 4, ("muted", None): 5}


def spell(answer: str) -> str:
    return SPELLING.get(answer.strip().lower(), answer.strip())


def tidy_label(label: str) -> str:
    label = " ".join(label.split())
    for pat, new in TYPOS:
        label = re.sub(pat, new, label)
    return label


def _bare(label: str) -> str:
    """A label without "photo(s) / image(s) / video" and punctuation, to pair a photo with its
    check."""
    s = re.sub(r"\b(photos?|images?|videos?|recording)\b", "", label.lower())
    return re.sub(r"[^a-z0-9]", "", s)


# ---------------------------------------------------------------- fields
def to_field(f: dict, taken: set[str], problems: list[str]) -> dict | None:
    """One Clappia field as ours (no show-rule yet), or None when it is dropped."""
    kind, label, st = f["kind"], tidy_label(f.get("_label") or f["label"]), settings(f)
    if kind in DROP_KINDS or "do not touch" in (f.get("desc") or "").lower():
        return None
    key = slug(label)
    n = 2
    while key in taken:
        key = f"{slug(label)[:57]}_{n}"
        n += 1
    taken.add(key)
    phase = _phase(st.get("Description") or f.get("desc") or "")
    if phase:
        label = f"{label} ({phase.lower()})"               # "Car KM Reading (after test drive)"
    out: dict[str, Any] = {"key": key, "label": label, "config": {}, "required": f["required"],
                           "helper_text": (st.get("Description") or f.get("desc") or "")[:200],
                           "clappia": f["key"]}
    if kind in ("app-radio", "app-check-box", "app-select"):
        opts = list(dict.fromkeys(spell(o) for o in choices(f)))
        out["type"] = "multi_choice" if kind == "app-check-box" else "single_choice"
        built = []
        tones = {o: tone_of(o, label) for o in opts}
        # a plain fact (car make, state, fuel, rim): none of its answers is a check word
        plain = (all(t is None for t, _ in tones.values()) or kind == "app-select"
                 or bool(re.search(r"\btype\b|\bsize\b|company|state|seat", label, re.I)))
        for o in opts:
            tone, sev = (None, None) if plain else tones[o]
            if tone is None and not plain:
                problems.append(f"no colour for answer {o!r} of {label!r}")
            opt: dict[str, Any] = {"key": slug(o), "label": o}
            if tone:
                opt["tone"] = tone
            if sev:
                opt.update(is_defect=True, severity=sev)
            built.append(opt)
        if not plain:
            built.sort(key=lambda o: RANK.get((o.get("tone"), o.get("severity")), 6))
        out["config"] = {"options": built}
        if kind == "app-select" or len(built) > 6:
            out["config"]["display"] = "dropdown"
    elif kind == "app-file":
        video = re.search(r"video|recording", label, re.I)
        out["type"] = "video" if video else "photo"
        n_files = int(st.get("Maximum number of files allowed") or 1)
        out["config"] = {"max_count": max(1, min(n_files, 3 if video else 10))}
    elif kind == "ng:input:text":
        num = next((n for n in NUMBERS if re.search(n[0], label, re.I)), None)
        if num is not None:                            # typed on Clappia, a number here
            out["type"] = "number"
            out["config"] = {"min": num[2], "max": num[3], **({"unit": num[1]} if num[1] else {})}
        elif "Validation" in st:                       # Clappia's text box has a Validation box
            out["type"] = "short_text"
            if st.get("Validation") == "Number":
                out["config"] = {"pattern": r"^\d+$", "pattern_message": "Numbers only"}
        else:                                          # its number box has none
            out["type"] = "number"
            for ours, theirs in (("min", "Minimum Value"), ("max", "Maximum Value")):
                v = st.get(theirs)
                if v is not None and v not in ("", "null"):
                    out["config"][ours] = int(float(v))
    elif kind == "app-text-area":
        out["type"] = "long_text"
    elif kind == "app-date-v2":
        out["type"] = "date"
    elif kind == "app-time":
        out["type"] = "time"
    elif kind == "app-location":
        out["type"] = "gps"
        out["config"] = {"auto": True}
    elif kind == "app-toggle":
        out["type"] = "yes_no"
    elif kind in SHOWN_ONLY:
        return None                                    # QR / instruction pictures: not answers
    else:
        problems.append(f"unknown Clappia field kind {kind} for {label!r}")
        return None
    return out


def convert(app: str, ns: str = "inspection", only: set[str] | None = None,
            system: Mapping[str, Any] | None = None) -> dict:
    """The spec of one app. `ns` is the form the rules are read in (inspection, start, end,
    booking); `only` limits it to those Clappia sections (e.g. the check-in ones). `system`:
    Clappia key → our system field it becomes ({"key", "type", optional "values": Clappia answer →
    our stored value}), or None to leave that Clappia field out (it is a double of one)."""
    system = system or {}
    data = load(app)
    problems: list[str] = []
    taken: set[str] = set()
    by_clappia: dict[str, dict] = {}
    rules: list[tuple[dict, str]] = []
    sections = []
    seen_checks: set[str] = set()
    seen_photos: set[str] = set()
    for s in data["sections"]:
        title = s["title"].strip()
        if only is not None and title not in only:
            continue
        if only is None and title in NOT_INSPECTION:
            continue
        fields = []
        last_check: dict | None = None
        section_checks: dict[str, dict] = {}
        for f in s["fields"]:
            if f["key"] in system and system[f["key"]] is None:
                continue
            f = dict(f)
            label = tidy_label(f["label"])
            twin = section_checks.get(_bare(label))
            if f["kind"] == "app-file" and not re.search(
                    r"photo|image|video|recording", label, re.I) and (
                    twin or any(_bare(x["label"]) == _bare(label) for x in s["fields"]
                                if x["kind"] in ("app-radio", "app-check-box"))):
                label = f"{twin['label'] if twin else label} photo"   # "Wiring" → "Wiring photo"
            if f["kind"] in ("app-radio", "app-check-box") and label.lower() in seen_checks:
                label = f"{label} ({title.lower()})"           # same check in two sections
            n = 2
            while f["kind"] == "app-file" and label.lower() in seen_photos:
                label = f"{re.sub(r' [0-9]+$', '', label)} {n}"
                n += 1
            f["_label"] = label
            ours = to_field(f, taken, problems)
            if ours is None:
                continue
            if f["key"] in system:
                ours.update(system[f["key"]] or {})
                if ours["type"] not in ("single_choice", "multi_choice"):
                    ours["config"].pop("options", None)        # e.g. Clappia Yes/No → yes_no
            if ns in ("end", "start") and ours["config"].get("options"):
                ours["config"]["options"] = [                  # facts, not checks: no tones
                    {"key": o["key"], "label": o["label"]} for o in ours["config"]["options"]]
            by_clappia[f["key"]] = ours
            rule = settings(f).get("Display this field if", "")
            if rule:
                rules.append((ours, rule))
            if ours["type"] in ("single_choice", "multi_choice"):
                last_check = ours
                section_checks[_bare(ours["label"])] = ours
                seen_checks.add(tidy_label(f["label"]).lower())
            elif ours["type"] in ("photo", "video"):
                seen_photos.add(ours["label"].lower())
                ours["_section"] = title
                if last_check is not None and _pairs(ours, last_check):
                    ours["_check"] = last_check
            fields.append(ours)
            if (app, title) in ADD_PROBLEM_PHOTOS and ours["type"] in ("single_choice",
                                                                         "multi_choice"):
                photo = to_field({"kind": "app-file", "required": False, "key": "",
                                  "_label": re.sub(r"\s*-\s*", " ", ours["label"]) + " Photos",
                                  "label": ""}, taken, problems)
                assert photo is not None                   # a photo field always converts
                photo.update(type="photo", _section=title, _check=ours)
                photo.pop("clappia")                       # ours: Clappia has no such photo
                fields.append(photo)
        if fields:
            phase = _phase(s.get("sdesc", ""))
            if phase and sum(x["title"].strip() == title for x in data["sections"]) > 1:
                title = f"{title} ({phase.lower()})"       # "Engine (after test drive)"
            sections.append({"title": title, "fields": fields, "_phase": phase,
                             "_rule": settings(s.get("settings") or {}).get(
                                 "Display this section if", "")})
    hidden = set()
    for ours, rule in rules:
        try:
            ours["show_if"] = translate(rule, ns, by_clappia)
        except RuleError as e:
            # a rule pointing at nothing (a removed or test field) means the field never shows
            # on Clappia: leave the field out instead of guessing
            hidden.add(ours["key"])
            problems.append(f"left out {ours['label']!r}: {e}")
    for s in sections:
        s["fields"] = [f for f in s["fields"] if f["key"] not in hidden]
        rule = s.pop("_rule", "")
        if rule:                                   # e.g. CNG only on a CNG car
            try:
                s["show_if"] = translate(rule, ns, by_clappia)
            except RuleError as e:
                problems.append(f"section {s['title']!r} rule kept out: {e}")
    pages: list[dict] = []
    for sec in sections:
        phase = sec.pop("_phase", None)
        if not sec["fields"]:
            continue
        title = PHASE_PAGES.get(phase or "", sec["title"])
        if phase and pages and pages[-1]["title"] == title:
            pages[-1]["sections"].append(sec)              # same phase, same page
        else:
            pages.append({"title": title, "sections": [sec]})
    spec = {"app": app, "pages": pages, "problems": problems}
    photo_rules(spec, app, ns, hidden)
    return spec


# Used Car's Clappia Exterior has checks but no photos: ours adds an on-problem photo per check
ADD_PROBLEM_PHOTOS = {("used_car_3_0", "Exterior Body")}
# the test drive, from Clappia's section and field descriptions ("Before / During / After Test
# Drive"): sections of one phase share a page; a repeated section or a field names its phase
PHASE_PAGES = {"Before test drive": "Before test drive", "During test drive": "Test drive",
               "After test drive": "After test drive"}


def _phase(text: str) -> str | None:
    m = re.fullmatch(r"\s*(before|during|after) test drive\s*", text or "", re.I)
    return f"{m.group(1).capitalize()} test drive" if m else None

# ---------------------------------------------------------------- photo rules (agreed 2026-11-24)
ISSUE_PHOTOS = re.compile(r"photos? of issues", re.I)
ALWAYS = re.compile(r"odometer|km reading|chassis|number plate|cng plate|obd|temperature|"
                    r"battery state|generator state|charger (port )?photo|"
                    r"underbody (left|right|front|rear)|"
                    r"wiring|oil quality|"
                    r"roof from inside|shocker|tool kit|selfie|car'?s number plate|payment|"
                    r"review|perfume|certificate", re.I)
ALWAYS_SECTIONS = {"Car Images From All Directions", "Car Details", "Car Documents", "Tyres"}
LIMIT_PROBLEM, LIMIT_ONE, LIMIT_ISSUES = 5, 1, 10


def _problem_rule(check: dict, ns: str) -> Any:
    bad = [o["key"] for o in check["config"].get("options", []) if o.get("is_defect")]
    if not bad:
        return None
    var = {"var": f"{ns}.{check['key']}"}
    return ({"some": [var, {"in": [{"var": ""}, bad]}]} if check["type"] == "multi_choice"
            else {"in": [var, bad]})


def _about(rule: Any, key: str) -> bool:
    return f'"{key}"' in json.dumps(rule) or f".{key}\"" in json.dumps(rule)


def photo_rules(spec: dict, app: str, ns: str, hidden: set[str]) -> None:
    """Every photo and video: camera only, the agreed limits, and when it is asked: always
    (readings, identity, videos, overview, tyres, Used Car's body frame) or only when its check
    finds a problem (then required). A rule about something else (CNG car, OBD scanned, a
    certificate available) is kept."""
    used_car = app == "used_car_3_0"
    for p in spec["pages"]:
        for s in p["sections"]:
            for f in s["fields"]:
                if f["type"] not in ("photo", "video"):
                    continue
                check = f.pop("_check", None)
                section = f.pop("_section", s["title"])
                f["config"] = {**f["config"], "capture": "camera"}
                if ISSUE_PHOTOS.search(f["label"]):
                    f["config"]["max_count"] = LIMIT_ISSUES
                    f["config"]["issue_photo"] = True        # printed with the issues
                    f["required"], f["show_if"] = False, None
                    continue
                frame = section == "Body Frame Accidental Checklist"
                if frame and not used_car and check is None and f.get("show_if"):
                    f["config"]["max_count"], f["required"] = LIMIT_PROBLEM, True
                    about = re.search(rf'"{ns}\.([a-z0-9_]+)"', json.dumps(f["show_if"]))
                    if about:
                        f["config"]["photo_of"] = about.group(1)   # its problem's check
                    continue                     # its own problem rule from Clappia: kept
                if section == "Car Documents" and check is not None and any(
                        o["key"] == "available" for o in check["config"].get("options", [])):
                    f["config"]["max_count"], f["required"] = LIMIT_ONE, True
                    f["show_if"] = {"==": [{"var": f"{ns}.{check['key']}"}, "available"]}
                    continue                     # a document's photo: only when it is there
                always = (f["type"] == "video" or section in ALWAYS_SECTIONS
                          or (used_car and frame)
                          or (not frame and bool(ALWAYS.search(f["label"])))
                          or check is None or check["key"] in hidden)
                rule = None if always else _problem_rule(check, ns)
                if rule is None:                       # always asked
                    f["config"]["max_count"] = LIMIT_ONE
                    if check is not None and f.get("show_if") and _about(f["show_if"],
                                                                         check["key"]):
                        f["show_if"] = None            # its check's problem rule is dropped
                    f["required"] = True
                else:                                  # only when the check finds a problem
                    f["config"]["max_count"] = LIMIT_PROBLEM
                    f["config"]["photo_of"] = check["key"]   # an issue photo when it fails
                    f["show_if"], f["required"] = rule, True


def _pairs(photo: dict, check: dict) -> bool:
    """Is this photo the picture of that check (right after it, about the same thing)?"""
    import difflib

    a, b = _bare(photo["label"]), _bare(check["label"])
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


