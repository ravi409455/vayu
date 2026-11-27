"""Per-type rules for fields: config validation (design time) and answer cleaning (runtime).

Required/visibility logic is not here; it lives in rules.py, which calls clean_answer for every
visible, non-empty answer.
"""
import math
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
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
# system fields copied into a booking column: never longer than the column (F-120)
COLUMN_LIMITS = {"booking_id": 64, "chassis_no": 64, "customer_name": 200}
CAPTURE_MODES = ("both", "camera", "upload")   # how an expert may add a photo or video
CAMERAS = ("back", "front")                     # which camera the Android app opens first
TONES = ("ok", "warn", "bad", "muted")           # print colour of a choice: green, amber, red, grey
# a field without its own maximum takes one file (plan batch 4, F-010: the same everywhere)
DEFAULT_MAX_COUNT = {"photo": 1, "video": 1, "file": 1}


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


def _check_choices(type: str, config: dict) -> None:
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


def _check_master_list(type: str, config: dict) -> None:
    if not MasterList.objects.filter(key=config.get("list")).exists():
        raise ConfigError(f"Master list '{config.get('list')}' does not exist.")


def _check_user_picker(type: str, config: dict) -> None:
    if config.get("role") not in ROLES:
        raise ConfigError(f"role must be one of {', '.join(ROLES)}.")


def _check_text(type: str, config: dict) -> None:
    _int_in(config, "max_length", 1, 500 if type == "short_text" else 10000)
    if not isinstance(config.get("scan", False), bool):
        raise ConfigError("scan must be true or false.")
    if "pattern" in config:
        try:
            regex.compile(config["pattern"])
        except (regex.error, TypeError) as e:
            raise ConfigError(f"Invalid pattern: {e}") from e


def _check_number(type: str, config: dict) -> None:
    for k in ("min", "max"):
        if k in config and not _is_number(config[k]):
            raise ConfigError(f"{k} must be a number.")
    if "min" in config and "max" in config and config["min"] > config["max"]:
        raise ConfigError("min must not be greater than max.")
    _int_in(config, "decimals", 0, 4)


def _check_image(type: str, config: dict) -> None:
    from .models import FormAsset

    asset = config.get("asset")
    try:
        known = isinstance(asset, str) and FormAsset.objects.filter(pk=asset).exists()
    except ValidationError:                       # not a UUID at all
        known = False
    if not known:
        raise ConfigError("Upload the picture first: asset must be an uploaded image.")


def _check_capture(type: str, config: dict) -> None:
    if config.get("capture", "both") not in CAPTURE_MODES:
        raise ConfigError(f"capture must be one of {', '.join(CAPTURE_MODES)}.")
    if config.get("camera", "back") not in CAMERAS:
        raise ConfigError(f"camera must be one of {', '.join(CAMERAS)}.")
    if not isinstance(config.get("ops_upload", True), bool):
        raise ConfigError("ops_upload must be true or false.")
    if not isinstance(config.get("hide_from_customer", False), bool):
        raise ConfigError("hide_from_customer must be true or false.")
    if not isinstance(config.get("issue_photo", False), bool):
        raise ConfigError("issue_photo must be true or false.")
    if "photo_of" in config and not (isinstance(config["photo_of"], str)
                                     and KEY_RE.fullmatch(config["photo_of"])):
        raise ConfigError("photo_of must be the key of a field.")
    _int_in(config, "min_count", 0, 30)
    _int_in(config, "max_count", 1, 30)
    if config.get("min_count", 0) > config.get("max_count", DEFAULT_MAX_COUNT[type]):
        raise ConfigError("min_count must not exceed max_count.")


def _check_file(type: str, config: dict) -> None:
    _int_in(config, "max_count", 1, 10)
    if not isinstance(config.get("ops_upload", True), bool):
        raise ConfigError("ops_upload must be true or false.")
    if not isinstance(config.get("hide_from_customer", False), bool):
        raise ConfigError("hide_from_customer must be true or false.")
    allowed = config.get("allowed", ["image", "pdf"])
    if not isinstance(allowed, list) or not allowed or set(allowed) - {"image", "pdf"}:
        raise ConfigError("allowed must be a non-empty subset of ['image', 'pdf'].")


def _check_derived(type: str, config: dict) -> None:
    if not isinstance(config.get("rule"), dict) or not config["rule"]:
        raise ConfigError("rule is required (a JsonLogic expression).")
    for k in ("true_label", "false_label"):
        if not str(config.get(k, "")).strip():
            raise ConfigError(f"{k} is required.")


def _check_rating(type: str, config: dict) -> None:
    if not LIST_KEY_RE.fullmatch(str(config.get("category", ""))):
        raise ConfigError("category is required (a lowercase key).")


def validate_config(type: str, config: Any) -> None:
    if not isinstance(config, dict):
        raise ConfigError("config must be an object.")
    spec = TYPES[type]
    unknown = set(config) - spec.config_keys
    if unknown:
        raise ConfigError(f"Unknown config keys for {type}: {', '.join(sorted(unknown))}.")
    if "auto" in config and not isinstance(config["auto"], bool):
        raise ConfigError("auto must be true or false.")
    spec.check_config(type, config)


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
        words = (f"Must be between {lo} and {hi}." if lo is not None and hi is not None
                 else f"Must be at least {lo}." if hi is None else f"Must be at most {hi}.")
        raise AnswerError("OUT_OF_RANGE", words)
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


def _clean_derived(field, value: Any) -> Any:
    if not isinstance(value, bool):
        raise AnswerError("INVALID_TYPE", "Choose yes or no.")
    return value


def _clean_rating(field, value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnswerError("INVALID_TYPE", "Enter a whole number.")
    if not 1 <= value <= 5:
        raise AnswerError("OUT_OF_RANGE", "Ratings are 1 to 5.")
    return value


def _clean_single(field, value: Any) -> Any:
    if not isinstance(value, str):
        raise AnswerError("INVALID_TYPE", "Choose one option.")
    if value not in _options(field):
        raise AnswerError("INVALID_OPTION", "Not one of the options.")
    return value


def _clean_multi(field, value: Any) -> Any:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise AnswerError("INVALID_TYPE", "Choose one or more options.")
    if len(set(value)) != len(value):
        raise AnswerError("DUPLICATE_OPTION", "An option was chosen twice.")
    if set(value) - set(_options(field)):
        raise AnswerError("INVALID_OPTION", "Not one of the options.")
    return value


def _clean_yes_no(field, value: Any) -> Any:
    if not isinstance(value, bool):
        raise AnswerError("INVALID_TYPE", "Choose yes or no.")
    return value


def _clean_master_list(field, value: Any) -> Any:
    if not isinstance(value, str):
        raise AnswerError("INVALID_TYPE", "Choose one option.")
    item = MasterListItem.objects.filter(list__key=field.config.get("list"), key=value).first()
    if item is None:
        raise AnswerError("INVALID_OPTION", "Not one of the options.")
    if item.archived:
        raise AnswerError("ARCHIVED_OPTION", "This option is no longer available.")
    return value


def _clean_form_choice(field, value: Any) -> Any:
    from .models import Form, FormType, VersionStatus

    if not isinstance(value, str):
        raise AnswerError("INVALID_TYPE", "Choose one option.")
    if not Form.objects.filter(type=FormType.CUSTOM, is_active=True, inspection_type=value,
                               versions__status=VersionStatus.PUBLISHED).exists():
        raise AnswerError("INVALID_OPTION", "Not one of the options.")
    return value


def _clean_user(field, value: Any) -> Any:
    from apps.accounts.models import User  # avoid an import cycle at module load

    if isinstance(value, bool) or not isinstance(value, int):
        raise AnswerError("INVALID_TYPE", "Choose a user.")
    if not User.objects.filter(pk=value, role=field.config.get("role"), is_active=True).exists():
        raise AnswerError("INVALID_USER", "Not an active user with the required role.")
    return value


def _clean_text(field, value: Any) -> Any:
    t, c = field.type, field.config
    if not isinstance(value, str):
        raise AnswerError("INVALID_TYPE", "Enter text.")
    text = value.strip() if t == "short_text" else value
    limit = min(c.get("max_length", DEFAULT_MAX_LENGTH[t]),
                COLUMN_LIMITS.get(field.key, DEFAULT_MAX_LENGTH[t]))
    if len(text) > limit:
        raise AnswerError("TOO_LONG", f"Use at most {limit} characters.")
    if c.get("pattern"):
        try:
            matched = regex.fullmatch(c["pattern"], text, timeout=REGEX_TIMEOUT_S)
        except TimeoutError as e:
            raise AnswerError("PATTERN_TIMEOUT", "Could not check this value.") from e
        if not matched:
            raise AnswerError("PATTERN_MISMATCH", c.get("pattern_message") or "Wrong format.")
    return text


def _clean_number(field, value: Any) -> Any:
    c = field.config
    return _number(value, decimals=c.get("decimals", 0), lo=c.get("min"), hi=c.get("max"))


def _clean_currency(field, value: Any) -> Any:
    return _number(value, decimals=2, lo=0)


def _clean_phone(field, value: Any) -> Any:
    return _phone(value)


def _clean_date(field, value: Any) -> Any:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise AnswerError("INVALID_DATE", "Use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as e:
        raise AnswerError("INVALID_DATE", "Not a real date.") from e


def _clean_time(field, value: Any) -> Any:
    if not isinstance(value, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?",
                                                      value):
        raise AnswerError("INVALID_TIME", "Use HH:MM (24-hour).")
    return value[:5]


def _clean_datetime(field, value: Any) -> Any:
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError as e:
        raise AnswerError("INVALID_DATETIME", "Use an ISO date-time.") from e
    if dt.tzinfo is None:
        raise AnswerError("NAIVE_DATETIME", "Date-time needs a timezone.")
    return dt.astimezone(IST).isoformat(timespec="seconds")


def _clean_gps(field, value: Any) -> Any:
    if (not isinstance(value, dict) or set(value) - {"lat", "lng", "accuracy"}
            or not _is_number(value.get("lat")) or not _is_number(value.get("lng"))
            or not -90 <= value["lat"] <= 90 or not -180 <= value["lng"] <= 180
            or ("accuracy" in value and not (_is_number(value["accuracy"])
                                             and value["accuracy"] >= 0))):
        raise AnswerError("INVALID_GPS", "Invalid location.")
    return value


def _clean_files(field, value: Any) -> Any:
    c = field.config
    if not isinstance(value, list):
        raise AnswerError("INVALID_TYPE", "Expected a list of media.")
    ids = [_uuid(v) for v in value]
    if len(set(ids)) != len(ids):
        raise AnswerError("DUPLICATE_MEDIA", "The same file was attached twice.")
    if len(ids) < c.get("min_count", 0):
        raise AnswerError("TOO_FEW", f"Add at least {c.get('min_count')}.")
    max_count = c.get("max_count", DEFAULT_MAX_COUNT[field.type])
    if len(ids) > max_count:
        raise AnswerError("TOO_MANY", f"Add at most {max_count}.")
    return ids


def _clean_signature(field, value: Any) -> Any:
    if not isinstance(value, str):
        raise AnswerError("INVALID_TYPE", "Expected one signature.")
    return _uuid(value)


def _no_answer(field, value: Any) -> Any:
    raise AnswerError("NOT_ANSWERABLE", "This field only shows a picture; it takes no answer.")


def _no_check(type: str, config: dict) -> None:
    """Nothing beyond the allowed keys (form_choice: the choices are the custom forms)."""


@dataclass(frozen=True)
class FieldType:
    """Everything the server knows about one field type (F-043, plan-quality Q3): a new type is
    one entry in TYPES. value=False: a file or picture, a link rather than a value (never a row,
    a check or a webhook value); system=True: filled by the system, only overridden by Ops."""

    config_keys: frozenset
    clean: Callable[[Any, Any], Any]
    check_config: Callable[[str, dict], None] = _no_check
    value: bool = True
    choice: bool = False
    system: bool = False


def _keys(*names: str) -> frozenset:
    return frozenset(names)


TYPES: dict[str, FieldType] = {
    "single_choice": FieldType(_keys("options", "display"), _clean_single, _check_choices,
                               choice=True),
    "multi_choice": FieldType(_keys("options", "display"), _clean_multi, _check_choices,
                              choice=True),
    "yes_no": FieldType(_keys(), _clean_yes_no),
    "currency": FieldType(_keys(), _clean_currency),
    "phone": FieldType(_keys(), _clean_phone),
    "signature": FieldType(_keys(), _clean_signature, value=False),
    "date": FieldType(_keys("auto"), _clean_date),
    "time": FieldType(_keys("auto"), _clean_time),
    "datetime": FieldType(_keys("auto"), _clean_datetime),
    "gps": FieldType(_keys("auto"), _clean_gps),
    "image": FieldType(_keys("asset", "name"), _no_answer, _check_image, value=False),
    "master_list": FieldType(_keys("list"), _clean_master_list, _check_master_list),
    "form_choice": FieldType(_keys(), _clean_form_choice),
    "user_picker": FieldType(_keys("role"), _clean_user, _check_user_picker),
    # scan: the Android app offers to read it with the camera (the expert can still type over it)
    "short_text": FieldType(_keys("max_length", "pattern", "pattern_message", "scan"),
                            _clean_text, _check_text),
    "long_text": FieldType(_keys("max_length"), _clean_text, _check_text),
    "number": FieldType(_keys("unit", "min", "max", "decimals"), _clean_number, _check_number),
    # issue_photo: always an issue photo when filled; photo_of: the check this photo shows
    # ops_upload: Ops and Admin may add or replace this field's files on the web (default yes)
    # camera: which camera the Android app opens first (default back); the expert can still flip
    # hide_from_customer: never in the report, its downloads, integrations or a ZIP (default no)
    "photo": FieldType(_keys("min_count", "max_count", "capture", "issue_photo", "photo_of",
                             "ops_upload", "camera", "hide_from_customer"), _clean_files,
                       _check_capture, value=False),
    "video": FieldType(_keys("min_count", "max_count", "capture", "ops_upload", "camera",
                             "hide_from_customer"), _clean_files, _check_capture, value=False),
    "file": FieldType(_keys("max_count", "allowed", "ops_upload", "hide_from_customer"),
                      _clean_files, _check_file, value=False),
    "derived": FieldType(_keys("rule", "true_label", "false_label"), _clean_derived,
                         _check_derived, system=True),
    "rating": FieldType(_keys("category"), _clean_rating, _check_rating, system=True),
}
ALLOWED_KEYS: dict[str, set[str]] = {t: set(s.config_keys) for t, s in TYPES.items()}
NOT_VALUES = frozenset(t for t, s in TYPES.items() if not s.value)     # photo, video, ... image
CHOICES = frozenset(t for t, s in TYPES.items() if s.choice)
SYSTEM_FILLED = frozenset(t for t, s in TYPES.items() if s.system)


def clean_answer(field, value: Any, *, override: bool = False) -> Any:
    """Validate one non-empty answer and return its stored form. Raises AnswerError."""
    spec = TYPES.get(field.type)
    if spec is None:
        raise AnswerError("UNKNOWN_TYPE", f"Unknown field type {field.type}.")
    if spec.system and not override:
        raise AnswerError("SYSTEM_FILLED", "This value is filled by the system.")
    return spec.clean(field, value)
