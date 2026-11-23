# UI / UX review: every page, by role (laptop first)

Reviewed 2026-11-23 on the running local app at commit `a9bf6d6`, at **1440 × 900** (laptop) with a spot check
at **1024 × 768** (tablet, ~5% of users). Phone layouts are out of scope (the Android app comes later).
Font is kept as is. Judged only by what each role sees and has to do, not by how it was built.

Severity: **Must** (hurts daily work or looks broken), **Should** (clear improvement), **Polish**.

---

## 1. The short verdict
The app is clean and readable, but it reads as **a set of database screens**, not as a tool shaped around
the day of an Ops person. The biggest problems:

1. **No real home or dashboard.** Ops land on a filtered table. Nothing answers "what needs me today?".
   The "Dashboards" page is a table with red bars.
2. **Reviewing an inspection is a 12,000 px editable form.** Media is 14,000 px, one card per empty photo
   field. This is the most important Ops task and the least efficient screen.
3. **Bookings and Job board are the same table twice** with slightly different filters.
4. **Headers are inconsistent:** the main button floats in the middle of the header at a different spot
   on every page; every page repeats an "ⓘ" icon and a descriptive sentence.
5. **Brand red is used for everything**: primary buttons, selected choices (a selected "OK" looks like an
   error), every field-type icon, chart bars, the active nav mark. Red stops meaning anything.
6. **Space is used poorly:** forms are a single 720 px column on a 1440 px screen with half the width
   empty; details are hidden behind tabs that each show a tiny card.
7. **No top bar:** no breadcrumb or back path from a booking, no global search, no place for the
   environment (local / staging / production), profile tucked at the bottom of the sidebar.
8. **Dark theme has almost no elevation:** cards, dialogs and the page share one colour; dialogs float
   without a visible edge.

---

## 2. Design direction (one system for every screen)

**Shell**
- **Slim top bar** (48 px) across the content: breadcrumb on the left (`Bookings / DEMO-3`), global search
  in the middle (`⌘K`: booking ID, customer, phone, chassis), on the right the environment badge (Local /
  Staging, hidden on production), a problems bell with a count, and the profile avatar menu (Profile,
  theme, Sign out).
- **Sidebar:** keep it, but lighter and narrower (≈ 216 px; same surface as the page with a hairline
  border, or keep the dark one but quieter). Auto-collapse below 1200 px wide (tablet). Move the user
  block into the top-bar avatar menu; the sidebar then holds only navigation.
- **Logo and name:** today it is the text `VAYU` (letter-spaced) and `V` when collapsed, and the sign-in page
  says `Vayu` in red. Use **one mark**: a small square logo tile (Car C.I.D. red, white glyph) + `Vayu` in the
  normal weight of the UI font; collapsed = the tile only; the same lock-up on the sign-in page. If Car C.I.D.
  has an official logo file, use its mark in the tile.

**Page header (every page the same)**
- One row: **title** (and a muted count, e.g. `Bookings 128`) on the left; **actions on the right**, the
  primary one last. No floating buttons in the middle.
- Drop the "ⓘ" and the explanatory sentence on everyday screens; keep a short sentence only where a first-time
  Admin needs it (Library, Roles, Integrations), and put help behind one `?` in the top bar.

**Colour**
- **Primary actions in ink (near-black / white in dark mode)**, the premium default of modern tools; brand red
  only in the logo, the active nav indicator and **destructive** actions.
- **Semantic colours only for meaning:** green = done / OK, amber = needs attention, red = defect / failed /
  delete, blue = in progress / info. A selected "OK" becomes neutral or green, never red.
- Disabled buttons: neutral grey, not pale pink (pale pink looks broken).
- Field-type icons in the builder: monochrome on a neutral tile.

**Density and layout**
- Tables: 40-44 px rows, sticky header, the row itself opens the record, actions in a `⋯` menu (no rows of
  blue text links or unlabelled icons).
- Forms: a **2- or 3-column grid** grouped by meaning (Customer, Schedule, Car, Assignment), never one long
  column. Record pages: **read view first**, `Edit` per section.
- Detail pages: **two panes**: a fixed summary rail on the left (key facts, people, activity) and the work
  area on the right.
- Dates: human (`Tue 24 Nov, 10:30` and `Tomorrow`), not `2026-11-24 10:30`. Phones formatted
  (`+91 98765 00000`).

**States**
- One empty-state pattern (icon, one sentence, the primary action), one loading skeleton, one error banner.
  Today: Integrations shows only a header row; Problems says "No uploads are stuck." in plain grey.

**Dark theme**
- Three surface levels (page, card, raised/dialog), visible 1 px borders, a darker overlay behind dialogs.

---

## 3. Findings by page

### Everyone
| Page | Finding | Severity | Fix |
|---|---|---|---|
| Shell | No top bar, no breadcrumb, no global search, no environment badge | Must | Top bar (section 2) |
| Shell | Main button floats mid-header, different place per page (`New booking`, `Export CSV`, `New user`, `New item`) | Must | Actions right-aligned in one header pattern |
| Shell | "ⓘ" + sentence on every title | Should | Remove on everyday screens |
| Shell | Sidebar stays expanded at 1024 px (22% of the width) | Should | Auto-collapse below 1200 px |
| Shell | User block repeats the role in lower case (`Priya Ops · ops`) and holds Sign out | Polish | Avatar menu in the top bar |
| Sign in | Plain centred card, red text name; no product feel | Polish | Logo lock-up, environment badge, "Forgot password? Ask an Admin" |
| Profile | Single 720 px column of four cards; password form always open | Polish | Two columns (Picture + Theme / Details + Password); "Change password" opens the form; theme as three preview tiles |

### Ops
| Page | Finding | Severity | Fix |
|---|---|---|---|
| **Home** | Lands on Job board (a table); nothing says what needs attention | Must | **Today** page: KPI strip (today's jobs, unassigned, in progress, uploading, completed today, problems), today's schedule by expert, "Needs you" list (unassigned soon, conflicts, stuck uploads, PDFs out of date) |
| **Bookings vs Job board** | Same table twice; Bookings has no date filter, Job board has no actions | Must | One **Bookings** page with saved views as tabs (Today, Unassigned, In progress, Needs review, All) and a date range; optional **Board** view (columns by stage, cards draggable to assign) as a toggle, or drop Job board |
| Bookings list | Row actions are unlabelled icons (open, cancel, delete) side by side; delete sits next to cancel | Must | Row click opens; `⋯` menu with labelled Cancel / Delete (delete confirms) |
| Bookings list | Filters take a full card; no date range; count and paging at the bottom | Should | One filter row (search, stage, city, type, expert, date range chips); count in the header; 50 per page with page size |
| Bookings list (tablet) | Names wrap to 3 lines | Should | Hide Type/Car below 1200 px, truncate with tooltip |
| New booking | One long column titled "Page 1 / Section 1" (builder words leak in) | Must | Drawer or page with a 2-column grid: Customer (name, phone, address, city), Schedule (date, time), Car (type, model), Assignment (expert, lead owner); hide builder page/section titles when there is only one |
| **Booking: header** | Booking ID big, customer tiny grey, only "Reassign" button, status and expert far right | Must | Header: `DEMO-3 · Sunita Iyer` + chips (car, type, date/time, city) + status + expert avatar; actions right: Assign/Reassign, Reschedule, Cancel, `⋯` |
| Booking: Booking tab | Editable inputs everywhere by default; single column; pale-pink disabled Save | Must | Read view in a 2-3 column grid; `Edit` per group; save bar appears only while editing |
| **Booking: Inspection tab** | 12,157 px of editable inputs; "Check-in" heading three times; Ops see the expert's capture UI ("GPS unavailable · Try again", selfie placeholder); selected "OK" is red | Must | **Review sheet**: summary at the top (defects by severity, Key Checks, missing answers), then answers as compact label/value rows in 2 columns per section with a sticky page index on the left; defects highlighted; `Edit` per section; GPS shows the captured place (map link) or "Not captured"; filters: *Defects only*, *Edited by Ops*, *Empty* |
| **Booking: Media tab** | 14,359 px: one card per photo field, mostly "Nothing here" + "Add photo" | Must | One **gallery** grouped by section showing only fields that have media (toggle "show empty fields"); lightbox with next/previous and field name; add/replace from the lightbox or a single "Add photo to…" picker; ZIP buttons in the header |
| Booking: Ratings | Dropdown per row; Key Checks as dropdowns | Should | 1-5 segmented control per category with the suggested value marked; overall as a word chip; Key Checks as three-state toggles (Auto / Yes / No); show which defects drove each category |
| Booking: Report | Small card, big empty page; long verify URL as text | Should | Inline PDF preview filling the pane; header buttons Download, Regenerate (with "out of date" banner), Copy check link |
| Booking: History | Two near-empty cards | Should | Activity timeline in the left summary rail (created, assigned, rescheduled, started, submitted, completed, Ops edits, PDF versions) |
| Problems | Four tabs, counts only when > 0, plain empty text | Should | One list grouped by type with counts in the sidebar badge and the top-bar bell; empty state "All clear" |
| **Dashboards** | A table of dates with red bars; unlabelled date inputs (`dd/mm/yyyy`); no KPIs | Must | KPI cards (bookings, completed, completion rate, average time to complete, PDFs out of date) with period presets (Today, 7 days, 30 days, This month, custom); stacked bar chart by day/week/month split by type, city or expert; a table below for exact numbers; Export CSV in the header |

### Admin
| Page | Finding | Severity | Fix |
|---|---|---|---|
| Forms list | "What it is" column repeats the name; no last-changed or draft owner | Polish | Columns: name, type, live version, draft (by whom, when), used by bookings |
| **Form builder** | Six buttons of equal weight in the header; Start/End checkboxes take a full-width card; the right third says "Nothing selected" | Should | Header: primary (Start a draft / Publish), secondary Preview, rest in `⋯` (Export, Duplicate, Who sees submissions); show **Form settings** (start/end, visibility) in the inspector when nothing is selected |
| Form builder | Every field-type icon is a red tile; field keys in monospace on every row | Should | Neutral icons; key shown in the inspector and on hover only |
| Form builder (tablet) | Primary button wraps to a second row | Polish | Collapse secondary actions into `⋯` below 1200 px |
| Library list | Floating "New item"; "no form" text | Polish | Header pattern; "Not used" chip; row click opens |
| Library item | Access grid: dashed boxes with coloured text in every cell is loud | Should | Compact matrix with icon + short word, solid only when set here, legend once |
| **PDF templates** | Template tabs show keys (`ev`, `pdi`, `used_car`); preview needs a pasted **internal booking UUID**; right half empty until a block is chosen | Must | Tabs by form name; **live preview pane** on the right that auto-picks the latest completed booking of that form, with a booking search (by Booking ID) to change it; block list left, block settings in a drawer |
| Master lists | List + "Open" link then a dialog; text still mentions "inspection types" | Should | Split view: lists on the left, items on the right with inline edit and drag order; update the text |
| Users | Four blue text links per row; no search or role filter | Should | Row click edits; `⋯` menu (Reset password, Deactivate, Sign out devices); search + role filter; last sign-in column |
| Users dialog (dark) | Dialog blends into the page | Must (dark) | Elevation tokens (section 2) |
| **Roles & permissions** | Ops and Expert on separate tabs; tiny `all/off` buttons 1,100 px from their labels | Should | One matrix: permission rows × Ops / Expert columns with Off / Own / All segmented controls; sticky save bar |
| Integrations, API keys | Empty table header only | Should | Empty state with what it does and the primary action |
| Promote | Duplicates Export/Import that now live on Forms | Polish | Fold into Forms (Import / Export) or keep as "Move between servers" with a clear note |
| Audit log | Filter box floats mid-header; only free-text action filter | Polish | Filters row: who, action (list), date range; link the target |

### Expert (web, laptop)
| Page | Finding | Severity | Fix |
|---|---|---|---|
| My jobs | 640 px cards on a 1440 px screen; ISO dates | Should | Grouped list (Today, Tomorrow, Later, Earlier) with time, customer, car, area; selecting a job shows its details on the right |
| Job summary | Plain text block; phone unformatted; no map | Should | Address with "Open in Maps", call button, booking notes; the Start button stays prominent |
| Inspection steps (wizard) | Seen in code, not run (it would change the demo data): one long column per step, progress bar | Should | At laptop width: step list on the left with ticks and missing counts, the step on the right, sticky Back / Next footer, "saved" indicator |

### Public
| Page | Finding | Severity | Fix |
|---|---|---|---|
| Report check | Clear and minimal | — | Add the logo lock-up |
| ZIP download | Clear | — | Logo lock-up |

---

## 4. Suggested order of work
| Step | What | Estimate |
|---|---|---|
| 1 | **Shell and system:** top bar (breadcrumb, search, environment, avatar menu), header pattern, colour roles (ink primary, semantic colours, red only for brand/destructive), logo lock-up, sidebar auto-collapse, empty states, dark-theme elevation | 2 days |
| 2 | **Ops core:** Today home; one Bookings page with views and date range; booking page redesign (header, summary rail, read-first booking tab, review sheet, media gallery, report preview, activity) | 4-5 days |
| 3 | **Dashboards:** KPIs, presets, chart, table | 1.5 days |
| 4 | **Admin:** PDF live preview + booking picker; builder header and inspector settings; roles matrix; users table; master-lists split view; library access grid | 3 days |
| 5 | **Expert (laptop) and polish:** my jobs list, job summary, wizard layout, dates/phones formatting, tablet pass | 2 days |

About **12-13 days** in total. Each step keeps the browser tests green and adds a screenshot check at
1440 and 1024 widths.

## 5. Decisions needed before building
1. **Primary colour:** ink (recommended, premium and calm) or keep brand red for primary buttons?
2. **Sidebar:** light (recommended) or keep the dark sidebar?
3. **Bookings vs Job board:** merge into one page with views (recommended), or keep both and make Job board a
   real board (columns by stage)?
4. **Logo:** is there an official Car C.I.D. / Vayu mark to use, or should a simple monogram tile be designed?
5. **Ops home:** a new **Today** page as the landing page (recommended)?
