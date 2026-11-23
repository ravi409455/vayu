# PDI field map (Phase 0)

Sources: the sample report `AV66022PDI.pdf` (34 pages) and Clappia "New Car 3.0" (garuda), read
only, 28 sections, about 400 fields once Clappia's score helper fields are left out. Target: our
PDI inspection form (now a small stand-in in `backend/apps/core/demo_forms.py`).

Status: **proposal for approval.** Severities and option sets are my call; check them.

## Principles

1. **One home per fact.** Clappia mixes booking, check-in, payment and inspection in one app. Ours
   splits them: booking form (customer, car, slot), start form (check-in), inspection form (the
   checks), end form (payment, review, perfume). Only the inspection form is rebuilt here.
2. **Standard option sets.** Clappia has 80 slightly different option lists for the same idea
   ("Damaged/Scratches/Ok", "Not Ok/Damaged/Scratches/Ok"...). We use 14 named sets; a field may
   use a subset. Each option carries `is_defect`, severity and a print tone.
3. **Photo per check, required when bad.** Every check keeps its photo field (as in Clappia); the
   photo becomes required when the answer is a defect. Body-frame checks also get a remark.
4. **Scores are computed.** Clappia's ~150 "Score n" helper fields and the hand-typed category
   ratings on "Report First Page" go away; our scoring engine computes category ratings and the
   overall verdict, and Ops can override them.
5. **Key Checks are derived** from the answers (rules), not typed again.
6. **Conditional sections.** CNG shows only for CNG cars; 7-seater rows only for 7 seaters.
   That removes the empty CNG section and the "Not Applicable" noise from the report.
7. **Keys** are new, readable snake_case (`door_driver_front`), not Clappia's truncated keys
   (`driver_fro`). A Clappia key → our key table lives in the seed for any later data import.

## Option sets

Tone: `ok` green, `warn` amber, `bad` red, `muted` grey. Severity only on defects.

| Set | Options (tone / defect severity) |
|---|---|
| PANEL | Ok (ok) · Minor Scratches (warn, minor) · Major Scratches (bad, major) · Minor Dents (warn, minor) · Major Dents (bad, major) · Repainted (warn, minor) · Rusted (bad, major) · Replaced (bad, major) · Panel Gaps (warn, minor) · Not Opening Comfortably (warn, minor) · Damaged (bad, major) · Bent (bad, major) |
| GLASS | Ok · Scratches (warn, minor) · Loose (warn, minor) · Damaged (bad, major) |
| LAMP | Ok · Scratches (warn, minor) · Yellowish (warn, minor) · Damaged (bad, major) · Not Available (muted) · Not Applicable (muted) |
| TRIM | Ok · Scratches (warn, minor) · Rusted (bad, major) · Damaged (bad, major) · Not Available (muted) · Not Applicable (muted) |
| FRAME | Ok · Scratches (warn, minor) · Repainted (bad, major) · Rusted (bad, major) · Accidental (bad, critical) · Replaced (bad, critical) · Not Applicable (muted) |
| OKNOT | Ok · Not Ok (bad, major) · Not Applicable (muted) · Not Able to Check (warn) |
| PRESENCE | Not Present (ok) · Present (bad, major) · Not Applicable (muted) · Not Able to Check (warn) |
| WORKING | Working (ok) · Not Working (bad, major) · Not Available (muted) · Not Applicable (muted) · Not Able to Check (warn) |
| DOC | Available (ok) · Not Available (warn) · Not Required (muted) |
| MATCH | Matching (ok) · Not Matching But Original (warn) · Not Matching (bad, critical) · Not Able To Locate (warn) |
| FLOOR | Ok · Not Ok (bad, major) · Covered - Not Able To See (muted) · Not Applicable (muted) |
| TREAD | Good (ok) · Average (warn, minor) · Bad (bad, major) · Stepney Not Available (muted) |
| SHAPE | Ok · Damaged (bad, major) · Not Able to Check (warn) |
| UNDER | Ok · Not Ok (bad, major) · Rusted (bad, major) · Accidental (bad, critical) · Not Able to Check (warn) · Not Applicable (muted) |

"Not Able to Check" is never a defect but prints amber, so a buyer sees what was not verified.

## Inspection form: pages and sections

`c(SET)` = single choice from the set + photo (required on defect). `c(SET)+r` adds a remark
shown on defect. Subsets are noted where Clappia offered fewer options.

### Page 1. Vehicle
**Vehicle details**
- `cover_photo` Car photo for the report cover (photo, 1, required)
- `fuel` Fuel (Petrol / Diesel / CNG (bi-fuel) / Electric / Hybrid) — booking has car and variant
- `transmission` Transmission (Manual / Automatic)
- `engine_cc` Engine capacity (number, cc)
- `colour` Colour (short text)
- `odometer` Odometer (number, km) + `odometer_photo` (photo)
- `mfg_month` Manufacturing month (Jan–Dec) + `mfg_year` (number) — prints "August, 2026"
- `chassis_no` Chassis number (short text, 17 chars) + `chassis_plate_photo` (photo)
- `engine_no` Engine number (short text)
- `keys` Number of keys (number)
- `seats` Seating (5 seater / 7 seater) — new; drives the 7-seater rows

**CNG** (shown when fuel = CNG)
- `cng_fitting` CNG fitting (Company Fitted (Sequential) / Outside Fitted (Conventional))
- `cng_hydro_test` CNG hydro test date (date)
- `cng_plate_photo` CNG plate (photo)

### Page 2. Documents
Each DOC: `doc_insurance` Vehicle insurance · `doc_form21` Form 21 · `doc_form22` Form 22 ·
`doc_rc` Registration certificate · `doc_temp_reg` Temporary registration · `doc_road_tax` Road tax
receipt · `doc_puc` PUC certificate · `doc_warranty` Warranty card · `doc_manual` Owner's manual ·
`doc_service_book` Service booklet · `doc_noc` Bank finance NOC · `doc_ext_warranty` Extended
warranty · `doc_accessories` Accessories invoice · `doc_bifuel` Bi-fuel certificate (+ photo when
Available).

### Page 3. Exterior
**Front** — `bonnet` c(PANEL) · `front_bumper` c(PANEL) · `front_grill` c(PANEL) ·
`headlight_driver` c(LAMP) · `headlight_passenger` c(LAMP) · `fog_lights` c(LAMP) ·
`indicator_front_driver` c(LAMP) · `indicator_front_passenger` c(LAMP) · `number_plate_front`
c(TRIM)
**Driver side** — `fender_driver_front` · `door_driver_front` · `door_driver_back` ·
`quarter_panel_driver_back` (PANEL) · `sill_driver` (PANEL) · `cladding_driver_front` ·
`cladding_driver_rear` (TRIM) · `wheel_arch_driver_front` · `wheel_arch_driver_rear` (TRIM) ·
`mud_flap_driver_front` · `mud_flap_driver_back` (TRIM) · `roof_rail_driver` (TRIM) ·
`fuel_flap` (TRIM)
**Rear** — `boot_door` c(PANEL) · `rear_bumper` c(PANEL) · `taillight_driver` ·
`taillight_passenger` · `taillight_connected` · `indicator_back_driver` ·
`indicator_back_passenger` (LAMP) · `number_plate_rear` c(TRIM)
**Passenger side** — mirror of driver side (13 checks)
**Glass and mirrors** — `windshield` · `rear_windshield` · `window_driver_front` ·
`window_driver_back` · `window_passenger_front` · `window_passenger_back` (GLASS) ·
`mirror_glass_driver` · `mirror_glass_passenger` (GLASS) · `mirror_housing_driver` ·
`mirror_housing_passenger` (GLASS + Not Ok) · `glass_serial_match` (MATCH) +
`glass_serial_remark` (short text, shown unless Matching)
**Roof** — `roof_outside` c(PANEL)

### Page 4. Body frame (accident checklist)
All c(FRAME)+r: `radiator_support` · `strut_apron_driver` · `strut_apron_passenger` ·
`front_rail_driver` · `front_rail_passenger` · `bonnet_underbody` · `pillar_a_driver` ·
`pillar_b_driver` · `pillar_c_driver` · `pillar_d_driver` · `pillar_a_passenger` ·
`pillar_b_passenger` · `pillar_c_passenger` · `pillar_d_passenger` · `running_board_driver` ·
`running_board_passenger` · `boot_lock_pillar` · `boot_floor` · `rear_subframe_z_axle`
Plus `vin_plate_match` VIN plate matching the chassis imprint (MATCH)+r.

### Page 5. Engine
**Engine bay** — `car_start` c(OKNOT) + `car_start_video` (video) · `engine_noise` c(PRESENCE) +
video · `engine_vibration` c(PRESENCE) · `engine_oil_quality` (Clean and Complete / Low Level
(minor) / Oil Change Needed (minor) / Tar Found (major)) + photo · `engine_oil_cap` (Clean /
Sludge Present (major)) · `dipstick_smoke` c(PRESENCE) · `engine_oil_leak` c(PRESENCE) ·
`transmission_oil_leak` c(PRESENCE) · `engine_mounting` · `ac_compressor_mounting` · `hoses` ·
`radiator` · `ac_belt` · `engine_belt` (OKNOT) · `radiator_fan` (WORKING) · `coolant_quality` (Ok /
Water Mixed (major) / Oil Present (critical)) · `coolant_level` (OKNOT) · `battery` (Ok / Damaged
/ Acid Leakage / Rusted / Dissolved Battery Tray, all major) · `wiring` (Ok / Original Wiring
Changed (major) / Damaged (major))
**Exhaust** — `exhaust_pipe` (Ok / Black Particles Present (minor)) · `exhaust_sound` c(PRESENCE)
· `smoke_emission` (Ok / Present (major)) + video
**Battery and generator** — `battery_state` (Full / Medium / Low / Empty) · `generator_state`
(High / Good / Faulty) — *question: what are these read from? Not in the sample report.*

### Page 6. OBD
- `obd_fault_codes` Any fault codes present? (No / Yes (major) / Not Checked / Port Not Working)
- `obd_codes` Codes found (short text, shown when Yes) · `obd_photo` Scan screenshot (photo)

### Page 7. Electrical and interior
**Lights** — WORKING: indicators ×4, headlights ×2, high beams ×2, brake lights ×2, tail lights
×2, `number_plate_light_front`, `number_plate_light_rear`, `interior_lights`
**Controls** — `central_lock` (OKNOT) · `ignition` (OKNOT) · `horn` · `steering_controls` ·
`cruise_control` · `entertainment` · `back_camera` · `parking_sensor` · `sunroof` ·
`bonnet_release` · `fuel_cap_release` · `adblue_display` (diesel only) · `window_safety_lock` ·
`child_lock` (WORKING) · `mirror_control_driver` · `mirror_control_passenger` · `glove_box` ·
`wiper` · `rear_view_mirror` · `dashboard` · `mfd` (OKNOT) · `buttons_note` Anything not working
(short text)
**Windows** — WORKING ×4
**Seats and floor** — per seat row (front driver, front passenger, back driver, back passenger):
`*_seat` (OKNOT), `*_belt` (OKNOT), `*_floor` (FLOOR); seat adjustment ×4 (WORKING); 7-seater
row: seat, belt, floor (shown when seats = 7 seater) · `roof_inside` c(OKNOT)

### Page 8. Warning lights
PRESENCE each: `warn_engine` · `warn_battery` · `warn_oil_pressure` · `warn_airbag` · `warn_abs` ·
`warn_power_steering` · `warn_coolant` · `warn_brake` · `warn_other` + `warn_other_note`
(short text, shown when Present)

### Page 9. Air conditioning
`ac_on` (OKNOT) · `ac_cool_temp` (number, °C) · `ac_cool_mode` (OKNOT) · `ac_hot_temp` (number,
°C) · `ac_hot_mode` (OKNOT) · `ac_direction` · `defogger_front` · `defogger_rear` · `ac_vents`
(OKNOT) · `ac_vibration` (PRESENCE). Clappia's "Entire Total" helper is dropped.

### Page 10. Drive and brakes (test drive)
**Brakes and steering** — `brake_pedal` · `steering_smooth` (OKNOT) · `steering_return` ·
`alignment` (OKNOT) · `steering_noise` · `bubbling` · `steering_vibration` (PRESENCE)
**Transmission and clutch** — `gear_shifting` (OKNOT + Not Smooth (minor)) · `shift_4x4` ·
`clutch_pedal` · `clutch_rpm_down` · `clutch_rpm_up` · `clutch_rpm_accel` (OKNOT)
**Axle** — `axle_left` · `axle_right` (OKNOT) · `axle_noise` (PRESENCE)
**Brakes** — pads, discs, calipers × 4 wheels (OKNOT) · `brake_fluid_reservoir` ·
`brake_fluid_cap` · `handbrake` (OKNOT)
**Suspension** — `car_height` · `bounce_test` · `suspension_driver` · `suspension_passenger`
(OKNOT) · `shocker_leak_driver` · `shocker_leak_passenger` (PRESENCE)

### Page 11. Tyres
`tyre_size` (number, inch) · `tyre_type` (With Tube / Tubeless) · `rim_type` (Normal / Alloy)
For each of driver front, driver back, passenger front, passenger back, stepney:
`*_tread` (TREAD) · `*_depth` (number, mm) · `*_dot` Manufacturing week-year (4 digits, e.g.
2826) · `*_shape` (SHAPE) · photo
`tyre_year` Tyre manufacturing year (number; printed in Key Checks) · `camber` (PRESENCE)

### Page 12. Underbody
UNDER each: `chassis_driver` · `chassis_passenger` · `rear_subframe` · `engine_underbody` ·
`under_trays` · `front_protection` · `rear_protection` · `silencer` · `fuel_tank`;
`underbody_leaks` (PRESENCE); photos: `underbody_photo_left`, `_right`, `_front`, `_rear`

### Page 13. Equipment and pictures
**Equipment** — `tool_kit` (Present / Not Present (minor)) + photo
**Car pictures** (photo, 1 each, required): front, corner front driver, driver side, corner back
driver, back, corner back passenger, passenger side, corner front passenger, front interior, rear
interior, 4-way switch (driver door), trunk open

### Page 14. Summary
- `expert_comments` Expert comments (long text) — printed on the Key Checks page
- `issue_photos` Photos of issues (photo, up to 10)
- Extra key checks: `extra_check_1..3` label + value (short text pairs), optional

## Key Checks (derived, printed on page 2)

| Key check | Rule (true = issue) | Prints |
|---|---|---|
| Control panel lights | any `warn_*` = Present | Found / Not Found |
| Any fluid leaks underbody? | `underbody_leaks` = Present | Present / Not Present |
| Rear subframe damage | `rear_subframe` is a defect | Damaged / Ok |
| Seat-belt issues | any `*_belt` = Not Ok | Found / Not Found |
| Abnormal engine noise | `engine_noise` = Present | Present / Not Present |
| Abnormal steering vibrations | `steering_vibration` = Present (Not Able to Check prints as such) | … |
| Scratches and dents | any Exterior answer in {Minor/Major Scratches, Minor/Major Dents, Scratches} | Found / Not Found |
| Repainted panels | any Exterior or Body frame answer = Repainted | Found / Not Found |
| Any fault codes in OBD scan? | `obd_fault_codes` = Yes | Yes / No |
| Tyre manufacturing year | value of `tyre_year` (not derived) | 2026 |

## Ratings (computed, printed on the cover)

| Category | Sections |
|---|---|
| Engine | Engine bay, Exhaust, OBD, Transmission and clutch, Axle |
| A.C. | Air conditioning |
| Electronics | Lights, Controls, Windows, Warning lights |
| Exterior | Front, Driver side, Rear, Passenger side, Glass and mirrors, Roof, Body frame, Underbody |
| Tires | Tyres, Brakes, Suspension, Brakes and steering |
Overall verdict word: Excellent / Good / Average / Bad.

## Not in the inspection form (lives elsewhere)

| Clappia section | Where in Vayu |
|---|---|
| Inspection Details (booking ID, customer, phone, slot, address, car, lead owner, pending amount, OBD scanning yes/no) | Booking form (exists); add `obd_scan_booked` and `pending_amount` if missing |
| Car Details (company, variant, registered state/city) | Booking form (`car_make_model` master list); add `reg_state`, `reg_city` if wanted |
| Expert Details (45-min delay, selfie with number plate, location, time, payment taken on arrival) | Start (check-in) form |
| Payment Details, Google Review, Car Perfume | End form |
| Report First Page scores, all "Score n" fields, slack_thread_details | Dropped (computed or internal) |

## Questions for the product owner

1. Battery state / Generator state: keep in the PDI form? They are not in the sample report.
2. Are the severities above right (e.g. Repainted = minor on a panel, major on the frame)?
3. Clappia keeps three free "KeyCheck 1–3" slots; keep them as optional extra key checks?
4. Should "Not Available" documents (e.g. Form 21) count as issues, or only print amber?
