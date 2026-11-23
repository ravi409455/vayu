"""The full PDI inspection form, as in the Car C.I.D. sample report (AV66022PDI.pdf) and the
Clappia "New Car 3.0" app, mapped in docs/pdi-field-map.md. Local, test and e2e settings only.

Every check is a choice from a named option set; each answer carries its print colour (tone)
and, when it is a problem, a severity. A check gets a photo (shown and required when the answer
is a problem) and, on the body frame, a remark. Key Checks are worked out from the answers."""

from apps.forms import services as form_services
from apps.forms.models import Field, Page, Section, VersionCheck

# ---------------------------------------------------------------- option sets
# (key, label, tone, severity or None)
OK = ("ok", "Ok", "ok", None)
NA = ("not_available", "Not Available", "muted", None)
NAP = ("not_applicable", "Not Applicable", "muted", None)
NCHK = ("not_checked", "Not Able to Check", "warn", None)
SETS: dict[str, list[tuple]] = {
    "PANEL": [
        OK,
        ("minor_scratches", "Minor Scratches", "warn", "minor"),
        ("major_scratches", "Major Scratches", "bad", "major"),
        ("minor_dents", "Minor Dents", "warn", "minor"),
        ("major_dents", "Major Dents", "bad", "major"),
        ("repainted", "Repainted", "warn", "minor"),
        ("rusted", "Rusted", "bad", "major"),
        ("replaced", "Replaced", "bad", "major"),
        ("panel_gaps", "Panel Gaps", "warn", "minor"),
        ("not_opening", "Not Opening Comfortably", "warn", "minor"),
        ("damaged", "Damaged", "bad", "major"),
        ("bent", "Bent", "bad", "major"),
    ],
    "GLASS": [
        OK,
        ("scratches", "Scratches", "warn", "minor"),
        ("loose", "Loose", "warn", "minor"),
        ("not_ok", "Not Ok", "bad", "major"),
        ("damaged", "Damaged", "bad", "major"),
    ],
    "LAMP": [
        OK,
        ("scratches", "Scratches", "warn", "minor"),
        ("yellowish", "Yellowish", "warn", "minor"),
        ("damaged", "Damaged", "bad", "major"),
        NA,
        NAP,
    ],
    "TRIM": [
        OK,
        ("scratches", "Scratches", "warn", "minor"),
        ("rusted", "Rusted", "bad", "major"),
        ("damaged", "Damaged", "bad", "major"),
        NA,
        NAP,
    ],
    "FRAME": [
        OK,
        ("scratches", "Scratches", "warn", "minor"),
        ("repainted", "Repainted", "bad", "major"),
        ("rusted", "Rusted", "bad", "major"),
        ("accidental", "Accidental", "bad", "critical"),
        ("replaced", "Replaced", "bad", "critical"),
        NAP,
    ],
    "OKNOT": [OK, ("not_ok", "Not Ok", "bad", "major"), NAP, NCHK],
    "PRESENCE": [
        ("not_present", "Not Present", "ok", None),
        ("present", "Present", "bad", "major"),
        NAP,
        NCHK,
    ],
    "WORKING": [
        ("working", "Working", "ok", None),
        ("not_working", "Not Working", "bad", "major"),
        NA,
        NAP,
        NCHK,
    ],
    "DOC": [
        ("available", "Available", "ok", None),
        ("not_available", "Not Available", "warn", None),
        ("not_required", "Not Required", "muted", None),
    ],
    "MATCH": [
        ("matching", "Matching", "ok", None),
        ("not_matching_original", "Not Matching But Original", "warn", None),
        ("not_matching", "Not Matching", "bad", "critical"),
        ("not_located", "Not Able To Locate", "warn", None),
    ],
    "FLOOR": [
        OK,
        ("not_ok", "Not Ok", "bad", "major"),
        ("covered", "Covered - Not Able To See", "muted", None),
        NAP,
    ],
    "TREAD": [
        ("good", "Good", "ok", None),
        ("average", "Average", "warn", "minor"),
        ("bad", "Bad", "bad", "major"),
        ("no_stepney", "Stepney Not Available", "muted", None),
    ],
    "SHAPE": [OK, ("damaged", "Damaged", "bad", "major"), NCHK],
    "UNDER": [
        OK,
        ("not_ok", "Not Ok", "bad", "major"),
        ("rusted", "Rusted", "bad", "major"),
        ("accidental", "Accidental", "bad", "critical"),
        NCHK,
        NAP,
    ],
    "FOUND": [("not_found", "Not Found", "ok", None), ("found", "Found", "bad", "major")],
    "OIL": [
        ("clean_complete", "Clean and Complete", "ok", None),
        ("low_level", "Low Level", "warn", "minor"),
        ("change_needed", "Oil Change Needed", "warn", "minor"),
        ("tar_found", "Tar Found", "bad", "major"),
    ],
    "CAP": [("clean", "Clean", "ok", None), ("sludge", "Sludge Present", "bad", "major")],
    "COOLANT": [
        OK,
        ("water_mixed", "Water Mixed (No Color)", "bad", "major"),
        ("oil_present", "Oil Present", "bad", "critical"),
    ],
    "BATTERY": [
        OK,
        ("damaged", "Damaged", "bad", "major"),
        ("acid_leakage", "Acid Leakage", "bad", "major"),
        ("rusted", "Rusted", "bad", "major"),
        ("tray_dissolved", "Dissolved Battery Tray", "bad", "major"),
    ],
    "WIRING": [
        OK,
        ("changed", "Original Wiring Changed", "bad", "major"),
        ("damaged", "Damaged", "bad", "major"),
    ],
    "EXHAUST": [OK, ("black_particles", "Black Particles Present", "warn", "minor")],
    "SMOKE": [OK, ("present", "Present", "bad", "major")],
    "GEAR": [
        OK,
        ("not_smooth", "Not Smooth", "warn", "minor"),
        ("not_ok", "Not Ok", "bad", "major"),
        NCHK,
    ],
    "TOOLKIT": [
        ("present", "Present", "ok", None),
        ("not_present", "Not Present", "warn", "minor"),
    ],
    "OBD": [
        ("no", "No", "ok", None),
        ("yes", "Yes", "bad", "major"),
        ("not_checked", "Not Checked", "warn", None),
        ("port_not_working", "Port Not Working", "warn", None),
    ],
}
PLAIN = {  # choices that are facts, not checks: no colour, no defect
    "FUEL": [
        ("petrol", "Petrol"),
        ("diesel", "Diesel"),
        ("cng", "CNG (bi-fuel)"),
        ("electric", "Electric"),
        ("hybrid", "Hybrid"),
    ],
    "GEARBOX": [("manual", "Manual"), ("automatic", "Automatic")],
    "MONTH": [
        (m.lower(), m)
        for m in (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        )
    ],
    "SEATS": [("five", "5 seater"), ("seven", "7 seater")],
    "CNG_FIT": [
        ("company", "Company Fitted (Sequential)"),
        ("outside", "Outside Fitted (Conventional)"),
    ],
    "TYRE_TYPE": [("tubeless", "Tubeless"), ("tube", "With Tube")],
    "RIM": [("alloy", "Alloy"), ("normal", "Normal")],
    "BATT_STATE": [("full", "Full"), ("medium", "Medium"), ("low", "Low"), ("empty", "Empty")],
    "GEN_STATE": [("high", "High"), ("good", "Good"), ("faulty", "Faulty")],
}


def options(name: str) -> dict:
    if name in PLAIN:
        return {
            "options": [{"key": k, "label": lb} for k, lb in PLAIN[name]],
            "display": "dropdown",
        }
    out = []
    for key, label, tone, severity in SETS[name]:
        o = {"key": key, "label": label, "tone": tone}
        if severity:
            o.update(is_defect=True, severity=severity)
        out.append(o)
    return {"options": out}


def defects(name: str) -> list[str]:
    return [k for k, _, _, sev in SETS[name] if sev]


# ---------------------------------------------------------------- items
# c(key, label, SET)       a check: choice + a photo when the answer is a problem
# c(..., remark=True)      also a remark when the answer is a problem (body frame)
# c(..., photo=False)      no photo
# ("n", key, label, unit)  number · ("t", key, label) short text · ("l", key, label) long text
# ("s", key, label, PLAIN) a plain choice · ("p", key, label, n, required) photos
# ("d", key, label) date · ("show", rule, [items]) items shown only when rule holds


def c(key, label, set_, remark=False, photo=True):
    return ("c", key, label, set_, remark, photo)


def side(who: str, prefix: str) -> list:
    """The 13 checks along one side of the car (driver or passenger)."""
    return [
        c(f"fender_{prefix}_front", f"{who} front fender", "PANEL"),
        c(f"door_{prefix}_front", f"{who} front door", "PANEL"),
        c(f"door_{prefix}_back", f"{who} back door", "PANEL"),
        c(f"quarter_panel_{prefix}_back", f"{who} back quarter panel", "PANEL"),
        c(f"sill_{prefix}", f"{who} door sill", "PANEL"),
        c(f"cladding_{prefix}_front", f"{who} front cladding", "TRIM"),
        c(f"cladding_{prefix}_rear", f"{who} rear cladding", "TRIM"),
        c(f"wheel_arch_{prefix}_front", f"{who} front wheel arch / fender lining", "TRIM"),
        c(f"wheel_arch_{prefix}_rear", f"{who} rear wheel arch / fender lining", "TRIM"),
        c(f"mud_flap_{prefix}_front", f"{who} front mud flap", "TRIM"),
        c(f"mud_flap_{prefix}_back", f"{who} back mud flap", "TRIM"),
        c(f"roof_rail_{prefix}", f"{who} roof rail", "TRIM"),
    ]


CNG = {"==": [{"var": "inspection.fuel"}, "cng"]}
SEVEN = {"==": [{"var": "inspection.seats"}, "seven"]}
DIESEL = {"==": [{"var": "inspection.fuel"}, "diesel"]}
DOCS = [
    ("doc_insurance", "Vehicle insurance"),
    ("doc_form21", "Form 21"),
    ("doc_form22", "Form 22"),
    ("doc_rc", "Registration certificate"),
    ("doc_temp_reg", "Temporary registration"),
    ("doc_road_tax", "Road tax receipt"),
    ("doc_puc", "PUC certificate"),
    ("doc_warranty", "Warranty card"),
    ("doc_manual", "Owner's manual"),
    ("doc_service_book", "Service booklet"),
    ("doc_noc", "Bank finance NOC"),
    ("doc_ext_warranty", "Extended warranty"),
    ("doc_accessories", "Accessories invoice"),
    ("doc_bifuel", "Bi-fuel certificate"),
]
SEAT_ROWS = [
    ("front_driver", "Front driver side"),
    ("front_passenger", "Front passenger side"),
    ("back_driver", "Back driver side"),
    ("back_passenger", "Back passenger side"),
]
WHEELS = [
    ("front_driver", "front driver side"),
    ("front_passenger", "front passenger side"),
    ("back_passenger", "back passenger side"),
    ("back_driver", "back driver side"),
]
TYRES = [
    ("driver_front", "Driver front"),
    ("driver_back", "Driver back"),
    ("passenger_back", "Passenger back"),
    ("passenger_front", "Passenger front"),
    ("stepney", "Stepney"),
]
PICTURES = [
    ("front", "Front view"),
    ("corner_front_driver", "Corner front, driver side"),
    ("driver_side", "Driver side"),
    ("corner_back_driver", "Corner back, driver side"),
    ("back", "Back view"),
    ("corner_back_passenger", "Corner back, passenger side"),
    ("passenger_side", "Passenger side"),
    ("corner_front_passenger", "Corner front, passenger side"),
    ("front_interior", "Front row, interior"),
    ("rear_interior", "Rear row, interior"),
    ("four_way_switch", "4-way switch, driver door"),
    ("trunk_open", "Trunk open"),
]


def pdi_pages() -> list:
    lights = [
        c("indicator_front_driver_working", "Driver front indicator", "WORKING"),
        c("indicator_front_passenger_working", "Passenger front indicator", "WORKING"),
        c("indicator_back_driver_working", "Driver back indicator", "WORKING"),
        c("indicator_back_passenger_working", "Passenger back indicator", "WORKING"),
        c("headlight_driver_working", "Driver headlight", "WORKING"),
        c("high_beam_driver", "Driver headlight high beam", "WORKING"),
        c("headlight_passenger_working", "Passenger headlight", "WORKING"),
        c("high_beam_passenger", "Passenger headlight high beam", "WORKING"),
        c("brake_light_driver", "Brake light driver side", "WORKING"),
        c("brake_light_passenger", "Brake light passenger side", "WORKING"),
        c("tail_light_driver", "Driver tail light", "WORKING"),
        c("tail_light_passenger", "Passenger tail light", "WORKING"),
        c("number_plate_light_front", "Front number plate light", "WORKING"),
        c("number_plate_light_rear", "Rear number plate light", "WORKING"),
        c("interior_lights", "Interior lights", "WORKING"),
    ]
    controls = [
        c("central_lock", "Central locking", "OKNOT"),
        c("ignition", "Ignition switch / push button", "OKNOT"),
        c("horn", "Car horn", "WORKING"),
        c("steering_controls", "Steering mounted controls", "WORKING"),
        c("cruise_control", "Cruise control", "WORKING"),
        c("entertainment", "Entertainment system", "WORKING"),
        c("back_camera", "Back camera", "WORKING"),
        c("parking_sensor", "Reverse parking sensor", "WORKING"),
        c("sunroof", "Sun roof", "WORKING"),
        c("bonnet_release", "Bonnet release operation", "WORKING"),
        c("fuel_cap_release", "Fuel cap release operation", "WORKING"),
        ("show", DIESEL, [c("adblue_display", "Onboard computer AdBlue level", "WORKING")]),
        c("window_safety_lock", "Window safety lock", "WORKING"),
        c("child_lock", "Child safety lock", "WORKING"),
        c("mirror_control_driver", "Driver side mirror controls", "OKNOT"),
        c("mirror_control_passenger", "Passenger side mirror controls", "OKNOT"),
        c("glove_box", "Glove box", "OKNOT"),
        c("wiper", "Wiper", "OKNOT"),
        c("rear_view_mirror", "Rear view mirror", "OKNOT"),
        c("dashboard", "Dashboard condition", "OKNOT"),
        c("steering_wheel", "Steering wheel condition", "OKNOT"),
        c("mfd", "Multi-function display showing fuel and km", "OKNOT"),
        ("t", "buttons_note", "Anything else not working"),
    ]
    seats = []
    for k, who in SEAT_ROWS:
        seats += [
            c(f"seat_{k}", f"{who} seat condition", "OKNOT"),
            c(f"belt_{k}", f"{who} seat belt", "OKNOT"),
            c(f"floor_{k}", f"{who} floor", "FLOOR", photo=False),
        ]
    seats += [
        c("seat_adjust_driver", "Seat adjustment, driver side", "WORKING"),
        c("seat_adjust_passenger", "Seat adjustment, passenger side", "WORKING"),
        c("seat_adjust_back_driver", "Seat adjustment, back driver side", "WORKING"),
        c("seat_adjust_back_passenger", "Seat adjustment, back passenger side", "WORKING"),
        (
            "show",
            SEVEN,
            [
                c("seat_row3", "Rear seat condition, 7 seater", "OKNOT"),
                c("belt_row3", "Rear seat belt, 7 seater", "OKNOT"),
                c("floor_row3", "Rear floor, 7 seater", "FLOOR", photo=False),
            ],
        ),
        c("roof_inside", "Car roof from inside", "OKNOT"),
        ("p", "roof_inside_picture", "Car roof from inside: picture", 1, False),
    ]
    brakes = []
    for k, where in WHEELS:
        brakes += [
            c(f"brake_pads_{k}", f"Brake pads {where}", "OKNOT"),
            c(f"brake_discs_{k}", f"Brake discs {where}", "OKNOT"),
            c(f"brake_calipers_{k}", f"Brake calipers {where}", "OKNOT"),
        ]
    brakes += [
        c("brake_fluid_reservoir", "Brake fluid reservoir", "OKNOT"),
        c("brake_fluid_cap", "Brake fluid cap", "OKNOT"),
        c("handbrake", "Parking hand brake", "OKNOT"),
    ]
    tyres: list[tuple] = [
        ("n", "tyre_size", "Tyre size", "inch"),
        ("s", "tyre_type", "Tyre type", "TYRE_TYPE"),
        ("s", "rim_type", "Rim type", "RIM"),
    ]
    for k, who in TYRES:
        tyres += [
            c(f"tyre_{k}_tread", f"{who} tyre depth check", "TREAD", photo=False),
            ("n", f"tyre_{k}_depth", f"{who} tyre tread depth", "mm"),
            ("dot", f"tyre_{k}_dot", f"{who} tyre manufacturing week and year"),
            c(f"tyre_{k}_shape", f"{who} tyre shape", "SHAPE", photo=False),
            ("p", f"tyre_{k}_photo", f"{who} tyre photo", 2, True),
        ]
    tyres += [
        ("n", "tyre_year", "Tyre manufacturing year", ""),
        c("camber", "Signs of camber issue", "PRESENCE"),
    ]
    frame = [
        c(k, label, "FRAME", remark=True)
        for k, label in (
            ("radiator_support", "Radiator core support"),
            ("strut_apron_driver", "Driver side strut tower apron"),
            ("strut_apron_passenger", "Passenger side strut tower apron"),
            ("front_rail_driver", "Driver side front rail"),
            ("front_rail_passenger", "Passenger side front rail"),
            ("bonnet_underbody", "Front bonnet underbody"),
            ("pillar_a_driver", "Driver side A pillar"),
            ("pillar_b_driver", "Driver side B pillar"),
            ("pillar_c_driver", "Driver side C pillar"),
            ("pillar_d_driver", "Driver side D pillar"),
            ("pillar_a_passenger", "Passenger side A pillar"),
            ("pillar_b_passenger", "Passenger side B pillar"),
            ("pillar_c_passenger", "Passenger side C pillar"),
            ("pillar_d_passenger", "Passenger side D pillar"),
            ("running_board_driver", "Driver side running board"),
            ("running_board_passenger", "Passenger side running board"),
            ("boot_lock_pillar", "Boot lock pillar"),
            ("boot_floor", "Boot floor"),
            ("rear_subframe_z_axle", "Rear sub frame / Z axle"),
        )
    ]
    frame.insert(
        0, c("vin_plate_match", "VIN plate matching the chassis imprint", "MATCH", remark=True)
    )
    return [
        (
            "Vehicle",
            [
                (
                    "Vehicle details",
                    [
                        ("p", "cover_photo", "Car photo for the report cover", 1, True),
                        ("s", "fuel", "Fuel type", "FUEL"),
                        ("s", "transmission", "Transmission", "GEARBOX"),
                        ("n", "engine_cc", "Engine capacity", "cc"),
                        ("t", "colour", "Colour"),
                        ("n", "odometer", "Odometer reading", "km"),
                        ("p", "odometer_photo", "Odometer photo", 1, True),
                        ("s", "mfg_month", "Manufacturing month", "MONTH"),
                        ("n", "mfg_year", "Manufacturing year", ""),
                        ("p", "chassis_plate_photo", "Chassis number plate", 1, True),
                        ("t", "engine_no", "Engine number"),
                        ("n", "keys", "Number of keys", ""),
                        ("s", "seats", "Seating", "SEATS"),
                    ],
                ),
                (
                    "CNG",
                    [
                        (
                            "show",
                            CNG,
                            [
                                ("s", "cng_fitting", "CNG fitting", "CNG_FIT"),
                                ("d", "cng_hydro_test", "CNG hydro test date"),
                                ("p", "cng_plate_photo", "CNG plate photo", 1, False),
                            ],
                        )
                    ],
                ),
            ],
        ),
        (
            "Documents",
            [
                (
                    "Documents",
                    [c(k, label, "DOC", photo=False) for k, label in DOCS]
                    + [("p", "doc_bifuel_photo", "Bi-fuel certificate photo", 1, False)],
                )
            ],
        ),
        (
            "Exterior",
            [
                (
                    "Front",
                    [
                        c("bonnet", "Front bonnet top", "PANEL"),
                        c("front_bumper", "Front bumper", "PANEL"),
                        c("front_grill", "Front grill", "PANEL"),
                        c("headlight_driver", "Driver side headlight", "LAMP"),
                        c("headlight_passenger", "Passenger side headlight", "LAMP"),
                        c("fog_lights", "Fog lights", "LAMP"),
                        c("indicator_front_driver", "Driver side indicator front", "LAMP"),
                        c("indicator_front_passenger", "Passenger side indicator front", "LAMP"),
                        c("number_plate_front", "Front number plate", "TRIM"),
                    ],
                ),
                (
                    "Driver side",
                    side("Driver", "driver") + [c("fuel_flap", "Fuel filler flap", "TRIM")],
                ),
                (
                    "Rear",
                    [
                        c("boot_door", "Boot space door / backdoor", "PANEL"),
                        c("rear_bumper", "Rear bumper", "PANEL"),
                        c("taillight_driver", "Driver side taillight", "LAMP"),
                        c("taillight_passenger", "Passenger side taillight", "LAMP"),
                        c("taillight_connected", "Connected taillight", "LAMP"),
                        c("indicator_back_driver", "Driver side indicator back", "LAMP"),
                        c("indicator_back_passenger", "Passenger side indicator back", "LAMP"),
                        c("number_plate_rear", "Rear number plate", "TRIM"),
                    ],
                ),
                ("Passenger side", side("Passenger", "passenger")),
                (
                    "Glass and mirrors",
                    [
                        c("windshield", "Windshield", "GLASS"),
                        c("rear_windshield", "Rear windshield", "GLASS"),
                        c("window_driver_front", "Driver front door window", "GLASS"),
                        c("window_driver_back", "Driver back door window", "GLASS"),
                        c("window_passenger_front", "Passenger front door window", "GLASS"),
                        c("window_passenger_back", "Passenger back door window", "GLASS"),
                        c("mirror_glass_driver", "Driver side view mirror glass", "GLASS"),
                        c("mirror_glass_passenger", "Passenger side view mirror glass", "GLASS"),
                        c("mirror_housing_driver", "Driver side view mirror housing", "GLASS"),
                        c(
                            "mirror_housing_passenger",
                            "Passenger side view mirror housing",
                            "GLASS",
                        ),
                        c(
                            "glass_serial_match",
                            "Glass serial numbers",
                            "MATCH",
                            remark=True,
                            photo=False,
                        ),
                    ],
                ),
                ("Roof", [c("roof_outside", "Car roof outside", "PANEL")]),
            ],
        ),
        ("Body frame", [("Body frame", frame)]),
        (
            "Engine",
            [
                (
                    "Engine bay",
                    [
                        c("car_start", "Car start", "OKNOT"),
                        ("v", "car_start_video", "Car start video"),
                        c("engine_noise", "Abnormal engine noise", "PRESENCE"),
                        ("v", "engine_noise_video", "Engine noise video"),
                        c("engine_vibration", "Engine vibration", "PRESENCE"),
                        c("engine_oil_quality", "Engine oil quality", "OIL"),
                        ("p", "engine_oil_photo", "Engine oil photo", 1, True),
                        c("engine_oil_cap", "Engine oil cap", "CAP"),
                        c("dipstick_smoke", "Smoke from the dipstick point", "PRESENCE"),
                        c("engine_oil_leak", "Oil leaks near the engine", "PRESENCE"),
                        c("transmission_oil_leak", "Transmission oil leakage", "PRESENCE"),
                        c("engine_mounting", "Engine mounting and components", "OKNOT"),
                        c("ac_compressor_mounting", "AC compressor mounting", "OKNOT"),
                        c("hoses", "Hoses", "OKNOT"),
                        c("radiator", "Radiator condition", "OKNOT"),
                        c("radiator_fan", "Radiator fan", "WORKING"),
                        c("coolant_quality", "Coolant quality", "COOLANT"),
                        c("coolant_level", "Coolant level", "OKNOT"),
                        c("ac_belt", "AC fan belt", "OKNOT"),
                        c("engine_belt", "Engine fan belt", "OKNOT"),
                        c("battery", "Battery", "BATTERY"),
                        c("wiring", "Wiring", "WIRING"),
                    ],
                ),
                (
                    "Exhaust",
                    [
                        c("exhaust_pipe", "Exhaust pipe", "EXHAUST"),
                        c("exhaust_sound", "Abnormal exhaust sound", "PRESENCE"),
                        c("smoke_emission", "Smoke emission", "SMOKE"),
                        ("v", "smoke_emission_video", "Smoke emission video"),
                    ],
                ),
                (
                    "Battery and generator",
                    [
                        ("s", "battery_state", "Battery state", "BATT_STATE"),
                        ("s", "generator_state", "Generator state", "GEN_STATE"),
                    ],
                ),
            ],
        ),
        (
            "OBD",
            [
                (
                    "OBD scan",
                    [
                        c("obd_fault_codes", "Any fault codes present?", "OBD", photo=False),
                        (
                            "show",
                            {"==": [{"var": "inspection.obd_fault_codes"}, "yes"]},
                            [("t", "obd_codes", "Codes found")],
                        ),
                        ("p", "obd_photo", "OBD scan screenshot", 1, False),
                    ],
                )
            ],
        ),
        (
            "Electrical and interior",
            [
                ("Lights", lights),
                ("Controls", controls),
                (
                    "Windows",
                    [
                        c(f"window_{k}_working", f"Window {w}", "WORKING")
                        for k, w in (
                            ("driver", "driver side"),
                            ("passenger", "passenger side"),
                            ("back_driver", "driver rear side"),
                            ("back_passenger", "passenger rear side"),
                        )
                    ],
                ),
                ("Seats and floor", seats),
            ],
        ),
        (
            "Warning lights",
            [
                (
                    "Warning lights",
                    [
                        c(k, label, "PRESENCE")
                        for k, label in (
                            ("warn_engine", "Check engine light"),
                            ("warn_battery", "Battery warning light"),
                            ("warn_oil_pressure", "Engine oil pressure low warning light"),
                            ("warn_airbag", "Airbag sensor warning light"),
                            ("warn_abs", "ABS sensor warning light"),
                            ("warn_power_steering", "Power steering warning light"),
                            ("warn_coolant", "Low coolant / overheating warning light"),
                            ("warn_brake", "Brake system warning light"),
                            ("warn_other", "Any other control light found?"),
                        )
                    ]
                    + [
                        (
                            "show",
                            {"==": [{"var": "inspection.warn_other"}, "present"]},
                            [("t", "warn_other_note", "Which light")],
                        )
                    ],
                )
            ],
        ),
        (
            "Air conditioning",
            [
                (
                    "Air conditioning",
                    [
                        c("ac_on", "Air conditioning on", "OKNOT"),
                        ("n", "ac_cool_temp", "Cool mode temperature", "°C"),
                        c("ac_cool_mode", "Air conditioning cool mode", "OKNOT"),
                        ("n", "ac_hot_temp", "Hot mode temperature", "°C"),
                        c("ac_hot_mode", "Air conditioning hot mode", "OKNOT"),
                        c("ac_direction", "Air conditioning direction mode", "OKNOT"),
                        c("defogger_front", "Defogger front vent", "OKNOT"),
                        c("defogger_rear", "Defogger rear vent", "OKNOT"),
                        c("ac_vents", "Air conditioning all vents", "OKNOT"),
                        c("ac_vibration", "AC abnormal vibration", "PRESENCE"),
                    ],
                )
            ],
        ),
        (
            "Drive and brakes",
            [
                (
                    "Brakes and steering",
                    [
                        c("brake_pedal", "Brake pedal", "OKNOT"),
                        c("steering_smooth", "Steering rotating smoothly", "OKNOT"),
                        c("steering_return", "Steering coming back while driving", "OKNOT"),
                        c("steering_noise", "Steering weird noise", "PRESENCE"),
                        c("alignment", "Alignment", "OKNOT"),
                        c("bubbling", "Bubbling", "PRESENCE"),
                        c("steering_vibration", "Abnormal steering vibrations", "PRESENCE"),
                    ],
                ),
                (
                    "Transmission and clutch",
                    [
                        c("gear_shifting", "Gear box / transmission shifting", "GEAR"),
                        c("shift_4x4", "4x4 shifting", "OKNOT"),
                        c("clutch_pedal", "Clutch pedal", "OKNOT"),
                        c("clutch_rpm_down", "Clutch engagement: RPM downgrade", "OKNOT"),
                        c("clutch_rpm_up", "Clutch engagement: RPM upgrade", "OKNOT"),
                        c("clutch_rpm_accel", "Clutch engagement: RPM with acceleration", "OKNOT"),
                    ],
                ),
                (
                    "Axle",
                    [
                        c("axle_left", "Left axle", "OKNOT"),
                        c("axle_right", "Right axle", "OKNOT"),
                        c("axle_noise", "Abnormal axle noise", "PRESENCE"),
                    ],
                ),
                ("Brakes", brakes),
                (
                    "Suspension",
                    [
                        c("car_height", "Car height", "OKNOT"),
                        c("bounce_test", "Shocks and struts / bounce test", "OKNOT"),
                        c("suspension_driver", "Driver side suspension assembly", "OKNOT"),
                        c("suspension_passenger", "Passenger side suspension assembly", "OKNOT"),
                        c("shocker_leak_driver", "Driver side shocker leakage", "PRESENCE"),
                        c("shocker_leak_passenger", "Passenger side shocker leakage", "PRESENCE"),
                    ],
                ),
            ],
        ),
        ("Tyres", [("Tyres", tyres)]),
        (
            "Underbody",
            [
                (
                    "Underbody",
                    [
                        c(k, label, "UNDER")
                        for k, label in (
                            ("chassis_driver", "Driver side body chassis"),
                            ("chassis_passenger", "Passenger side body chassis"),
                            ("rear_subframe", "Rear subframe"),
                            ("engine_underbody", "Engine damage underbody"),
                            ("under_trays", "Under trays"),
                            ("front_protection", "Front protection cover"),
                            ("rear_protection", "Rear protection cover"),
                            ("silencer", "Silencer"),
                            ("fuel_tank", "Fuel tank"),
                        )
                    ]
                    + [c("underbody_leaks", "Any fluid leaks under the body", "PRESENCE")]
                    + [
                        ("p", f"underbody_photo_{k}", f"Underbody {k}", 1, True)
                        for k in ("left", "right", "front", "rear")
                    ],
                )
            ],
        ),
        (
            "Equipment and pictures",
            [
                (
                    "Equipment",
                    [
                        c("tool_kit", "Tool kit", "TOOLKIT", photo=False),
                        ("p", "tool_kit_photo", "Tool kit photo", 1, False),
                    ],
                ),
                ("Car pictures", [("p", f"picture_{k}", label, 1, True) for k, label in PICTURES]),
            ],
        ),
        (
            "Summary",
            [
                (
                    "Summary",
                    [
                        ("l", "expert_comments", "Expert comments"),
                        ("pi", "issue_photos", "Photos of issues", 10),
                        *[
                            x
                            for n in (1, 2, 3)
                            for x in (
                                ("t", f"extra_check_{n}", f"Extra key check {n}"),
                                ("t", f"extra_check_{n}_value", f"Extra key check {n}: answer"),
                            )
                        ],
                    ],
                )
            ],
        ),
    ]


# ---------------------------------------------------------------- building


def _make(v, sec, item, show=None, made=None) -> None:
    made = made if made is not None else []

    def add(key, label, type_, config=None, **kw):
        if show is not None:
            kw.setdefault("show_if", show)
        Field.objects.create(
            version=v,
            section=sec,
            key=key,
            label=label,
            type=type_,
            order=sec.fields.count(),
            config=config or {},
            **kw,
        )
        made.append(key)

    kind = item[0]
    if kind == "show":
        for sub in item[2]:
            _make(v, sec, sub, item[1], made)
    elif kind == "c":
        _, key, label, set_, remark, photo = item
        add(key, label, "single_choice", options(set_), required=True)
        bad = {"in": [{"var": f"inspection.{key}"}, defects(set_)]}
        if photo and defects(set_):
            add(
                f"{key}_photo",
                f"{label} photo",
                "photo",
                {"max_count": 3, "photo_of": key},
                show_if=bad,
                required_if=bad,
            )
        if remark:
            add(
                f"{key}_remark",
                f"{label} remark",
                "short_text",
                {"max_length": 300},
                # a remark for anything worth explaining: problems and amber answers
                show_if={"in": [{"var": f"inspection.{key}"},
                                [k for k, _, tone, _ in SETS[set_] if tone in ("warn", "bad")]]},
            )
    elif kind == "n":
        cfg = {"unit": item[3]} if item[3] else {}
        add(
            item[1],
            item[2],
            "number",
            {**cfg, "decimals": 1} if item[3] == "mm" else cfg,
            required=show is None,
        )
    elif kind == "dot":
        add(
            item[1],
            item[2],
            "short_text",
            {
                "max_length": 4,
                "pattern": r"^\d{4}$",
                "pattern_message": "Four digits: week and year, e.g. 2826",
            },
            helper_text="The DOT code on the tyre wall: week then year, e.g. 2826",
            required=True,
        )
    elif kind == "t":
        add(item[1], item[2], "short_text")
    elif kind == "l":
        add(item[1], item[2], "long_text")
    elif kind == "d":
        add(item[1], item[2], "date", required=show is not None)
    elif kind == "s":
        add(
            item[1],
            item[2],
            "single_choice",
            options(item[3]),
            required=item[1] not in ("battery_state", "generator_state"),
        )
    elif kind == "p":
        add(item[1], item[2], "photo", {"max_count": item[3]}, required=item[4])
    elif kind == "pi":
        add(item[1], item[2], "photo", {"max_count": item[3], "issue_photo": True})
    elif kind == "v":
        add(item[1], item[2], "video", {"max_count": 1})


def _any(keys: list[str], values: list[str]) -> dict:
    return {"or": [{"in": [{"var": f"inspection.{k}"}, values]} for k in keys]}


def key_checks(made: dict[str, list[str]]) -> list[tuple]:
    """(key, label, rule, true label, false label): issue when the rule holds."""
    exterior = [
        k
        for s in ("Front", "Driver side", "Rear", "Passenger side", "Glass and mirrors", "Roof")
        for k in made[s]
        if not k.endswith("_photo")
    ]
    painted = exterior + [k for k in made["Body frame"] if not k.endswith(("_photo", "_remark"))]
    warn = [k for k in made["Warning lights"] if k.startswith("warn_") and k != "warn_other_note"]
    belts = [k for k in made["Seats and floor"] if k.startswith("belt_")]
    return [
        (
            "kc_control_lights",
            "Control panel lights",
            _any(warn, ["present"]),
            "Found",
            "Not Found",
        ),
        (
            "kc_fluid_leaks",
            "Any fluid leaks underbody?",
            _any(["underbody_leaks"], ["present"]),
            "Present",
            "Not Present",
        ),
        (
            "kc_rear_subframe",
            "Rear subframe damage",
            _any(["rear_subframe"], defects("UNDER")),
            "Damaged",
            "Ok",
        ),
        ("kc_seat_belts", "Seat-belt issues", _any(belts, ["not_ok"]), "Found", "Not Found"),
        (
            "kc_engine_noise",
            "Abnormal engine noise",
            _any(["engine_noise"], ["present"]),
            "Present",
            "Not Present",
        ),
        (
            "kc_steering_vibration",
            "Abnormal steering vibrations",
            _any(["steering_vibration"], ["present"]),
            "Present",
            "Not Present",
        ),
        (
            "kc_scratches_dents",
            "Scratches and dents",
            _any(
                exterior,
                ["minor_scratches", "major_scratches", "minor_dents", "major_dents", "scratches"],
            ),
            "Found",
            "Not Found",
        ),
        ("kc_repainted", "Repainted panels", _any(painted, ["repainted"]), "Found", "Not Found"),
        (
            "kc_obd",
            "Any fault codes found in OBD scan?",
            _any(["obd_fault_codes"], ["yes"]),
            "Yes",
            "No",
        ),
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


def build_pdi(admin):
    """Create and publish the PDI form; returns (form, {section title: [field keys]})."""
    form = form_services.create_form(admin, key="pdi", name="PDI", inspection_type="pdi")
    v = form.versions.get(status="draft")
    first = Page.objects.get(version=v)
    chassis = Field.objects.get(version=v, key="chassis_no")
    made: dict[str, list[str]] = {}
    for n, (title, sections) in enumerate(pdi_pages()):
        page = first if n == 0 else Page.objects.create(version=v, title=title, order=n)
        page.title, page.gate = title, n == 0
        page.save()
        for m, (stitle, items) in enumerate(sections):
            if n == 0 and m == 0:
                sec = Section.objects.get(page=page)
                sec.title = stitle
                sec.save()
            else:
                sec = Section.objects.create(
                    version=v,
                    page=page,
                    title=stitle,
                    order=m,
                    show_if=CNG if stitle == "CNG" else None,
                )
            keys: list[str] = []
            for item in items:
                _make(v, sec, item, made=keys)
            if stitle == "Vehicle details":  # the chassis number goes first
                keys.insert(0, "chassis_no")
                Field.objects.filter(pk=chassis.pk).update(order=-1)
            made[stitle] = keys
    summary = Section.objects.get(version=v, title="Summary")
    for key, label, rule, yes, no in key_checks(made):
        Field.objects.create(
            version=v,
            section=summary,
            key=key,
            label=label,
            type="derived",
            order=summary.fields.count(),
            config={"rule": rule, "true_label": yes, "false_label": no},
        )
        made["Summary"].append(key)
    for ckey, clabel, _ in CATEGORIES:
        Field.objects.create(
            version=v,
            section=summary,
            key=f"rating_{ckey}",
            label=f"{clabel} rating",
            type="rating",
            order=summary.fields.count(),
            config={"category": ckey},
        )
        made["Summary"].append(f"rating_{ckey}")
    v.rating_config = {
        "categories": [{"key": c, "label": lb, "sections": secs} for c, lb, secs in CATEGORIES]
    }
    v.save()
    VersionCheck.objects.create(
        version=v,
        rule={">": [{"var": "inspection.odometer"}, 0]},
        message="The odometer cannot be zero.",
        fields=["odometer"],
        order=0,
    )
    v.refresh_from_db()
    form_services.publish_version(admin, v.id, v.row_version)
    return form, made


# ---------------------------------------------------------------- answers

SAMPLE = {  # the answers of the sample report AV66022 that are not the first option
    "fuel": "petrol",
    "transmission": "manual",
    "engine_cc": 1199,
    "colour": "Deep Forest",
    "odometer": 39,
    "mfg_month": "august",
    "mfg_year": 2026,
    "engine_no": "NPTZH48143",
    "keys": 2,
    "seats": "five",
    "battery_state": "full",
    "generator_state": "good",
    "doc_insurance": "not_available",
    "doc_form21": "not_available",
    "doc_form22": "not_available",
    "doc_rc": "not_available",
    "doc_temp_reg": "not_available",
    "doc_road_tax": "not_available",
    "doc_warranty": "not_available",
    "doc_manual": "available",
    "doc_noc": "not_required",
    "doc_ext_warranty": "not_available",
    "doc_accessories": "not_available",
    "doc_bifuel": "not_required",
    "fog_lights": "not_available",
    "number_plate_front": "not_available",
    "number_plate_rear": "not_available",
    "mud_flap_driver_front": "not_available",
    "mud_flap_driver_back": "not_available",
    "mud_flap_passenger_front": "not_available",
    "mud_flap_passenger_back": "not_available",
    "pillar_d_driver": "not_applicable",
    "pillar_d_passenger": "not_applicable",
    "window_driver_front": "loose",
    "number_plate_light_front": "not_available",
    "cruise_control": "not_checked",
    "adblue_display": "not_applicable",
    "seat_adjust_back_driver": "not_applicable",
    "seat_adjust_back_passenger": "not_applicable",
    "steering_return": "not_checked",
    "alignment": "not_checked",
    "bubbling": "not_checked",
    "steering_vibration": "not_checked",
    "shift_4x4": "not_applicable",
    "rear_protection": "not_applicable",
    "ac_cool_temp": 8,
    "ac_hot_temp": 48,
    "tyre_size": 16,
    "tyre_year": 2026,
    "tyre_driver_front_depth": 7.5,
    "tyre_driver_back_depth": 7.4,
    "tyre_passenger_back_depth": 7.6,
    "tyre_passenger_front_depth": 7.5,
    "tyre_stepney_depth": 7.9,
    "tyre_driver_front_dot": "2826",
    "tyre_driver_back_dot": "2826",
    "tyre_passenger_back_dot": "3126",
    "tyre_passenger_front_dot": "3126",
    "tyre_stepney_dot": "2926",
    "expert_comments": "The left front door glass outer weatherstrip is loose. The vehicle is "
    "not clean and requires washing.",
    **{f"floor_{k}": "covered" for k, _ in SEAT_ROWS},
}


def sample_answers(version, chassis: str, **overrides) -> tuple[dict, list[str]]:
    """Answers for every visible field like the sample report (first option unless SAMPLE or
    `overrides` say otherwise), and the keys of the photo fields that still need a picture."""
    from apps.forms.rules import truthy

    answers: dict = {"chassis_no": chassis}
    photos: list[str] = []
    values = {**SAMPLE, **overrides}
    fields = list(
        Field.objects.filter(version=version)
        .select_related("section")
        .order_by("section__page__order", "section__order", "order")
    )
    for f in fields:
        data = {"inspection": answers}
        if not truthy(f.show_if, data) or not truthy(f.section.show_if, data):
            continue
        if f.key in values:
            answers[f.key] = values[f.key]
        elif f.type == "single_choice" and (f.required or truthy(f.required_if, data)):
            answers[f.key] = f.config["options"][0]["key"]
        elif f.type == "photo" and (f.required or truthy(f.required_if, data)):
            photos.append(f.key)
        elif f.type == "short_text" and f.key.endswith("_remark"):
            answers[f.key] = "Outer weatherstrip is loose" if "window" in f.key else "Checked"
    return answers, photos


def _sec(key: str, title: str = "", **kw) -> dict:
    return {
        "type": "table",
        "title": title,
        "source": {"kind": "section", "section": f"inspection.{key}"},
        **kw,
    }


def _issue_photos(key: str, title: str = "Photos of issues") -> dict:
    return {
        "type": "photos",
        "title": title,
        "per_row": 3,
        "caption": "check",
        "source": {"kind": "section", "section": f"inspection.{key}"},
        "which": "issues",
    }


def _heading(text: str, sub: str = "") -> dict:
    small = f' <span class="tone-muted small">{sub}</span>' if sub else ""
    return {"type": "text", "html": f"<h2>{text}{small}</h2>", "box": {"space_below": 1}}


def _page(title: str, parts: list, style: str = "normal") -> dict:
    return {"title": title, "style": style, "parts": parts}


def pdf_definition(logo: str | None, watermark: str | None, disclaimer: str) -> dict:
    """The PDI report of the sample (AV66022PDI.pdf) in the new template format."""
    brand = [{"image": logo, "height": 11}] if logo else []
    tyre_grid = {
        "type": "table",
        "title": "",
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
        "title": "Overall rating",
        "look": {"header": True, "lines": "all"},
        "source": {
            "kind": "grid",
            "columns": [{"label": lb} for _, lb, _ in CATEGORIES] + [{"label": "Expert rating"}],
            "rows": [
                {
                    "label": "Rating",
                    "cells": [{"field": f"inspection.rating_{k}"} for k, _, _ in CATEGORIES]
                    + [{"text": "{{ sys.overall }}"}],
                }
            ],
        },
    }
    vehicle = {
        "type": "table",
        "title": "",
        "per_row": 2,
        "source": {
            "kind": "fields",
            "rows": [
                {"field": "booking.booking_id", "label": "Booking ID"},
                {"field": "booking.car_make_model", "label": "Car"},
                {"field": "inspection.engine_cc", "label": "Engine capacity"},
                {"field": "inspection.fuel"},
                {"field": "inspection.transmission"},
                {"field": "inspection.chassis_no"},
                {"field": "inspection.engine_no"},
                {"field": "inspection.colour"},
                {"field": "inspection.odometer"},
                {"field": "inspection.mfg_month", "label": "Manufactured (month)"},
                {"field": "inspection.mfg_year", "label": "Manufactured (year)"},
                {"field": "inspection.keys"},
            ],
        },
    }
    key_checks = {
        "type": "table",
        "title": "Key checks",
        "source": {
            "kind": "fields",
            "rows": [
                *[{"field": f"inspection.{k}"} for k, *_ in key_checks_list()],
                {"field": "inspection.tyre_year"},
            ],
        },
    }
    pages = [
        _page(
            "Cover",
            [
                {
                    "type": "photos",
                    "per_row": 1,
                    "shape": "16:9",
                    "caption": "none",
                    "source": {"kind": "fields", "fields": ["inspection.cover_photo"]},
                },
                vehicle,
                ratings,
                {
                    "type": "text",
                    "html": "<p><strong>{{ sys.issues }}</strong> issue(s) found. See the "
                    "summary on the next page.</p>",
                },
                {**_sec("documents", "Documents", per_row=2)},
                {
                    "type": "text",
                    "size": "small",
                    "html": "<p>*Please refer to the last pages for terms, conditions and "
                    "disclaimer.</p>",
                },
            ],
            style="cover",
        ),
        _page(
            "Summary",
            [
                {"type": "table", "title": "Issues found", "source": {"kind": "defects"}},
                {
                    "type": "photos",
                    "title": "Photos of issues",
                    "per_row": 3,
                    "caption": "check",
                    "source": {"kind": "issues"},
                },
                key_checks,
                {
                    "type": "text",
                    "html": "<h3>Expert comments</h3><p>{{ inspection.expert_comments }}</p>",
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
                {"type": "spacer", "height": 90},
                {
                    "type": "text",
                    "size": "title",
                    "align": "center",
                    "html": "<p>Detailed Report</p>",
                },
                {
                    "type": "text",
                    "align": "center",
                    "html": "<p>{{ sys.booking_id }} · {{ sys.car }}</p>",
                },
            ],
            style="full",
        ),
        _page(
            "Exterior",
            [
                _heading("Exterior"),
                _sec("front", "Front"),
                _sec("driver_side", "Driver side"),
                _sec("rear", "Rear"),
                _sec("passenger_side", "Passenger side"),
                _sec("glass_and_mirrors", "Glass and mirrors", per_row=2),
                _sec("roof", "Roof"),
                *[
                    _issue_photos(k, "")
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
            "Tyres",
            [
                _heading("Tyres"),
                {
                    "type": "table",
                    "title": "",
                    "per_row": 2,
                    "source": {
                        "kind": "fields",
                        "rows": [
                            {"field": "inspection.tyre_size"},
                            {"field": "inspection.tyre_type"},
                            {"field": "inspection.rim_type"},
                            {"field": "inspection.camber"},
                        ],
                    },
                },
                tyre_grid,
                {
                    "type": "photos",
                    "title": "Tyre photos",
                    "per_row": 3,
                    "source": {
                        "kind": "fields",
                        "fields": [f"inspection.tyre_{k}_photo" for k, _ in TYRES],
                    },
                },
                _heading("OBD (engine scan)"),
                _sec("obd_scan"),
                {
                    "type": "photos",
                    "per_row": 2,
                    "caption": "label",
                    "source": {"kind": "fields", "fields": ["inspection.obd_photo"]},
                },
            ],
        ),
        _page(
            "Electrical and interior",
            [
                _heading("Electrical and interior components"),
                _sec("lights", "Lights"),
                _sec("controls", "Controls"),
                _sec("windows", "Windows", per_row=2),
                _sec("seats_and_floor", "Seats and floor"),
                *[
                    _issue_photos(k, "")
                    for k in ("lights", "controls", "windows", "seats_and_floor")
                ],
            ],
        ),
        _page(
            "Warning lights and AC",
            [
                _heading("Warning lights"),
                _sec("warning_lights"),
                _issue_photos("warning_lights"),
                _heading("Air conditioning"),
                _sec("air_conditioning"),
                _issue_photos("air_conditioning"),
            ],
        ),
        _page(
            "Drive and brakes",
            [
                _heading("Brakes and steering"),
                _sec("brakes_and_steering"),
                _heading("Transmission and clutch pedal"),
                _sec("transmission_and_clutch"),
                _heading("Axle"),
                _sec("axle"),
                _heading("Brakes"),
                _sec("brakes", per_row=2),
                _heading("Suspension"),
                _sec("suspension"),
                *[
                    _issue_photos(k, "")
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
                    "title": "Engine photos",
                    "per_row": 3,
                    "caption": "check",
                    "source": {"kind": "section", "section": "inspection.engine_bay"},
                },
                _issue_photos("exhaust", ""),
            ],
        ),
        _page(
            "Underbody",
            [
                _heading("Underbody"),
                _sec("underbody"),
                {
                    "type": "photos",
                    "per_row": 2,
                    "source": {"kind": "section", "section": "inspection.underbody"},
                },
                _heading("Equipment"),
                _sec("equipment"),
                {
                    "type": "photos",
                    "per_row": 3,
                    "source": {"kind": "fields", "fields": ["inspection.tool_kit_photo"]},
                },
                {**_sec("cng", "CNG"), "show_if": CNG},
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
            "Verify",
            [
                {"type": "spacer", "height": 20},
                {
                    "type": "text",
                    "align": "center",
                    "html": "<h2>Verify this report</h2><p>Scan the "
                    "code or open the link to see this report as Car C.I.D. issued it. If anything "
                    "differs, the copy you hold has been changed.</p>",
                },
                {"type": "verify", "size": 60},
                {
                    "type": "text",
                    "align": "center",
                    "html": "<p>Booking {{ sys.booking_id }} · "
                    "revision {{ sys.revision }} · generated {{ sys.generated_at }}</p>",
                },
            ],
        ),
        _page("Disclaimer", [{"type": "text", "columns": 2, "size": "small", "html": disclaimer}]),
    ]
    header = {
        "left": brand + [{"text": "<strong>CAR C.I.D.</strong>"}],
        "right": [
            {"text": "<strong>PDI REPORT</strong>"},
            {"text": "{{ sys.booking_id }} · {{ sys.car }}"},
        ],
        "background": "brand",
        "height": 16,
    }
    return {
        "schema": 2,
        "filename": "{{ sys.booking_id }}PDI.pdf",
        "theme": {"colors": {"brand": "#a62830"}},
        "bands": {
            "cover": {
                "header": {
                    **header,
                    "height": 26,
                    "left": ([{"image": logo, "height": 18}] if logo else [])
                    + [{"text": "<strong>CAR C.I.D.</strong>"}],
                    "right": [
                        {"text": "<strong>PRE DELIVERY INSPECTION REPORT</strong>"},
                        {"text": "Booking {{ sys.booking_id }}"},
                    ],
                },
                "footer": {
                    "left": [{"text": "Verify this report and read the terms on the last pages"}],
                    "right": [{"text": "Page {{ sys.page }} of {{ sys.pages }}"}],
                    "height": 8,
                },
            },
            "normal": {
                "header": header,
                "footer": {
                    "left": [{"text": "Inspected {{ sys.inspected_on }}"}],
                    "right": [{"text": "Page {{ sys.page }} of {{ sys.pages }}"}],
                    "height": 8,
                },
            },
        },
        **({"watermark": {"image": watermark, "opacity": 0.35, "width": 62}} if watermark else {}),
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
