"""Per-type rules for fields: config validation (design time) and answer cleaning (runtime).

Required/visibility logic is not here; it lives in rules.py, which calls clean_answer for every
visible, non-empty answer.
"""
import math
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import regex
from django.core.exceptions import ValidationError

from apps.core.phone import InvalidPhone
from apps.core.phone import normalize as normalize_phone

from .models import KEY_RE, LIST_KEY_RE, MasterList, MasterListItem

IST = ZoneInfo("Asia/Kolkata")
SEVERITIES = ("minor", "major", "critical")
ROLES = ("expert", "ops", "admin")
REGEX_TIMEOUT_S = 0.1
DEFAULT_MAX_LENGTH = {"short_text": 200, "long_text": 5000}
CAPTURE_MODES = ("both", "camera", "upload")   # how an expert may add a photo or video
TONES = ("ok", "warn", "bad", "muted")           # print colour of a choice: green, amber, red, grey
DEFAULT_MAX_COUNT = {"photo": 10, "video": 3, "file": 5}

ALLOWED_KEYS: dict[str, set[str]] = {
    "single_choice": {"options", "display"},
    "multi_choice": {"options", "display"},
    "yes_no": set(), "currency": set(), "phone": set(), "signature": set(),
    "date": {"auto"}, "time": {"auto"}, "datetime": {"auto"}, "gps": {"auto"},
    "image": {"asset", "name"},
    "master_list": {"list"},
    "form_choice": set(),
    "user_picker": {"role"},
    "short_text": {"max_length", "pattern", "pattern_message"},
    "long_text": {"max_length"},
    "number": {"unit", "min", "max", "decimals"},
    # issue_photo: always an issue photo when filled; photo_of: the check this photo shows
    "photo": {"min_count", "max_count", "capture", "issue_photo", "photo_of"},
    "video": {"min_count", "max_count", "capture"},
    "file": {"max_count", "allowed"},
    "derived": {"rule", "true_label", "false_label"},
    "rating": {"category"},
}


class ConfigError(ValueError):
    pass


class AnswerError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- design time

def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _int_in(config: dict, key: str, lo: int, hi: int) -> None:
    v = config.get(key)
    if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi):
        raise ConfigError(f"{key} must be a whole number between {lo} and {hi}.")


def validate_config(type: str, config: Any) -> None:
    if not isinstance(config, dict):
        raise ConfigError("config must be an object.")
    unknown = set(config) - ALLOWED_KEYS[type]
    if unknown:
        raise ConfigError(f"Unknown config keys for {type}: {', '.join(sorted(unknown))}.")
    if "auto" in config and not isinstance(config["auto"], bool):
        raise ConfigError("auto must be true or false.")

    if type in ("single_choice", "multi_choice"):
        options = config.get("options")
        if not isinstance(options, list) or not options:
            raise ConfigError("options must be a non-empty list.")
        seen = set()
        for o in options:
            if not isinstance(o, dict) or not LIST_KEY_RE.fullmatch(str(o.get("key", ""))):
                raise ConfigError("Each option needs a lowercase key.")
            if not str(o.get("label", "")).strip():
                raise ConfigError(f"Option '{o['key']}' needs a label.")
            if o["key"] in seen:
                raise ConfigError(f"Duplicate option key '{o['key']}'.")
            seen.add(o["key"])
            if set(o) - {"key", "label", "is_defect", "severity", "tone"}:
                raise ConfigError(f"Option '{o['key']}' has unknown properties.")
            if o.get("tone", "ok") not in TONES:
                raise ConfigError(f"Option '{o['key']}': tone must be one of {', '.join(TONES)}.")
            defect, severity = o.get("is_defect", False), o.get("severity")
            if not isinstance(defect, bool):
                raise ConfigError("is_defect must be true or false.")
            if defect and severity not in SEVERITIES:
                raise ConfigError(f"Defect option '{o['key']}' needs a severity "
                                  f"({'/'.join(SEVERITIES)}).")
            if not defect and severity is not None:
                raise ConfigError(f"Option '{o['key']}' has a severity but is not a defect.")
        if config.get("display", "buttons") not in ("buttons", "dropdown"):
            raise ConfigError("display must be 'buttons' or 'dropdown'.")
    elif type == "master_list":
        if not MasterList.objects.filter(key=config.get("list")).exists():
            raise ConfigError(f"Master list '{config.get('list')}' does not exist.")
    elif type == "form_choice":
        pass                                  # the choices are the custom forms; nothing to set
    elif type == "user_picker":
        if config.get("role") not in ROLES:
            raise ConfigError(f"role must be one of {', '.join(ROLES)}.")
    elif type in ("short_text", "long_text"):
        _int_in(config, "max_length", 1, 500 if type == "short_text" else 10000)
        if "pattern" in config:
            try:
                regex.compile(config["pattern"])
            except (regex.error, TypeError) as e:
                raise ConfigError(f"Invalid pattern: {e}") from e
    elif type == "number":
        for k in ("min", "max"):
            if k in config and not _is_number(config[k]):
                raise ConfigError(f"{k} must be a number.")
        if "min" in config and "max" in config and config["min"] > config["max"]:
            raise ConfigError("min must not be greater than max.")
        _int_in(config, "decimals", 0, 4)
    elif type == "image":
        from .models import FormAsset

        asset = config.get("asset")
        try:
            known = isinstance(asset, str) and FormAsset.objects.filter(pk=asset).exists()
        except ValidationError:                       # not a UUID at all
            known = False
        if not known:
            raise ConfigError("Upload the picture first: asset must be an uploaded image.")
    elif type in ("photo", "video"):
        if config.get("capture", "both") not in CAPTURE_MODES:
            raise ConfigError(f"capture must be one of {', '.join(CAPTURE_MODES)}.")
        if not isinstance(config.get("issue_photo", False), bool):
            raise ConfigError("issue_photo must be true or false.")
        if "photo_of" in config and not (isinstance(config["photo_of"], str)
                                         and KEY_RE.fullmatch(config["photo_of"])):
            raise ConfigError("photo_of must be the key of a field.")
        _int_in(config, "min_count", 0, 30)
        _int_in(config, "max_count", 1, 30)
        if config.get("min_count", 0) > config.get("max_count", DEFAULT_MAX_COUNT[type]):
            raise ConfigError("min_count must not exceed max_count.")
    elif type == "file":
        _int_in(config, "max_count", 1, 10)
        allowed = config.get("allowed", ["image", "pdf"])
        if not isinstance(allowed, list) or not allowed or set(allowed) - {"image", "pdf"}:
            raise ConfigError("allowed must be a non-empty subset of ['image', 'pdf'].")
    elif type == "derived":
        if not isinstance(config.get("rule"), dict) or not config["rule"]:
            raise ConfigError("rule is required (a JsonLogic expression).")
        for k in ("true_label", "false_label"):
            if not str(config.get(k, "")).strip():
                raise ConfigError(f"{k} is required.")
    elif type == "rating":
        if not LIST_KEY_RE.fullmatch(str(config.get("category", ""))):
            raise ConfigError("category is required (a lowercase key).")


# ---------------------------------------------------------------- runtime

def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | dict):
        return len(value) == 0
    return False


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise AnswerError("INVALID_TYPE", "Enter a number.")
    if isinstance(value, float) and not math.isfinite(value):
        raise AnswerError("INVALID_TYPE", "Enter a number.")
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation as e:
        raise AnswerError("INVALID_TYPE", "Enter a number.") from e
    if not d.is_finite():
        raise AnswerError("INVALID_TYPE", "Enter a number.")
    return d


def _number(value: Any, *, decimals: int, lo=None, hi=None) -> int | float:
    d = _decimal(value)
    exponent = d.normalize().as_tuple().exponent
    if isinstance(exponent, int) and -exponent > decimals:
        raise AnswerError("TOO_MANY_DECIMALS", f"Use at most {decimals} decimal places.")
    if (lo is not None and d < Decimal(str(lo))) or (hi is not None and d > Decimal(str(hi))):
        raise AnswerError("OUT_OF_RANGE", f"Must be between {lo} and {hi}.")
    return int(d) if d == d.to_integral_value() else float(d)


def _uuid(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError as e:
        raise AnswerError("INVALID_MEDIA_ID", "Invalid media reference.") from e


def _phone(value: Any) -> str:
    if not isinstance(value, str):
        raise AnswerError("INVALID_TYPE", "Enter a phone number.")
    try:
        return normalize_phone(value)
    except InvalidPhone as e:
        raise AnswerError("INVALID_PHONE", str(e)) from e


def _options(field) -> dict[str, dict]:
    return {o["key"]: o for o in field.config.get("options", [])}


def clean_answer(field, value: Any, *, override: bool = False) -> Any:
    """Validate one non-empty answer and return its stored form. Raises AnswerError."""
    t, c = field.type, field.config
    if t == "image":
        raise AnswerError("NOT_ANSWERABLE", "This field only shows a picture; it takes no answer.")
    if t in ("derived", "rating"):
        if not override:
            raise AnswerError("SYSTEM_FILLED", "This value is filled by the system.")
        if t == "derived":
            if not isinstance(value, bool):
                raise AnswerError("INVALID_TYPE", "Choose yes or no.")
            return value
        if isinstance(value, bool) or not isinstance(value, int):
            raise AnswerError("INVALID_TYPE", "Enter a whole number.")
        if not 1 <= value <= 5:
            raise AnswerError("OUT_OF_RANGE", "Ratings are 1 to 5.")
        return value

    if t == "single_choice":
        if not isinstance(value, str):
            raise AnswerError("INVALID_TYPE", "Choose one option.")
        if value not in _options(field):
            raise AnswerError("INVALID_OPTION", "Not one of the options.")
        return value
    if t == "multi_choice":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise AnswerError("INVALID_TYPE", "Choose one or more options.")
        if len(set(value)) != len(value):
            raise AnswerError("DUPLICATE_OPTION", "An option was chosen twice.")
        if set(value) - set(_options(field)):
            raise AnswerError("INVALID_OPTION", "Not one of the options.")
        return value
    if t == "yes_no":
        if not isinstance(value, bool):
            raise AnswerError("INVALID_TYPE", "Choose yes or no.")
        return value
    if t == "master_list":
        if not isinstance(value, str):
            raise AnswerError("INVALID_TYPE", "Choose one option.")
        item = MasterListItem.objects.filter(list__key=c.get("list"), key=value).first()
        if item is None:
            raise AnswerError("INVALID_OPTION", "Not one of the options.")
        if item.archived:
            raise AnswerError("ARCHIVED_OPTION", "This option is no longer available.")
        return value
    if t == "form_choice":
        from .models import Form, FormType, VersionStatus

        if not isinstance(value, str):
            raise AnswerError("INVALID_TYPE", "Choose one option.")
        if not Form.objects.filter(type=FormType.CUSTOM, is_active=True, inspection_type=value,
                                   versions__status=VersionStatus.PUBLISHED).exists():
            raise AnswerError("INVALID_OPTION", "Not one of the options.")
        return value
    if t == "user_picker":
        from apps.accounts.models import User  # avoid an import cycle at module load

        if isinstance(value, bool) or not isinstance(value, int):
            raise AnswerError("INVALID_TYPE", "Choose a user.")
        if not User.objects.filter(pk=value, role=c.get("role"), is_active=True).exists():
            raise AnswerError("INVALID_USER", "Not an active user with the required role.")
        return value
    if t in ("short_text", "long_text"):
        if not isinstance(value, str):
            raise AnswerError("INVALID_TYPE", "Enter text.")
        text = value.strip() if t == "short_text" else value
        if len(text) > c.get("max_length", DEFAULT_MAX_LENGTH[t]):
            raise AnswerError("TOO_LONG", "Too long.")
        if c.get("pattern"):
            try:
                matched = regex.fullmatch(c["pattern"], text, timeout=REGEX_TIMEOUT_S)
            except TimeoutError as e:
                raise AnswerError("PATTERN_TIMEOUT", "Could not check this value.") from e
            if not matched:
                raise AnswerError("PATTERN_MISMATCH", c.get("pattern_message") or
                                  "Wrong format.")
        return text
    if t == "number":
        return _number(value, decimals=c.get("decimals", 0), lo=c.get("min"), hi=c.get("max"))
    if t == "currency":
        return _number(value, decimals=2, lo=0)
    if t == "phone":
        return _phone(value)
    if t == "date":
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise AnswerError("INVALID_DATE", "Use YYYY-MM-DD.")
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as e:
            raise AnswerError("INVALID_DATE", "Not a real date.") from e
    if t == "time":
        if not isinstance(value, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?",
                                                          value):
            raise AnswerError("INVALID_TIME", "Use HH:MM (24-hour).")
        return value[:5]
    if t == "datetime":
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError as e:
            raise AnswerError("INVALID_DATETIME", "Use an ISO date-time.") from e
        if dt.tzinfo is None:
            raise AnswerError("NAIVE_DATETIME", "Date-time needs a timezone.")
        return dt.astimezone(IST).isoformat(timespec="seconds")
    if t == "gps":
        if (not isinstance(value, dict) or set(value) - {"lat", "lng", "accuracy"}
                or not _is_number(value.get("lat")) or not _is_number(value.get("lng"))
                or not -90 <= value["lat"] <= 90 or not -180 <= value["lng"] <= 180
                or ("accuracy" in value and not (_is_number(value["accuracy"])
                                                 and value["accuracy"] >= 0))):
            raise AnswerError("INVALID_GPS", "Invalid location.")
        return value
    if t in ("photo", "video", "file"):
        if not isinstance(value, list):
            raise AnswerError("INVALID_TYPE", "Expected a list of media.")
        ids = [_uuid(v) for v in value]
        if len(set(ids)) != len(ids):
            raise AnswerError("DUPLICATE_MEDIA", "The same file was attached twice.")
        if len(ids) < c.get("min_count", 0):
            raise AnswerError("TOO_FEW", f"Add at least {c.get('min_count')}.")
        max_count = c.get("max_count", DEFAULT_MAX_COUNT[t])
        if len(ids) > max_count:
            raise AnswerError("TOO_MANY", f"Add at most {max_count}.")
        return ids
    if t == "signature":
        if not isinstance(value, str):
            raise AnswerError("INVALID_TYPE", "Expected one signature.")
        return _uuid(value)
    raise AnswerError("UNKNOWN_TYPE", f"Unknown field type {t}.")
