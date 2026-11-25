"""The PDI report layout (the Car C.I.D. sample report, AV66022PDI.pdf): pages, tables and photo
grids over the PDI form's sections. Production setup builds every inspection's report from it
(apps/core/setup/reports.py); the demo seed uses it too. Moved out of the demo module (F-004) so
production code never imports demo code."""

CNG = {"==": [{"var": "inspection.fuel"}, "cng"]}
TYRES = [
    ("driver_front", "Driver front"),
    ("driver_back", "Driver back"),
    ("passenger_back", "Passenger back"),
    ("passenger_front", "Passenger front"),
    ("stepney", "Stepney"),
]
CATEGORIES = [
    ("engine", "Engine", ["Engine bay", "Exhaust", "OBD scan", "Transmission and clutch", "Axle"]),
    ("ac", "A.C.", ["Air conditioning"]),
    ("electronics", "Electronics", ["Lights", "Controls", "Windows", "Warning lights"]),
    (
        "exterior",
        "Exterior",
        [
            "Front",
            "Driver side",
            "Rear",
            "Passenger side",
            "Glass and mirrors",
            "Roof",
            "Body frame",
            "Underbody",
        ],
    ),
    ("tyres", "Tyres", ["Tyres", "Brakes", "Suspension", "Brakes and steering"]),
]


def _sec(key: str, title: str = "", header: bool = True, **kw) -> dict:
    """A table of every check in one form section."""
    return {
        "type": "table",
        "title": title,
        "look": {"header": header},
        "source": {"kind": "section", "section": f"inspection.{key}"},
        "style_rules": [{"when": "not_checked", "value": "muted"}],
        **kw,
    }


def _issue_photos(key: str, title: str = "") -> dict:
    return {
        "type": "photos",
        "title": title,
        "per_row": 3,
        "caption": "check",
        "source": {"kind": "section", "section": f"inspection.{key}"},
        "which": "issues",
    }


def _heading(text: str, sub: str = "") -> dict:
    small = f' <span class="small">{sub}</span>' if sub else ""
    return {"type": "text", "html": f"<h2>{text}{small}</h2>", "box": {"space_below": 0.5}}


def _cols(*columns: list, widths: tuple = ()) -> dict:
    return {
        "type": "columns",
        "gap": 6,
        "columns": [
            {"parts": c, **({"width": widths[k]} if widths else {})} for k, c in enumerate(columns)
        ],
    }


def _page(title: str, parts: list, style: str = "normal") -> dict:
    return {"title": title, "style": style, "parts": parts}


def _centre(*parts: dict, width: int = 64) -> dict:
    side = (100 - width) / 2
    return _cols([], list(parts), [], widths=(side, width, side))


def pdf_definition(logo: str | None, watermark: str | None, disclaimer: str) -> dict:
    """The PDI report of the sample (AV66022PDI.pdf), laid out like the approved prototype."""
    tyre_grid = {
        "type": "table",
        "look": {"header": True},
        "source": {
            "kind": "grid",
            "columns": [
                {"label": "Tread"},
                {"label": "Depth"},
                {"label": "Made (week, year)"},
                {"label": "Shape"},
            ],
            "rows": [
                {
                    "label": who,
                    "cells": [
                        {"field": f"inspection.tyre_{k}_{c}"}
                        for c in ("tread", "depth", "dot", "shape")
                    ],
                }
                for k, who in TYRES
            ],
        },
    }
    ratings = {
        "type": "table",
        "look": {"header": True, "emphasis": True, "stripes": False},
        "source": {
            "kind": "grid",
            "columns": [{"label": lb} for _, lb, _ in CATEGORIES]
            + [{"label": "Expert rating", "width": 22}],
            "rows": [
                {
                    "label": "",
                    "cells": [{"field": f"inspection.rating_{k}"} for k, _, _ in CATEGORIES]
                    + [{"text": "{{ sys.overall }}"}],
                }
            ],
        },
    }
    tiles = {
        "type": "table",
        "look": {"header": True, "emphasis": True, "stripes": False},
        "source": {
            "kind": "grid",
            "columns": [
                {"label": "Issues found"},
                {"label": "Not able to check"},
                {"label": "Checks done"},
            ],
            "rows": [
                {
                    "label": "",
                    "cells": [
                        {"text": "{{ sys.issues }}"},
                        {"text": "{{ sys.not_checked }}"},
                        {"text": "{{ sys.checks }}"},
                    ],
                }
            ],
        },
    }
    vehicle = {
        "type": "table",
        "look": {"kv": True, "stripes": False, "label_width": 42},
        "source": {
            "kind": "fields",
            "rows": [
                {"field": "booking.booking_id", "label": "Booking ID"},
                {"field": "booking.car_make_model", "label": "Car"},
                {"field": "inspection.engine_cc", "label": "Engine capacity"},
                {"field": "inspection.fuel", "label": "Fuel type"},
                {"field": "inspection.transmission"},
                {"field": "inspection.chassis_no", "label": "Chassis no."},
                {"field": "inspection.engine_no", "label": "Engine no."},
                {"field": "inspection.colour"},
                {"field": "inspection.odometer", "label": "Odometer"},
                {"field": "inspection.mfg_month", "label": "Manufactured"},
                {"field": "inspection.mfg_year", "label": "Year"},
                {"field": "inspection.keys", "label": "Keys"},
            ],
        },
    }
    key_checks = {
        "type": "table",
        "source": {
            "kind": "fields",
            "rows": [
                *[{"field": f"check.{k}"} for k, *_ in key_checks_list()],
                {"field": "inspection.tyre_year"},
            ],
        },
    }
    verify_rows = {
        "type": "table",
        "look": {"kv": True, "header": False, "stripes": False},
        "source": {
            "kind": "grid",
            "columns": [{"label": ""}],
            "rows": [
                {"label": label, "cells": [{"text": value}]}
                for label, value in (
                    ("Booking ID", "{{ sys.booking_id }}"),
                    ("Car", "{{ sys.car }}"),
                    ("Report revision", "{{ sys.revision }}"),
                    ("Generated", "{{ sys.generated_at }}"),
                    ("Inspected by", "{{ sys.expert }}"),
                )
            ],
        },
    }
    pages = [
        _page(
            "Cover",
            [
                _cols(
                    [
                        {
                            "type": "photos",
                            "per_row": 1,
                            "shape": "4:3",
                            "caption": "none",
                            "source": {"kind": "fields", "fields": ["inspection.cover_photo"]},
                        }
                    ],
                    [vehicle],
                    widths=(52, 48),
                ),
                _heading("Overall rating"),
                ratings,
                tiles,
                _heading("Documents"),
                _sec("documents", per_row=2, header=False),
            ],
            style="cover",
        ),
        _page(
            "Summary",
            [
                _heading("Issues found", "from all sections"),
                {
                    "type": "table",
                    "source": {"kind": "defects"},
                    # a critical problem stands out: bold on a red tint
                    "style_rules": [{"when": "critical", "bold": True, "background": "bad"}],
                },
                {"type": "photos", "per_row": 3, "caption": "check", "source": {"kind": "issues"}},
                {
                    "type": "text",
                    "html": '<p><strong class="tone-warn">Not able to check:</strong> '
                    "{{ sys.not_checked_list }}</p>",
                },
                _heading("Key checks"),
                key_checks,
                _heading("Expert comments"),
                {
                    "type": "text",
                    "html": "<p>{{ inspection.expert_comments }}</p>",
                    "box": {
                        "padding": 3,
                        "background": "muted",
                        "border": "left",
                        "border_color": "brand",
                        "border_width": 1,
                    },
                },
            ],
        ),
        _page(
            "Detailed report",
            [
                {"type": "spacer", "height": 70},
                {
                    "type": "text",
                    "align": "center",
                    "size": "small",
                    "html": '<p class="tone-brand"><strong>{{ sys.booking_id }} · '
                    "{{ sys.car }}</strong></p>",
                },
                {
                    "type": "text",
                    "size": "title",
                    "align": "center",
                    "html": "<p>Detailed Report</p>",
                },
                {"type": "spacer", "height": 10},
                _centre({"type": "contents", "columns": 2}, width=70),
            ],
            style="full",
        ),
        _page(
            "Exterior",
            [
                _heading("Exterior"),
                _cols([_sec("front", "Front")], [_sec("driver_side", "Driver side")]),
                _cols([_sec("rear", "Rear")], [_sec("passenger_side", "Passenger side")]),
                _sec("glass_and_mirrors", "Glass and mirrors", per_row=2),
                _sec("roof", "Roof"),
                *[
                    _issue_photos(k)
                    for k in (
                        "front",
                        "driver_side",
                        "rear",
                        "passenger_side",
                        "glass_and_mirrors",
                        "roof",
                    )
                ],
            ],
        ),
        _page(
            "Body frame",
            [
                _heading("Body frame accidental checklist"),
                _sec("body_frame"),
                _issue_photos("body_frame"),
            ],
        ),
        _page(
            "Tyres and OBD",
            [
                _heading(
                    "Tyres",
                    "{{ inspection.tyre_size }} · {{ inspection.tyre_type }} · "
                    "{{ inspection.rim_type }} rims",
                ),
                tyre_grid,
                {
                    "type": "table",
                    "source": {"kind": "fields", "rows": [{"field": "inspection.camber"}]},
                },
                {
                    "type": "photos",
                    "per_row": 3,
                    "source": {
                        "kind": "fields",
                        "fields": [f"inspection.tyre_{k}_photo" for k, _ in TYRES],
                    },
                },
                _heading("OBD scan"),
                _cols(
                    [_sec("obd_scan", header=False)],
                    [
                        {
                            "type": "photos",
                            "per_row": 1,
                            "caption": "label",
                            "source": {"kind": "fields", "fields": ["inspection.obd_photo"]},
                        }
                    ],
                    widths=(64, 36),
                ),
            ],
        ),
        _page(
            "Electrical and interior",
            [
                _heading("Electrical and interior"),
                _cols([_sec("lights", "Lights")], [_sec("controls", "Controls")]),
                _sec("windows", "Windows", per_row=2),
                _sec("seats_and_floor", "Seats and floor"),
                *[_issue_photos(k) for k in ("lights", "controls", "windows", "seats_and_floor")],
            ],
        ),
        _page(
            "Warning lights and AC",
            [
                _cols(
                    [
                        _heading("Warning lights"),
                        _sec("warning_lights"),
                        _issue_photos("warning_lights"),
                    ],
                    [
                        _heading("Air conditioning"),
                        _sec("air_conditioning"),
                        _issue_photos("air_conditioning"),
                    ],
                )
            ],
        ),
        _page(
            "Drive and brakes",
            [
                _cols(
                    [_heading("Brakes and steering"), _sec("brakes_and_steering")],
                    [
                        _heading("Transmission and clutch"),
                        _sec("transmission_and_clutch"),
                        _heading("Axle"),
                        _sec("axle"),
                    ],
                ),
                _heading("Brakes"),
                _sec("brakes", per_row=2),
                _heading("Suspension"),
                _sec("suspension"),
                *[
                    _issue_photos(k)
                    for k in (
                        "brakes_and_steering",
                        "transmission_and_clutch",
                        "axle",
                        "brakes",
                        "suspension",
                    )
                ],
            ],
        ),
        _page(
            "Engine",
            [
                _heading("Engine"),
                _sec("engine_bay"),
                _sec("exhaust", "Exhaust"),
                {
                    "type": "photos",
                    "per_row": 3,
                    "caption": "check",
                    "source": {"kind": "section", "section": "inspection.engine_bay"},
                },
                _issue_photos("exhaust"),
            ],
        ),
        _page(
            "Underbody and equipment",
            [
                _heading("Underbody"),
                _sec("underbody"),
                {
                    "type": "photos",
                    "per_row": 4,
                    "source": {"kind": "section", "section": "inspection.underbody"},
                },
                _heading("Equipment"),
                _cols(
                    [_sec("equipment", header=False)],
                    [
                        {
                            "type": "photos",
                            "per_row": 1,
                            "caption": "label",
                            "source": {"kind": "fields", "fields": ["inspection.tool_kit_photo"]},
                        }
                    ],
                    widths=(64, 36),
                ),
                {**_heading("CNG"), "show_if": CNG},
                {**_sec("cng"), "show_if": CNG},
            ],
        ),
        _page(
            "Car pictures",
            [
                _heading("Car pictures"),
                {
                    "type": "photos",
                    "per_row": 2,
                    "source": {"kind": "section", "section": "inspection.car_pictures"},
                },
            ],
        ),
        _page(
            "Verify this report",
            [
                {"type": "spacer", "height": 18},
                {
                    "type": "text",
                    "align": "center",
                    "html": "<h2>Verify this report</h2><p>Scan the "
                    "code or open the link to see this report as Car C.I.D. issued it. If anything "
                    "differs, the copy you hold has been changed.</p>",
                },
                {"type": "verify", "size": 62},
                {"type": "spacer", "height": 6},
                _centre(verify_rows, width=60),
                {"type": "spacer", "height": 8},
                # one under the other, centred: a link with nothing behind it is left out
                {"type": "button", "link": "photos", "label": "Download photos"},
                {"type": "button", "link": "videos", "label": "Download videos"},
            ],
        ),
        _page("Disclaimer", [{"type": "text", "columns": 2, "size": "fine", "html": disclaimer}]),
    ]
    logo_item = [{"image": logo, "height": 12}] if logo else []  # the shield on the red
    header = {
        "left": logo_item + [{"text": "<strong>CAR C.I.D.</strong>"}],
        "right": [
            {"text": "<strong>PDI REPORT</strong>"},
            {"text": "{{ sys.booking_id }} · {{ sys.car }}"},
        ],
        "background": "brand",
        "height": 15,
    }
    cover_header = {
        "left": ([{"image": logo, "height": 19}] if logo else [])
        + [
            {"text": '<span class="large">CAR C.I.D.</span>'},
            {"text": '<span class="small">CAR INSPECTION</span>'},
        ],
        "right": [
            {"text": "<strong>PRE DELIVERY</strong>"},
            {"text": "<strong>INSPECTION REPORT</strong>"},
            {"text": "Booking {{ sys.booking_id }}"},
        ],
        "background": "brand",
        "height": 26,
    }
    page_no = {"text": "Page {{ sys.page }} of {{ sys.pages }}"}
    return {
        "schema": 2,
        "filename": "{{ sys.booking_id }}PDI.pdf",
        "theme": {
            "colors": {"brand": "#a62830"},
            "fonts": {"body": "Inter", "headings": "Barlow Semi Condensed"},
            "size": 10.5,  # read mostly on phones: 1 pt above the default
        },
        "bands": {
            "cover": {
                "header": cover_header,
                "footer": {
                    "left": [{"text": "Verify this report and read the terms on the last pages"}],
                    "right": [page_no],
                    "height": 8,
                },
            },
            "normal": {
                "header": header,
                "footer": {
                    "left": [{"text": "Inspected {{ sys.inspected_on }}"}],
                    "right": [page_no],
                    "height": 8,
                },
            },
        },
        **({"watermark": {"image": watermark, "opacity": 0.15, "width": 62}} if watermark else {}),
        "pages": pages,
    }


def key_checks_list() -> list[tuple]:
    """The Key Check fields in report order (their rules need the built form)."""
    return [
        (k,)
        for k in (
            "kc_control_lights",
            "kc_fluid_leaks",
            "kc_rear_subframe",
            "kc_seat_belts",
            "kc_engine_noise",
            "kc_steering_vibration",
            "kc_scratches_dents",
            "kc_repainted",
            "kc_obd",
        )
    ]
