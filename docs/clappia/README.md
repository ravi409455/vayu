# Clappia Garuda apps: read-out and mapping

Read on 2026-11-24 from https://garuda.clappia.com, **read-only** (designer view; every outgoing
write in the browser tab was blocked while reading; nothing was saved). Source for the test-setup
and go-live setup script (see memory `project-vayu-test-setup`).

| App | File | Sections | Fields | Score/helper formulas | Show-rules |
|---|---|---|---|---|---|
| New Car 3.0 (PDI) | `new_car_3_0.json` | 28 | 559 | 100 | 115 |
| Used Car 3.0 (PPI) | `used_car_3_0.json` | 29 | 529 | 111 | 41 |
| EV 3.0 | `ev_3_0.json` | 25 | 505 | 83 | 111 |
| BookingCreation 3.0 | `booking_creation_3_0.json` | 1 | 20 | 2 | 4 |

Each JSON: `sections[] → {title, sdesc, settings, fields[]}`; a field has `kind` (Clappia widget:
`app-radio` single choice, `app-check-box` multi choice, `app-file` photos/videos,
`ng:input:text` text/number, `app-formula`, `app-select` dropdown, `app-toggle`, `app-location`,
`app-date-v2`, `app-time`, `app-image-viewer`/`app-read-only-file` shown pictures,
`app-dependency-app` booking lookup), `label`, `key`, `required`, `opts`, `desc`, and the raw
settings panel as `basic` / `advanced` pairs (options, max files, min/max, default value,
"Display this field if" rule, formulas). Section rules are in `settings.advanced`
("Display this section if"). Note: `settings` of a section also carries the previous field's
panel rows; use only its "Section …" / "Display this section if" rows.

## How it maps onto ours (agreed: same content, our structure)

- **Inspection forms**: PDI, PPI, EV. About 80% of the checks are shared (Exterior Body, Body
  Frame, Electrical and Interior, Warning Lights, AC, Brakes and Steering, Axle, Tyres, Brakes,
  Suspension, UnderBody, Equipments, Car Images, Final Car Result) → shared library sections.
  - PPI only (37 questions): service-history Key Checks, its own document list (RC, insurance,
    finance NOC, purchase invoice, bi-fuel), shocker / exhaust / wiring photos, engine noise
    recording, AC video, axle video, ORVM controls, price estimate.
  - EV only (27): Battery, Charger and Hood; Auxiliary Battery; motor, charger, charging port,
    cables; no Engine, CNG, OBD, Transmission.
  - PDI only: the long per-panel photo list and the new-car documents (Form 21/22, temporary
    registration, road tax, PUC, warranty, owner's manual, service booklet, accessories invoice,
    extended warranty).
  - Dropped: the `app-formula` score helpers (our scoring engine computes ratings),
    `slack_thread_details` ("do not touch"), hidden XYZ fields.
- **Check-in → shared Start form**: "Expert Details" is identical in all three apps:
  45-minutes-delayed? → if yes take (pending + 500) payment (amount ≥ 500, mode, screenshot);
  selfie with the number plate; current location; date; time.
- **Wrap-up → shared End form**: identical in all three: Payment Details (taking payment?,
  amount, mode, QR, screenshot if online), Google Review (toggle, QR, screenshot), Car Perfume
  (given?, photo). "Final Car Result" (issues text + photos) stays in the inspection.
- **Inspection Details** (booking lookup + copied booking values) → our booking carries these.
- **Ops-only sections** (hidden from experts: `{$submitter#is_expert}='No'`):
  - "Report First Page": Ops-typed ratings 1–5 (Exterior, AC, Electronics / Drive Train /
    Battery, Engine, Tires), Expert Rating word, top page photo, PPI price estimate,
    manufacturing date → our rating categories + overall word; price estimate and
    manufacturing date become Key Checks.
  - "Key Checks": KeyCheck1–4 with a value (free text), plus named items with defaults (PPI:
    last service date, accidental history reported, total services, service history analysis,
    odometer rollback, engine / transmission work done, last odometer, accidental history,
    scratches and dents, repainted panels, rusting; PDI/EV: tyre manufacturing year, scratches
    and dents, repainted panels) → our Key Checks (text, with the same defaults).
- **Booking form** mirrors BookingCreation 3.0: booking ID, expert ID, customer name / phone,
  address, date, time, type (PDI / Used Car / EV), OBD scanning (yes → OBD amount, default 600,
  max 800), car, final amount, advance amount, pending amount (= final − advance), city,
  service history taken? (Used Car only), any offer given? (yes → why), lead owner (= who
  booked).

## Real master lists found

- Cities (13): Delhi, Faridabad, Ghaziabad, Greater Noida, Gurgaon, Hyderabad, Manesar, Meerut,
  Noida, Pune, Gandhinagar, Ahmedabad, Bangalore.
- Car companies (PPI 25 incl. Datsun, Mitsubishi; PDI 23) + "Others" (then free text).
- Registered states: all Indian states (30).
- Expert codes on Clappia (NCRA1, HYDU1, BLRS1…): staff ids, not a list; real staff come from
  the users file at go-live.
- Car model is free text on Clappia ("Car"); our car make/model list stays ours.
