"""Makes plan.json for the review page from the real form files: the forms as they are on this
branch (backend/apps/platform/setup/frozen), the library, and what changed in each form against
the forms before shared sections (before/*.json, main's files of 2026-11-25).
    python3 docs/common-sections/build_page_data.py"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1] / "backend"
sys.path.insert(0, str(ROOT))
FROZEN = ROOT / "apps/platform/setup/frozen"
NAME = {"pdi": "PDI", "used_car": "Used Car", "ev": "EV"}
ALIAS = {"driver orvm controls": "driver orvm control", "passenger orvm controls": "passenger orvm control",
         "car variant": "variant", "bi fuel certification": "bi fuel certificate",
         "engine noise recording": "engine noise video", "wiring image": "wiring photo",
         "driver back indicator light": "driver back indicator",
         "passenger back indicator light": "passenger back indicator"}


RENAMED = {"Body Frame Accidental Checklist": "Body Frame", "Equipments": "Tool Kit"}


def norm(label):
    s = re.sub(r"\((before|after) test drive\)|\(electrical and interior\)", "", label.lower())
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return ALIAS.get(s, s)


def opts(f):
    return [o["label"] for o in f.get("config", {}).get("options") or []]


def rows(spec):
    return [(p["title"], s, f) for p in spec["pages"] for s in p["sections"] for f in s["fields"]]


def when(f, form=None):
    rule = json.dumps(f.get("show_if") or "")
    if "booking.inspection_type" in rule:        # always on Used Car, else on a problem
        return "always, required" if form == "used_car" else "only on a problem / condition, then required"
    if f.get("show_if"):
        return "only on a problem / condition" + (", then required" if f.get("required") else "")
    return "always, required" if f.get("required") else "always, optional"


lib = json.loads((FROZEN / "library.json").read_text())
out = {"forms": {}, "library": [], "shared_fields": [], "changes": {},
       "conflicts": json.loads((HERE / "decisions.json").read_text())}
for key, item in lib["sections"].items():
    out["library"].append({"name": item["name"], "forms": [NAME[k] for k in item["forms"]],
                           "parent": item["parent"], "ops": bool(item["definition"].get("access")),
                           "fields": [{"label": f["label"], "type": f["type"], "options": opts(f),
                                       "pending": [], "new_for": []}
                                      for f in item["definition"]["fields"]]})
for key, item in lib["fields"].items():
    f = item["definition"]
    out["shared_fields"].append({"label": f["label"], "type": f["type"], "group": item["group"],
                                 "forms": [NAME[k] for k in item["forms"]], "pending": [],
                                 "options": opts(f)})

for k, name in NAME.items():
    new = json.loads((FROZEN / f"{k}.json").read_text())["spec"]
    old = json.loads((HERE / "before" / f"{k}.json").read_text())["spec"]
    for pg in old["pages"]:               # a section only renamed is the same section
        for sec in pg["sections"]:
            sec["title"] = RENAMED.get(sec["title"], sec["title"])
    # ---- the form as it is now
    secs = []
    for p in new["pages"]:
        for s in p["sections"]:
            item = lib["sections"].get(s.get("library", ""))
            kind = "own" if item is None else ("master3" if len(item["forms"]) == 3 else "master2")
            if [f["key"] for f in s["fields"]] == ["chassis_no"]:
                kind = "builtin"
            secs.append({"page": p["title"], "name": s["title"], "kind": kind,
                         "parent": s.get("parent"),
                         "ops": bool(item and item["definition"].get("access")),
                         "fields": [{"label": f["label"], "type": f["type"], "options": opts(f),
                                     "where": "master" if item else "built-in" if kind == "builtin"
                                     else "shared field" if f.get("library") else "own",
                                     "pending": []} for f in s["fields"]]})
    out["forms"][name] = secs
    # ---- what changed against the form before
    olds = rows(old)
    left = list(range(len(olds)))
    ch = {"added": [], "removed": [], "renamed": [], "answers": [], "asked": [], "moved": {},
          "same": 0, "before": len(olds), "after": 0}
    for page, s, f in rows(new):
        ch["after"] += 1
        base = s.get("parent") or s["title"]
        n = norm(f["label"])
        hit = next((i for i in left if olds[i][2]["key"] == f["key"] and norm(olds[i][2]["label"]) == n), None)
        if hit is None:      # same key, same kind of question, in the same section: a rename
            hit = next((i for i in left if olds[i][2]["key"] == f["key"] and olds[i][2]["type"] == f["type"]
                        and olds[i][1]["title"] == base), None)
        if hit is None:
            hit = next((i for i in left if norm(olds[i][2]["label"]) == n and olds[i][1]["title"] == base), None)
        if hit is None:
            cands = [i for i in left if norm(olds[i][2]["label"]) == n]
            hit = cands[0] if len(cands) == 1 else None
        if hit is None:
            ch["added"].append({"label": f["label"], "section": s["title"], "type": f["type"], "when": when(f, k)})
            continue
        left.remove(hit)
        _, os_, of = olds[hit]
        changed = False
        if of["label"] != f["label"]:
            ch["renamed"].append({"from": of["label"], "to": f["label"], "section": s["title"]}); changed = True
        if opts(of) != opts(f):
            a, b = opts(of), opts(f)
            ch["answers"].append({"label": f["label"], "section": s["title"],
                                  "added": [x for x in b if x not in a], "removed": [x for x in a if x not in b],
                                  "reordered": sorted(a) == sorted(b)}); changed = True
        if when(of, k) != when(f, k):
            ch["asked"].append({"label": f["label"], "section": s["title"], "from": when(of, k), "to": when(f, k)}); changed = True
        if os_["title"] != s["title"]:
            ch["moved"].setdefault(f"{os_['title']} → {s['title']}", []).append(f["label"])
        elif not changed:
            ch["same"] += 1
    for i in left:
        _, os_, of = olds[i]
        ch["removed"].append({"label": of["label"], "section": os_["title"], "type": of["type"]})
    out["changes"][name] = ch
    print(name, {a: (len(v) if not isinstance(v, int) else v) for a, v in ch.items()})
(HERE / "plan.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
