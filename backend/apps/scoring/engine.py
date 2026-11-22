"""Rating maths: pure functions, no database. Numbers and rules: REQUIREMENTS §5.4.

Each category starts at 5; every defect in its sections subtracts by severity; the result is
floored at 1 and rounded half up. The overall rating is the average of the category values, turned
into a word; any critical defect anywhere caps the word at 'average'."""
import math
import re

DEFAULT_CONFIG = {
    "deductions": {"minor": 0.25, "major": 1, "critical": 3},
    "thresholds": {"excellent": 4.5, "good": 3.5, "average": 2.5},
}
WORDS = ("excellent", "good", "average", "bad")
CATEGORY_KEY = re.compile(r"[a-z][a-z0-9_]{1,31}")


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def category_value(severities: list[str], deductions: dict, cap: int | None = None) -> int:
    value = max(1.0, 5 - sum(deductions[s] for s in severities))
    rounded = round_half_up(value)
    if cap is not None and "critical" in severities:
        rounded = min(rounded, cap)
    return rounded


def word_for(average: float, thresholds: dict) -> str:
    for word in ("excellent", "good", "average"):
        if average >= thresholds[word]:
            return word
    return "bad"


def overall_result(values: list[int], thresholds: dict, any_critical: bool) -> dict:
    if not values:
        return {"average": None, "word": None}
    average = round(sum(values) / len(values), 2)
    word = word_for(average, thresholds)
    if any_critical and WORDS.index(word) < WORDS.index("average"):
        word = "average"                      # a critical defect never allows better than average
    return {"average": average, "word": word}


def _num(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def validate_config(cfg) -> None:
    """Raises ValueError. An empty config is valid (no ratings configured)."""
    if not isinstance(cfg, dict) or set(cfg) - {"categories", "deductions", "thresholds"}:
        raise ValueError("rating config may only hold categories, deductions and thresholds.")
    if "categories" in cfg:
        cats = cfg["categories"]
        if not isinstance(cats, list):
            raise ValueError("categories must be a list.")
        keys: set[str] = set()
        titles: set[str] = set()
        for c in cats:
            if not isinstance(c, dict) or set(c) - {"key", "label", "sections", "cap"}:
                raise ValueError("A category needs key, label, sections (and optionally cap).")
            if not CATEGORY_KEY.fullmatch(str(c.get("key", ""))) or c["key"] in keys:
                raise ValueError("Category keys are unique lowercase slugs.")
            keys.add(c["key"])
            if not isinstance(c.get("label"), str) or not c["label"].strip():
                raise ValueError(f"Category '{c['key']}' needs a label.")
            sections = c.get("sections")
            if (not isinstance(sections, list) or not sections
                    or not all(isinstance(t, str) and t.strip() for t in sections)):
                raise ValueError(f"Category '{c['key']}' needs section titles.")
            if titles & set(sections):
                raise ValueError("A section can feed only one category.")
            titles |= set(sections)
            cap = c.get("cap")
            if cap is not None and (not isinstance(cap, int) or isinstance(cap, bool)
                                    or not 1 <= cap <= 5):
                raise ValueError("cap must be a whole number from 1 to 5.")
    if "deductions" in cfg:
        d = cfg["deductions"]
        if (not isinstance(d, dict) or set(d) != {"minor", "major", "critical"}
                or not all(_num(v) and v >= 0 for v in d.values())
                or not d["minor"] <= d["major"] <= d["critical"]):
            raise ValueError("deductions need minor <= major <= critical, all >= 0.")
    if "thresholds" in cfg:
        t = cfg["thresholds"]
        if (not isinstance(t, dict) or set(t) != {"excellent", "good", "average"}
                or not all(_num(v) and 1 <= v <= 5 for v in t.values())
                or not t["excellent"] > t["good"] > t["average"]):
            raise ValueError("thresholds need excellent > good > average, each from 1 to 5.")
