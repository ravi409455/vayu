"""The forms the setup puts on a server: our own form files in setup/frozen/, made once from the
Clappia apps (`manage.py freeze_forms`, see convert.py) and kept by hand from then on. Each holds
{"spec": pages → sections → fields, "extra": version settings (Key Checks, rating config)}."""
import json
from pathlib import Path

FROZEN = Path(__file__).parent / "frozen"
# (form key, name, inspection type, Clappia app it was made from)
INSPECTIONS = [("pdi", "PDI", "pdi", "new_car_3_0"),
               ("used_car", "Used Car", "used_car", "used_car_3_0"),
               ("ev", "EV", "ev", "ev_3_0")]


def load(name: str) -> tuple[dict, dict]:
    data = json.loads((FROZEN / f"{name}.json").read_text())
    return data["spec"], data.get("extra", {})


def booking() -> dict:
    return load("booking")[0]


def start() -> dict:
    return load("start")[0]


def end(admin) -> dict:
    """The wrap-up, its two pictures (Clappia's CarCID payment QR, the Google review QR) uploaded
    once and found by name after; the Admin can replace them in the form builder."""
    from apps.forms import assets
    from apps.forms.models import FormAsset

    text = json.dumps(load("end")[0])
    for marker, label, file in (("@pay_qr", "Payment QR", "pay-qr.jpg"),
                                ("@review_qr", "Google review QR", "review-qr.png")):
        pic = FormAsset.objects.filter(name=label).first() or assets.create_asset(
            admin, (Path(__file__).parent / "data" / file).read_bytes(), label)
        text = text.replace(json.dumps(marker), json.dumps(str(pic.id)))
    return json.loads(text)


def inspection(form_key: str) -> tuple[dict, dict]:
    return load(form_key)


def library() -> dict:
    """The library sections and fields the inspection forms are built on (setup/common.py)."""
    data = json.loads((FROZEN / "library.json").read_text())
    return {"sections": data["sections"], "fields": data["fields"]}
