# PDF reports: the plan

Status: Phase 0 (agree on layouts) in review. No code written yet. Last updated 2026-11-24.

Mockups: https://claude.ai/artifact/BP1E3mUr3vukcR2yZXX97T · Field list: `docs/pdi-field-map.md`

## 1. What we are building

A report designer inside Vayu where an admin builds the customer's PDF report from ready-made
pieces ("blocks"), sees the real PDF update as they work, and publishes it. The first template we
build with it is the full PDI report, matching your sample `AV66022PDI.pdf` but without its
problems.

**Why:** today's designer has 9 fixed blocks and almost no styling, so it cannot make your
report. Clappia can, but only through one 412 KB hand-written HTML page with 366 placeholders,
which breaks easily and still has the problems below.

**Problems in the sample we fix:** empty sections still print (CNG), a blank page (page 4), long
tables split across pages without their header, photos alone on a page without their section
title, uneven column widths, no page numbers, the disclaimer pasted as pictures.

## 2. The PDI report your customers get

| Page | What is on it |
|---|---|
| 1 Cover | Big red band with logo and title · car photo beside a vehicle details table · overall rating (5 categories + expert rating) · count of issues found · documents in two columns |
| 2 Summary (new) | Issues found (table, photos below it) · what could not be checked · key checks · expert comments |
| 3 Divider | "Detailed Report" with a list of sections and their page numbers |
| 4–22 Sections | Exterior, body frame, tyres, OBD, electrical and interior, warning lights, brakes and steering, transmission and axle, engine, AC, suspension, underbody, car pictures |
| 23 Verify | Large QR code, link, booking ID, revision, time. Nothing about verifying in headers or footers |
| 24–25 Disclaimer | Your exact text from the sample, typed out, two columns |

On every page: your logo, a faint watermark that shows through tables, page X of Y. Answers are
coloured: green ok, amber not checked or minor, red problem, grey not available. Problems also get
a small coloured label so they still stand out when printed in black and white.

## 3. The building blocks

### Table (three layouts)

**One check per row.** You choose which checks go in (pick them, or "all checks in a form
section", or "all problems found"). The report fills in each check's name and answer, in form
order.

| Check | Result |
|---|---|
| Driver front window | Loose |
| Driver front window remark | Outer weatherstrip is loose |
| Driver back window | Ok |

- A field that is hidden or empty prints nothing. So a remark (its own field, shown to the expert
  only when the answer is bad) appears as a normal row right after its check, only when filled.
- Photo fields never go inside a table. They print in a photo grid under it.
- Optional "fallback text" per row instead of hiding, e.g. "Not mentioned".
- With "all checks in a form section", a check added to the form later shows up by itself.

**Two (or 3–4) checks per row.** Same as above, laid out side by side to save paper. Used for
documents and glass.

| Check | Result | Check | Result |
|---|---|---|---|
| Windshield | Ok | Rear windshield | Ok |
| Driver front window | Loose | Driver front window remark | Outer weatherstrip is loose |

**Grid.** You type the row names and column names; each cell is one field. Used for tyres.
"Fill automatically" fills all cells in one click when field names follow the pattern
(`tyre_driver_front_tread`, `tyre_driver_front_depth`, ...).

| Tyre | Tread | Depth | Made | Shape |
|---|---|---|---|---|
| Driver front | Good | 7.5 mm | 28/2026 | Ok |
| Stepney | Good | 7.9 mm | 29/2026 | Ok |

Every table can set: header text and width of each column, lines (all, rows only, none), row
height (compact, normal, roomy), stripes, header row shown and repeated on each page.

### Photo grid

| Setting | Choices |
|---|---|
| Which photos | All · only issue photos · first photo of each field |
| Photos per row | 1, 2, 3, 4 |
| Box shape | 4:3 · 16:9 · square · as taken |
| Photo does not fit the box | Fill and crop · show whole photo (grey bands) · crop keeping the top |
| Caption | Photo label · check name + answer ("Driver front window: Loose") · your own text · none |
| Frame | Border (none, thin grey, thin red) · corners · gap between photos |

A photo and its caption never split across pages.

### Text

Formatted text: bold, lists, links, colours, 1 or 2 columns. It can include values, e.g.
"Inspected on {{ inspection.date }} by {{ sys.expert }}". The disclaimer is one text block.

### Columns

Puts blocks side by side, e.g. on the cover: car photo on the left (52%), vehicle table on the
right (48%). Widths as presets or your own %, line up top / middle / stretch photo to table
height, gap 4–10 mm. Both sides stay on the same page.

### Verify code

The QR code and link for this report. Used on the verify page.

### Page break, spacer

A page break can have a condition, e.g. "only if the car has CNG".

### Custom HTML (for experts)

For anything the blocks cannot do. HTML and CSS with values like `{{ inspection.colour }}`,
nothing else (no scripts, no outside links or images).

**Deliberately not separate blocks:** defect summary, rating pictures, table of contents,
signature, map. The pieces above already make them (e.g. "Issues found" is a table of all
problems).

## 4. Settings every block has

- **Show only if:** a condition, e.g. "only when fuel is CNG". Single rows and photos can have
  one too.
- **When empty:** hidden by default (so no empty CNG section); can be switched to show.
- **Style rules:** e.g. "when the answer is a problem, red label" or "when severity is critical,
  bold row with red background".
- **Page breaks:** start on a new page · keep together on one page · keep the title with the
  first rows.
- **Box:** space above and below, padding inside, border (none, all sides, bottom, left; width;
  colour), light background tint (light, so the watermark still shows), corners.

## 5. Template settings

- **Page setup:** A4 or Letter, portrait or landscape, margins.
- **Page styles:** where a new page starts, pick its style:
  *Normal* (slim red band, footer with page X of Y) · *Cover* (big red band) ·
  *Full page* (no band or footer, own background colour or image). The divider is a Full page with
  a big title and the automatic section list. The verify page is a Normal page with text, the
  Verify code and a small table.
- **Header and footer:** three slots each (left, centre, right). Each slot holds the logo, text,
  any value, page X of Y, or the date. Each page style chooses its own.
- **Theme:** brand colours (brand, text, ok, amber, red, grey), fonts (3–4 good print fonts with
  the ₹ sign built in, or upload your own), text size, table look, heading look.
- **Logo and watermark:** your images (saved in `backend/apps/core/seed_assets/`), watermark
  strength and position.

## 6. What a report can show

- Any field of the booking, check-in, inspection and end forms.
- Key checks (worked out from the answers) and ratings (5 categories + expert rating; Ops can
  override).
- System values: booking ID, inspection type, expert, inspection and submit time, report
  revision, generated time, number of issues, verify link.
- All problems found, as table rows.
- Dates print as dd-mm-yyyy.

## 7. Changes to the form builder

- **Print colour on each answer option**, e.g. Ok = green, Loose = amber, Damaged = red,
  Not available = grey. Tables use it automatically.
- **Two settings on photo fields:**
  - *Issue photo* (checkbox): counts as an issue photo whenever filled, e.g. "Photos of issues".
  - *Photo of* (pick a check): filled in automatically with the check just above it when the
    photo is added. A linked photo counts as an issue photo when its check's answer is a
    problem, and its caption can say "Driver front window: Loose".
- Behind the scenes, sections get a permanent name, so "all checks in a section" keeps working
  when a section is renamed. Nothing changes on screen.

## 8. The designer screen (simplified 2026-11-24)

Words used on screen: the report is a list of **pages**; a page holds **parts** (a table of
checks, some photos, a piece of text). No "blocks" or "outline".

- **Left: Pages.** Page 1 Cover → Car photo and details, Overall rating, Documents. Page 4
  Exterior → Front, Driver side, Rear, Photos of issues. Drag to reorder. Pages that only show
  sometimes say so ("CNG: only CNG cars").
- **Middle: the real PDF** for a sample booking you pick, updated about half a second after each
  change. Click any part in the PDF to change it.
- **Right: settings of the clicked part.** The common ones first (title, which checks, layout).
  The rest are folded rows with a one-line summary, opened when needed: When to show · Colours and
  rules · Page breaks · Look. Every control from sections 3 and 4 is still there.
- **"+ Add to this page":** six choices with a picture each: Table of checks, Photos, Text, Side
  by side, Verify code, Custom HTML.
- **"+ Add page" quick start:** pick a form page (e.g. Body frame) and get a ready page: title, a
  table for each section, its issue photos. Or start from a blank page, divider, verify page, or a
  shared part (Disclaimer).
- **Top:** Show with [sample booking] · Report settings (paper, page styles, header and footer,
  colours and fonts, logo and watermark, file name) · ⋯ (Export, Import, Copy template, Discard
  draft) · Publish.
- **Warnings** on publish: "4 form fields are not in this report", "1 part uses a field that no
  longer exists".

## 9. Saving, publishing, sharing

- **Draft and publish:** edits go to a draft; Publish makes it live. Reports already sent never
  change; new and re-made reports use the new version.
- **One published template per inspection type** (PDI, Used car, EV, ...).
- **Shared themes and saved block groups ("snippets"):** e.g. one theme for PDI, Used car and EV,
  one "Disclaimer" snippet. Edit once; publishing shows which templates use it, then updates
  them all. Each report remembers exactly which theme version made it.
- **Image library:** logos, fonts, backgrounds, watermarks, uploaded once, used anywhere.
- **Copy a template** to start another inspection type.
- **Export and import (backup):** Export saves the whole template in one file (layout, settings,
  theme, snippets, images). Import replaces the draft with everything in the file. Anything the
  file uses that this form does not have (a field, section or answer option) is a conflict:
  listed, marked red in the outline, with a closest-match suggestion ("use `obd_fault_codes`?").
  Publishing stays blocked until each one is fixed. The same file moves templates from staging to
  production.
- **Starting fresh:** old templates are removed; admins rebuild them with the new designer (Vayu
  is not live yet, so nothing is lost).

## 10. Quality and safety

- Photos are shrunk for print (about 1000 px), originals kept. A full PDI stays under 15 MB.
- Measured: 25 pages with 100 photos renders in 0.6 s with preview-size photos and 2.5 s with
  print-size photos.
- Reports render in the background, as today.
- The renderer can only load our own images and fonts: no outside links, no files on the server.
- Values put into text and HTML are made safe, so typed answers cannot break the page.
- PDFs get bookmarks for each section and a title, for easy navigation in PDF readers.
- Automatic checks on every change: page count, no blank pages, no heading alone at a page
  bottom, header on every page, nothing loaded from outside.

## 11. Phases

Each phase ends with all checks passing, a commit, and a review with you: the current PDI render
next to your sample.

| Phase | What | You see at the end |
|---|---|---|
| 0 | Layouts, field list, speed test | Mockups and field list to approve **(now)** |
| 1 | Form builder changes (print colours, photo settings, section names) and the full PDI form with a sample booking | The new PDI form in the expert app |
| 2 | Report engine, first part: tables, photo grids, text, page breaks, conditions, colours, header and footer | PDI pages 1–10 rendered |
| 3 | Designer screen, first part: pages list, settings panel, quick start, live PDF, publish | Editing the PDI template yourself |
| 4 | Second part: columns, page styles (cover, divider, verify), Custom HTML, style rules, watermark, fonts, bookmarks | The whole PDI report |
| 5 | Sharing: themes, snippets, image library, copy, export and import with conflicts, staging to production | Backup and restore of the PDI template |
| 6 | Final review with you, speed and size check, PDI template exported for staging | Sign-off |

The finished PDI template is the complete report: every section, the verify page and the exact
disclaimer, built only with the designer.

### Phase 2 status (2026-11-24)

Done: the new template format (`backend/apps/reports/schema.json`, schema 2: pages of parts),
values in text (`{{ ... }}`, sandboxed), rich text cleaned on save, tables (one per row, side
by side, grid; rows from picked fields, a form section, or all problems), photo grids (which,
per row, shape, fit, caption, frame), text, verify code, page break, spacer, page styles (normal,
cover, full page) with header and footer bands, watermark, answer colours, hide when empty,
fallback text, show-if on pages, parts and rows, page-break settings, box settings. Photos are
shrunk once for print (1000 px, kept), previews use the 480 px copies, and the renderer loads
only data URIs. Old templates were removed by migration (`reports 0004`); the seeded PDI template
is the full sample report (20 pages). The current PDF templates screen edits the new format in a
simple way until Phase 3 replaces it.

Pulled forward after review (to match the approved prototype): side-by-side columns, bundled
fonts (Inter and Barlow Semi Condensed, SIL OFL, in `backend/apps/reports/fonts`), logo and name
on one line in the header, ring-icon headings, big rating numbers with dots, summary tiles
(issues, not able to check, checks done), the divider's section list with page numbers, coloured
answers in photo captions. Sample render: `docs/samples/DEMO-3PDI.pdf`.

Still for Phase 4: style rules, Custom HTML, PDF bookmarks per section.

## 12. Questions for you

1. Battery state and Generator state: keep them in the PDI form? They are not in the sample
   report.
2. Are the problem levels right? E.g. Repainted counts as minor on a body panel but major on the
   body frame. (Full list in `docs/pdi-field-map.md`.)
3. Keep three free "extra key check" slots like Clappia's KeyCheck 1–3?
4. Should a missing document (insurance, Form 21) count as an issue, or only print amber?
5. Tyres as a grid (recommended) or 18 rows like the sample?

## Appendix: engineering notes

For developers; nothing here changes what you see.

- Template versions pin exact theme and snippet versions; publishing a theme republishes the
  templates that use it.
- Sections get a stable key (like field keys), backfilled, before "all checks in a section".
- Placeholders are `{{ ... }}`, rendered by Jinja2 in a sandbox with variable lookups only
  (`{ }` would clash with CSS).
- WeasyPrint `url_fetcher` allows only our asset ids and data URIs; tested against `file://` and
  remote URLs.
- Designer preview uses the existing 480 px media previews; superseded renders are cancelled.
- Print photos: one cached ~1000 px derivative per photo, made on first render.
- Template file format is shared by export/import and promote bundles (`apps/forms/promote.py`);
  old-format templates are refused with a clear message. Definitions carry `schema: 2`; old
  versions are deleted by migration.
- One JSON Schema for the template definition, validated in Python and used to generate the
  designer's TypeScript types; semantic checks (field refs, snippet cycles) in code.
- Rich text stored as a sanitised HTML subset (p, strong, em, u, lists, a, br, coloured span);
  editor TipTap (one new web dependency).
- Page styles are CSS named pages; bookmarks from `bookmark-level`; PDF metadata set.
- Tests: snapshot the generated HTML; check PDFs with `pypdf` (page count, blank pages, heading
  with first row, header text, no remote fetches).
- The PDI form lives in `backend/apps/core/demo_forms.py` for local use and is also exported as a
  promote bundle (form + template + theme + images) for staging and production.
- Still open: font upload formats and licence check; snippet = a group of blocks (default).
