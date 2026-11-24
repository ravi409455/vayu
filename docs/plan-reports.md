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

### Download links (2026-11-24)

- Every report has two more links: all photos and all videos of the inspection, each as one
  ZIP. They are the verify link plus `/photos` or `/videos` (`{{ sys.photos_url }}`,
  `{{ sys.videos_url }}`), so they work as long as the report does. `{{ sys.photo_count }}` and
  `{{ sys.video_count }}` say how many.
- Use them anywhere: the **Button link** part (Download photos / Download videos / Verify; it
  hides when nothing is behind it), a link in rich text (Link… in the toolbar), or as text.
  A link in report text can only hold these three values, never a form answer.
- What goes in: photo or video fields of the inspection form that show for this car. Start and
  end forms and Ops-only uploads stay out. Inside the ZIP: a folder per section, files named by
  the field ("Engine bay/Engine oil photo.jpg").
- The customer's page builds the ZIP once, shows progress, then the download starts. A built
  ZIP is kept 7 days, then built again on the next tap.
- **Retention** (Admin → Settings → Photo and video storage): keep photos / videos N days
  (0 = for ever, else 30–3650). An hourly job deletes older originals of completed jobs for
  good, with their previews, print copies and ZIPs. Stored PDFs keep their pictures; the
  report's links then say the files are no longer available.
- PDI template: Download photos and Download videos under the verify box. Used car and EV end
  with a verify page that has both buttons.
- **Deployment (to do before go-live):** `infra/Caddyfile` only sends `APP_HOST` to the API; it
  serves neither the web app nor `verify.carcid.in`. Report links are
  `VERIFY_BASE_URL/<token>`, `/<token>/photos` and `/<token>/videos`, and the web app answers them
  at `/verify/<token>[/photos|/videos]`. Either set `VERIFY_BASE_URL=https://app.carcid.in/verify`
  once the app host serves the web build, or give the verify host a site that serves the web
  build, sends `/api/*` to the API, and rewrites every other path `/x` to `/verify/x`. Add the
  verify host to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` either way. PDFs already made keep
  the address they were made with, so decide this before the first real report.

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

### Phase 3 status (2026-11-24)

Done: the designer screen (`web/src/pages/admin/PdfDesigner.tsx`, `web/src/pages/admin/report/`).
Pages list with drag and drop and "+ Add to this page" (table, photos, text, side by side, verify
code, contents list, space, page break); "+ Add page" from a form page (heading, a table per
section, its issue photos), blank, divider or verify page. The real PDF drawn with pdf.js, a
moment after each change, unsaved edits included; click a part in the PDF to select it.
Settings per part with folded groups (when to show, page breaks, look, box); rich text with
"Insert a value"; grid editor with "Fill automatically". Report settings: header and footer
slots per page style, colours, fonts, watermark, paper, file name. Autosave of the draft,
warnings (fields the form lacks, form fields not in the report), publish, discard draft.
Backend: `POST pdf-template-versions/<id>/preview` with a definition returns the PDF and where
each part sits; `POST .../checks` lists problems and fields left out.

Browser tests can run beside a local stack: `E2E_WEB_PORT=5176 E2E_API_PORT=8003 npx playwright test`.

### Phase 4 status (2026-11-24)

Done:
- **Style rules** on tables (Look → Style rules): "when [the answer is a problem / severity is
  critical, major or minor / the answer is red, amber or green / not able to check / no answer]"
  → label colour, answer colour, row tint, bold. Lower rules win. Severity comes from the answer
  options in the form builder. The PDI template uses two: problems list "critical → bold on a red
  tint", section tables "not able to check → grey answer".
- **Custom HTML** part ("+ Add to this page" → Custom HTML): HTML and CSS with values like
  `{{ sys.booking_id }}`. Cleaned on save: no scripts, links, pictures or `url(...)`; the CSS is
  nested under the part, so it only styles that part.
- **PDF bookmarks**: each page is a bookmark, its part titles under it (e.g. Exterior → Front,
  Driver side, Rear…). Headings inside text are not bookmarks, so nothing is listed twice.

Not separate settings (on purpose): style rules on photo captions (captions already take the
answer's colour); turning bookmarks off per page.

### Phase 5 status (2026-11-24)

Done:
- **Picture library** (Report settings → Pictures): logos, watermarks and backgrounds with a name,
  uploaded once, picked from a list in the header, footer and watermark settings. The same
  picture uploaded twice is kept once. A picture still in use cannot be removed.
- **Shared theme** (Report settings → Theme): colours, fonts, header, footer and watermark in one
  theme, e.g. "Car C.I.D." for PDI, Used car and EV. "Save this report's look as a shared theme",
  "Use a shared theme", "Stop sharing (copy it into this report)". While a report uses a theme,
  those tabs show the theme's settings, read only.
- **Shared parts**: any part can be shared ("Share with other reports"), e.g. the disclaimer;
  "+ Add to this page" and "+ Add page" list the shared parts. To change one: "Stop sharing" in
  one report, change it, then share it again replacing the old one.
- **Versions**: each save of a theme or shared part is a new version. Every template using it
  moves to the new version at once: its draft changes and its live layout is republished (refused,
  with nothing changed, if a template's form lacks a field the new version shows). Each template
  version names the exact theme and part versions it uses, so a report always shows what it was
  made with.
- **Copy a template** (⋯ → Copy to another form): a new draft for another inspection form.
- **Export and import** (⋯ → Export / Import): one JSON file with the layout, settings, shared
  theme and parts, and pictures. Import replaces the draft. A shared item already here with other
  content is kept (noted). Anything the form lacks is marked "fix" in the pages list and listed in
  warnings with the closest match ("Use inspection.odometer"); publishing stays blocked until fixed.
- **Staging to production**: form bundles (`apps/forms/promote.py`) now carry the template's
  pictures and shared items, matched by key on the other server.
- Local demo: the PDI template uses the shared theme "Car C.I.D." and the shared part
  "PDI disclaimer"; the logo and watermark are in the picture library.

Not done (on purpose): uploading your own fonts (the three bundled fonts cover the ₹ sign;
upload needs a licence check); answer-option conflicts on import (templates name fields and
sections, not answer options).

### Phase 6: final review (2026-11-24)

**Speed and size** (measured on this Mac; staging should be similar or faster):

| What | Result | Target |
|---|---|---|
| Real PDI report (DEMO-3, 18 pages) | 2.8 s, 0.7 MB | under 2 min, under 15 MB |
| 100 photos, worst case (noisy test photos) | 7.4 s, 5.4 MB | under 15 MB |
| 150 photos, worst case | 11.1 s, 8.2 MB | under 2 min |

Fixed during the review: every photo used to print at 1000 px, so 100 photos made a 21.5 MB PDF.
Now a photo in a small box (up to 65 mm wide, e.g. 3 per row) prints at 600 px, still about
250 dpi; a photo across the page stays at 1000 px.

**Layout checks** now run with every preview and show under warnings: a blank page, and a
heading left alone at the bottom of a page. The PDI report has none. (Header and footer come
from the page style, and nothing can load from outside, so those need no check.)

**Staging bundle:** `docs/samples/pdi-bundle.json` is the PDI form with its report: layout,
shared theme "Car C.I.D.", shared part "PDI disclaimer", logo and watermark. Tried on an empty
server: everything arrives as drafts. Import the booking form first (the report shows booking
fields), then this bundle, then publish the form and the template.

**Sample report:** `docs/samples/DEMO-3PDI.pdf`.

**Sign-off checklist** (everything agreed; ✓ = built and tested):

| Agreed | Where to see it |
|---|---|
| ✓ Full report with the exact disclaimer | Sample PDF, last pages |
| ✓ Cover: car photo beside the vehicle table, logo and name on one line in the header | Sample PDF, page 1 |
| ✓ Ratings as big numbers with dots, issues / not able to check / checks done tiles | Page 1 |
| ✓ Divider page with the section list and page numbers | Page 3 |
| ✓ Verify page with QR code before the disclaimer | Second last page |
| ✓ Watermark shows through table rows | Every normal page |
| ✓ No photos inside table rows; remarks are normal rows | Section pages |
| ✓ Issue photos and "photo of" with "Check: answer" captions | Summary, section pages |
| ✓ Page breaks: new page, keep together, keep title with rows | Part settings → Page breaks |
| ✓ Photo grids: per row, shape, fit and crop, border, gap, captions | Photo part settings |
| ✓ Side by side columns with widths and line-up | Cover page part |
| ✓ Box: space, padding, border, light tint, corners | Part settings → Box |
| ✓ Style rules (e.g. critical → bold on red) | Table settings → Style rules |
| ✓ Custom HTML for experts, safe | "+ Add to this page" → Custom HTML |
| ✓ PDF bookmarks per page and part | Open the PDF's side panel |
| ✓ Simple designer: pages and parts, real PDF, click to select | PDF templates screen |
| ✓ Picture library, shared themes and parts with versions | Report settings → Theme, Pictures |
| ✓ Copy, export and import with conflicts marked and suggestions | ⋯ menu |
| ✓ Staging to production carries pictures and shared items | `docs/samples/pdi-bundle.json` |

Not built, on purpose (say if you want them): uploading your own fonts; import checks on
answer options.

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
