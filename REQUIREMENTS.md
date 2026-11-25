# Vayu — Car CID Inspection Platform: v1 Requirements

Decided across three grill sessions plus a spec review on 2026-11-22. This is a brand-new system: nothing is migrated from Clappia.
Reference report: `SA37926PDI.pdf` (PDI, 35 pp). Clappia (garuda) was reviewed read-only as a domain reference.

**Guiding principle:** the system **records data through admin-designed forms**. Ops apply the business judgement, and external systems compute things (distance, payouts) and write back through the API. Keep auto-calculation to a minimum. The only automatic logic is listed in §5.4.

---

## 1. Scope, scale, timeline
- **v1:** Booking → Expert check-in/ops → Inspection (PDI / Used Car / EV, and more later as forms) → PDF → webhooks.
- **Out of scope:** Service History, Expense Manager, Leave, customer messaging (Ops send reports manually), payout computation, calendar/scheduling, Hindi, data migration.
- **Users:** ~200 (≈150 experts, 40 ops, 10 admins). Design load is ≈500 inspections/month. Each inspection has 60–150 photos and 3–10 videos.
- **Timeline:** target was 3 months with full scope; **plan.md estimates ~21 weeks (range 18–22)**. Decide before plan Phase 10 between accepting ~21 weeks, a web-only launch at ~week 16, or cutting scope. Big-bang launch, with Clappia kept as a fallback for 2–4 weeks and any switch-back handled manually by Ops.
- **v1.1:** form-version diff and rollback, Ops/Admin screens on Android, polished PDF designer UX.

## 2. Roles, users, security
- **Three roles:** Expert, Ops, Admin. No custom roles and no per-user exceptions: one role per user.
- **Permissions are configurable per role.** The Admin edits what Expert and Ops may do in a role-by-permission matrix (web, Admin only; audited). The **Admin role is locked to full access** (so nobody can lock everyone out), and `roles.manage` can't be granted to another role. **Admin-only, never grantable:** integrations, API keys, and editing forms, PDF templates and master lists.
  - **One permission per action** (~35), e.g. `bookings.delete`, `submissions.edit`, `forms.publish`, `pdf_templates.edit`, `payments.verify`, `ratings.override`. Permissions on bookings, submissions, payments and reports are **scoped**: `own` (assigned to me) or `all`.
  - Only an Admin can create, change, reset or sign out an Admin user, whatever other permissions someone holds (no privilege escalation).
  - This is separate from **field-level access** (hidden/view/edit per role per stage, set in the form builder).
  - **Defaults.** Expert: own bookings/submissions, fill own inspections, record own payments. **Ops: daily operations only**: create/edit/assign/reschedule/cancel bookings, view and edit submission data and media, verify payments, override ratings and Key Checks, regenerate/view reports, dashboards, force-release; read-only view of forms and library. **Ops cannot** change any template (forms, library, PDF templates, master lists), cannot delete bookings or submissions, cannot sign users out of their devices (an Admin may grant it), and cannot manage users, integrations, API keys or permissions. Admin: everything.
- **Users have:** name, email (stored, not used for sending), username, password, role, user ID, active/inactive (deactivate, never delete).
- **Surfaces:** Android (v1: expert screens only) and web (all roles). Form builder, PDF designer, master lists, users, integrations and API keys are **web-only**.
- **Field access:** per role **per stage** (hidden / view / edit), set in the form builder.
- **Experts see only bookings assigned to them** (exception: their own unfinished drafts, see §6). They see the customer phone with tap-to-call.
- **Security:** every failed sign-in gets the same message; five wrong tries lock **that username from that address** for 15 minutes (not the whole account, not the whole address: many phones share one mobile-network IP); a role change signs the app out; a web sign-in posted from another site is refused; forced password change on first login or after an admin reset. Web sessions expire; Android sessions persist for offline work.
- **One active device per expert.** Logging in on a new phone signs out the old one after the old phone's data syncs. **Ops/Admin can force "sign out all devices"** (with a data-loss warning) for lost or broken phones.
- **Config audit log:** who published, promoted or changed a form version or PDF template, master lists, webhooks, API keys, users or roles.
- **Privacy/DPDP:** legal review happens outside this project; nothing extra is built in v1.

## 3. Booking model
- **1 booking = 1 car.** Customer details are plain fields on the booking.
- **Two IDs:**
  - **Booking ID**: entered by Ops as free text; **unique, case-insensitive, trimmed**; editable by Ops/Admin; used by humans and experts.
  - **Internal ID**: system UUID, never changes. **Primary key for the API and integrations.** Webhooks carry both IDs, and a Booking ID edit fires `booking.updated` with old → new.
- **System stage** (fixed, drives the app): `Draft → Assigned → In progress → Submitted → Completed` or `Cancelled`.
- **Ops status:** an admin-defined dropdown, set freely by Ops.
- Only Ops/Admin can create, edit, reschedule, cancel or assign. Experts are assigned by user ID; any booking can go to any expert.
  - **Reschedule** keeps a history of old slots (who and why).
  - **Cancel** requires a reason from a master list ("On arrival" is one of them).
  - **Reassign** is blocked once the server knows the expert has started, unless **Ops/Admin force-release** the job (with a warning that the unsynced draft will be lost; if that draft turns up later it's flagged as a conflict).
- **Delete:** **Admin only** (web). Permanent; there is no trash.
- **Inspection type** can change **only before Start**. If the expert started offline and Ops changed the type meanwhile, the **expert's started type wins** on sync and Ops get a "type change rejected" alert.
- **Locked system fields** (admin can relabel, never remove):
  - Customer name, customer phone, city, lead owner, car make/model, address, inspection date/time: in the Booking form.
  - Chassis no.: in the Inspection form.
  - Search, tap-to-call, filters and dashboards use these.
- **Master lists (admin-managed):** City, Car make/model, Cancel/reschedule reasons, Ops status, plus any custom list. Lead owner = **user picker** (Ops users).
- **Address:** text only. No geocoding or distance check.
- **Payout, conveyance, bonuses, distance:** plain fields filled by Ops or by external systems through the API.

## 4. Form engine (one engine, three form kinds)
- **Form kinds:** **Booking form**, **Ops/Check-in form**, **Inspection forms** (one per type), all built in one web builder.
- **Hierarchy:** Form → Version → **Page** (one wizard step) → **Section** → **Field**. Order and visibility are controlled at every level.
- **Shared library** of sections and fields. When adding an item, the admin chooses: reuse from library, create in library, or create form-local.
  - Library items are **linked**: an edit lands in each form's draft ("update available") and goes live on that form's publish.
  - **A library item in use can't be deleted, only archived** (hidden from the picker; existing uses keep it).
- **Authoring and versioning:**
  - **Forms are built and tested on the staging server**, then **"Promote to production"**. Promotion carries the form version, linked library items, referenced master lists (matched by key) and the PDF template.
  - Production keeps draft → **PDF preview** → publish. No test mode in production.
  - An inspection's version is **frozen at Start**. Jobs not yet started move to the latest version on sync.
  - The expert never chooses a version: the phone pins the **latest published** version when the lead is started (offline too) and sends it with the start. The server keeps it if it really was the latest published version at the phone's start time (10-minute clock allowance; a start time before the booking existed counts from the booking), even if the Admin published a newer one before the start arrived (Ops alerted); an older one is refused and Ops are alerted. The phone keeps every form version its open drafts use (sync sends them again when missing).
  - v1.1: change diff vs live, one-click rollback.
- **Field settings:**
  - Stable machine key: **never editable**, unique within its form and in the library.
  - Form label, **helper text** shown to whoever fills the field, input type.
  - Options for choice fields, each with **defect flag + severity (Minor/Major/Critical)**, set by the admin.
  - Required, **required-if**, min/max, **regex pattern**, **cross-field checks**.
  - Media count min/max; role and stage access.
- **Input types:**
  - Choice: single/multi choice, yes/no, **master-list dropdown**, **user picker**.
  - Text and numbers: short/long text, number (unit, min/max), currency, phone.
  - Date and place: date, time, datetime, GPS location.
  - Media: photo(s), video(s), file (photo or PDF ≤20 MB), signature.
  - **System-filled** (derived Key Checks, suggested ratings): read-only, and Ops can override.
  - No repeating blocks.
- **Conditions:** show/hide and required-if, based on **any field of the same booking, across forms** (e.g. a checklist rule reads fuel type from the Booking form).
- No built-in expert notes, photo annotation or damage diagram.

## 5. Inspection flow (expert, Android)
### 5.1 App basics
- Kotlin / Jetpack Compose, **Android 11+**, English, distributed as an **APK download link** with an in-app self-update.
- **Forced minimum app version:** an outdated app can't start new jobs but can finish a job already in progress, including one started offline before its version became too old (accepted; Ops alerted). Work on a form the Admin switched off after the start is accepted too (Ops alerted).
- **Visible push notifications** (Firebase) for: new job assigned, rescheduled, cancelled / reassigned away, force-released by Ops, booking details changed (with field and option labels; never a field the booking form hides from experts, and no customer name when that is hidden). Ops' review (ratings, Key Checks, cleared alerts) is never shown to experts. The check-in answers are kept from Start, so Ops see the arrival selfie and GPS of a running job. Each push also triggers an immediate sync. Pull-to-refresh is also available.
- **My Jobs** list → **booking summary confirmation** → Start.
- **Check-in** on Start:
  - GPS and **server-corrected time** captured automatically (no distance check).
  - Source location and travel details.
  - Selfie / arrival photo.
- **Linear wizard** (Next/Back + page jump list). Every field starts **blank** and is answered one by one. A final review screen lists the gaps, and submit is blocked until all required fields are filled.
- Last wizard steps: **Payment → Google review → Submit** (one submit).

### 5.2 Payment
**Changed 2026-11-24 (owner): payment is ordinary wrap-up form fields**, built by Admin in the form
builder like any other field; there are no payment-specific screens, models or permissions ("they are
forms at the end of the day; the app keeps its generic nature").
- New wrap-up forms start with Taking payment?, mode, amount and screenshot as **ordinary** fields
  (not locked); Admin changes them freely: e.g. up to 2 payments, Paid now / Pay later, transaction
  ID, the payment QR (an image field), an Ops-only "Verified / Mismatch" choice and note.
- Who fills or sees each payment field, and whether it is in the report, is set on the field (field
  access by role and stage; the report designer).
- Pay later: Ops fill the payment in the wrap-up answers when it arrives (normal answer editing).
- No Needs-you item for payments; the expert is not told about a mismatch.
- To find payments: Bookings **filter by an answer** (generic, web and Android): pick any choice or
  yes/no field the person may see and a value, or "not filled".

### 5.3 Media
- Photo/video fields: the expert taps the camera repeatedly up to the configured count (a field without its own maximum takes **1 file**). Camera and gallery are both allowed.
- **In-app camera photos get a burned-in stamp** (booking ID, expert, server time, GPS, or **"GPS unavailable"**). Gallery photos aren't stamped. The source is tagged internally and never shown in the PDF.
- Stored as sent, plus a preview copy and, for an iPhone **HEIC** photo or one larger than 2048 px, a **separate JPEG copy** (≤ 2048 px) used for previews and the PDF. Videos are clips of up to 60 s at 720p, compressed on the phone. The server checks each video really is an MP4 / MOV file. A failed upload, or one left unfinished longer than the stuck-upload limit (6 h), does not use up a place on its field.
- Expert can **delete/retake** and review full-screen before submit.
- **Upload as you go** on any network: background, resumable, chunked, checksum-verified, **sent directly from the phone to R2** via pre-signed URLs (never through the API server).
- **Local copies:** cleared manually only; **unuploaded files can never be cleared**. Low-storage warning below 2 GB, and starting a job is blocked below 500 MB.

### 5.4 The only automatic logic
1. **Key Checks** (derived fields): any/all/count rules over other answers. Ops can override.
2. **Rating suggestions:**
   - Per form, with admin-defined categories.
   - Each category maps to sections, a points deduction per severity, an optional cap on Critical defects, and the rating-to-word cut-offs.
   - **Experts never see or set ratings.** Ops override freely (no reason required).
   - **Launch rules (configurable by Admin):**
     - Categories: PDI and Used Car use Engine, A.C., Electronics, Exterior, Tyres. EV uses **Battery & Charging**, A.C., Electronics, Exterior, Tyres. Every form also has an overall **Expert Rating**.
     - Section mapping:
       - Engine ← Engine, Transmission & Clutch, OBD, CNG, Axle
       - A.C. ← Air Conditioning
       - Electronics ← Electrical & Interior, Warning Lights
       - Exterior ← Exterior Body, Body Frame Accidental, Underbody
       - Tyres ← Tyres, Brakes & Steering, Suspension
       - Battery & Charging (EV) ← Battery/Charger/Hood, Auxiliary Battery
     - Each category starts at **5**. Each defect deducts **Minor 0.25 / Major 1 / Critical 3**, with a minimum of 1. Shown as a whole number, rounded half up.
     - Overall = average of the categories: **≥4.5 Excellent, ≥3.5 Good, ≥2.5 Average, else Bad**. Any Critical defect anywhere caps the overall at **Average**.
3. **Recalculation:** when Ops edit answers after submit, Key Checks and suggestions recalculate, but **any value Ops overrode stays as Ops set it**.

## 6. Offline & sync rules
- **Fully offline-first.** Jobs and frozen form versions are pre-downloaded. Answers are saved on the phone instantly. **Drafts live on the phone only**: if the phone is lost before submit, the inspection is redone (only photos already uploaded survive).
- **Submit:** answers lock, and the stage becomes Submitted with "uploading x/y". When all media is verified, the stage becomes **Completed**, the PDF is generated, and webhooks fire.
- **After submit, only Ops/Admin/API edit** (simple overwrite + `last_edited_by/at`). Nothing goes back to the expert.
- **Concurrent web edits:** a save is stopped if someone else saved since the form was opened ("Priya changed this 2 min ago – reload"). On retry only the fields you changed are applied.
- **Ops changes while the expert is offline:** push notification + banner on the next sync (old → new).
- **Cancelled while the expert has a draft:** the draft still syncs and is kept on the cancelled booking.
- **Reassigned while the expert has a draft:** the job **stays in that expert's list** as "Reassigned – submit or discard". If submitted, **the submission is accepted** and the booking is flagged "Conflict: two experts". If the new expert hasn't started, their job is withdrawn; otherwise Ops choose which inspection to keep. Nothing completes and no report is made from the late work until Ops choose.
- **Force-release** closes the expert's draft (released): a new start opens a new draft (one open draft per expert per booking); the released one is still accepted if it arrives, as a conflict.
- **A second submit** by the same expert on a lead they already submitted is **refused** ("Already submitted; Ops can edit it"); the same request id still returns the first result.
- **Logout is blocked while data is unsynced.** If Admin disables an account with unsynced data, the Admin sees a data-loss warning.
- **Web sign-out** first says what the browser still holds that has not reached the office (inspection drafts, photos and files not sent or not checked yet); signing out anyway deletes them. Every sign-out clears the inspection drafts and queued files from that browser, so nothing stays behind on a shared computer.
- **Time:** server-corrected using the offset from the last sync. If there's been no sync that day, the last known offset is used and the time is **flagged "unverified"**. The phone sends `unverified_time` with the start and every submit; the server keeps it (once true, it stays true) on the inspection and its booking, the booking API shows it and the Ops problem queue lists it (`problem=unverified_time`).

## 7. PDF reports
- **v1 includes a basic block designer** (web), with one template per inspection form and its own draft → preview → publish (built on staging, promoted with the form).
- **Report labels live in the template** (field key → report label). The app provides only values and photos.
- **Blocks:**
  - Cover + info grid.
  - Tables: 2-col label/value, ratings row, documents grid.
  - Photo grid (1/2/3 per row, captions; the admin picks field + photo positions; no photos by default).
  - Heading, rich text, page break, spacer.
- **Block-level show-if.** Inside a shown block, rows always print, even when empty.
- **Fields the inspection doesn't have** (older form version) **print blank**. **Publishing a form version warns** about new fields the PDF template doesn't use.
- **Branding:** header/footer per template, background watermark, value colours, font sizes per block.
- **Extras:**
  - Page numbers.
  - Footer with generated time + revision.
  - **Verification QR** linking to a verify page on your own subdomain. The page shows a summary only: booking ID, car, type, date, overall rating, current revision.
  - Admin-set filename pattern.
- **No PDF size limit.** Videos are internal only.
- **Generation:** automatic **once**, when the booking completes. After that nothing re-renders by itself: Ops edits, files Ops add or replace and booking changes only mark the PDF **"out of date"**; Ops press **"Regenerate PDF"** (one new PDF, one `pdf.ready`). The every-few-minutes sweep only retries failed or killed renders. **Only the latest PDF is kept** (no old revisions). Renders run one at a time, with a memory limit and timeout. A later render that fails keeps the last PDF (the verify page keeps working); the failure is listed for Ops.
- **Which inspection the report uses:** the one that counts. During a two-expert conflict the customer **keeps the old report** and Regenerate is disabled; when Ops pick the inspection that counts, the PDF renders once automatically. If the first completion is already in conflict, there is no report until Ops resolve it.
- **Deleting a booking** removes all its files from storage (originals, previews, copies, the PDF, ZIPs). **Retention:** the photo setting also covers documents and signatures; cancelled bookings are purged too (counted from the cancel date); ZIPs go after their 7 days. Once the retention setting has purged a booking's photos, its **last PDF is kept** and Regenerate is disabled with the reason.
- **Photo / video ZIP links** in the report hold only the files the counted inspection uses, and **expire 30 days after the booking's first PDF**; a PDF regenerated after that leaves those links out. The verify page (QR) keeps working.
- An inspection on an older form version keeps the **layout made for that version** (the newest template version published before the next form version). "Not able to check" counts the option keys `not_checked` and `not_able_to_check`.
- **Access:** Ops + Admin (web), plus the webhook link.

## 8. Integrations
- **Webhooks:** multiple integrations per form. **One integration = one event** (a booking form integration: booking events only); to react to several events, make several (a Duplicate button copies one). It fires on every occurrence (no condition filters).
  - **Events:** booking created/updated/deleted (incl. stage changes); inspection started/submitted; media complete + PDF ready (also on each regenerate); conflict and stuck-upload alerts.
  - API writes fire webhooks too, including bulk updates. Spam is avoided by choosing the event, not by a silent flag.
  - **The request is designed in a visual editor:** method (POST, PUT, PATCH, GET, DELETE), URL (values allowed in the path only), query parameters, headers, and a body. Every text can hold **values picked from a searchable list** (form answers by form, job facts, results, links, event); nothing is typed as a raw key.
  - **Body:** *Standard* (the fixed JSON with toggles for data, PDF link, image ZIP link, video ZIP link, and a field checklist) or *Custom* (a JSON editor: the Admin writes the JSON and `{{` suggests the values; system-made lists such as photo links, Key Checks and ratings can be used; a string that is exactly one value keeps its type, `{{value | text}}` forces text, mixed text is text, missing is `null`).
  - **Preview** shows the whole request live (method, final URL, headers, body) for the latest job, a job picked by Booking ID, or sample values when the form has no job; it never sends anything or builds a ZIP.
  - **No HMAC signing:** the receiving system is authenticated by a token Admin puts in a header (over https). Retried with backoff, delivery log with re-send, test button (sends the designed request, marked `X-Vayu-Test`).
  - **Links:** PDF links are signed with 7-day expiry. **ZIP links open a "Preparing… x%" page**, which builds the ZIP once, caches it for 7 days, then downloads automatically.
- **REST API:** full CRUD via **API keys scoped to forms and fields**. A key may also **assign / reassign, cancel, reschedule and change type** (`POST ext/bookings/{ref}/assign|cancel|reschedule|change-type`), each a flag on the key that the Admin turns on (off by default, like delete); every action is audited and fires the same webhooks as on the web.
  - **Delete is off by default** per key; Admin must grant it explicitly.
  - Writes use field keys, bulk updates are supported, and booking lookup works by internal ID (primary) or Booking ID.
  - Auto-generated **Swagger** docs. No rate limiting.

## 9. Ops web
- **Booking:** create, assign, reschedule, cancel, force-release, force sign-out; submission edit; media gallery and video playback; add/replace/delete media; **download-all ZIP**; payment verification; rating/Key Check override; PDF download/regenerate.
- **Job board:**
  - Today / date-range views with stage + Ops status.
  - Filters for city, expert, type and stage.
  - **Problem queue:** stuck uploads (checked every hour; files on finished or cancelled jobs, failed or replaced ones drop out; bell, push and webhook once per booking, the bell at most daily), conflicts, rejected type changes (Ops clear each alert once looked at), unverified payments, pay-later outstanding, edited but not regenerated, unverified times, late starts and too-quick jobs not yet reviewed.
  - **Global search:** Booking ID, customer name/phone, chassis no., car.
- **Dashboards:** volume by day/week/month × type, city, expert, lead owner; **CSV export**.
- **Inspection timing (Admin and Ops only, never Experts; see `docs/plan-timing.md`):**
  - **Settings page** (`/settings`): Admin sets the late-start grace (one number, default 15 min) and the minimum inspection time per inspection type (PDI 30, Used car 45, EV 40, others the default 30). Ops can see the page but not change it. Every change is in the audit log.
  - **Started late:** the server got Start more than the grace after the booked date + time. **Too quick:** the server got Submit less than the type's minimum after Start. Server clock only; a job whose Start never reached the server is never flagged. A changed limit re-flags old jobs at once.
  - Shown as: two **Today** cards, two **Bookings** tabs ("Started late", "Too quick") with the usual filters, **Dashboard** counts and % (vs the previous period, and per expert), a badge on the **job page**, and **Needs you** (jobs from the last 7 days) until someone clicks **Mark reviewed**. The two are separate problems: each has its own tab, card, Needs-you group and Mark reviewed (who and when go in the timeline); reviewing one leaves the other open.

## 10. Stack & ops
- **Backend:** Django + DRF, Postgres, Celery + Redis (PDF rendering with headless Chromium, webhooks, ZIPs, media processing, push).
- **Web:** React. **Android:** Kotlin/Compose. Push via Firebase Cloud Messaging.
- **Hosting:** one **DigitalOcean Bangalore** VPS (**4 vCPU / 8 GB**) running Docker, with **Cloudflare R2** for media, PDFs and ZIPs.
- **Domains:** `app.carcid.in` (web + API at `/api/v1`), `verify.carcid.in` (QR page), `staging.carcid.in`.
- **APK** is served from a logged-in download page on the web app (latest build in R2). The in-app updater checks the same place.
- **Staging server** (separate VPS + bucket) is **also the form-authoring environment**, so it needs backups too.
- **Error tracking** for app, web and server.
- **Backups:** configured by you.
- **APK signing key** backed up offline: losing it means existing installs can never be updated.
- Media retention: keep everything; set a policy later.

## 11. Launch seed forms
Admins can change these in the builder; they're the launch seed and the test data. **Bold** = locked system field.
- **Booking form** (Ops):
  - System fields: **Booking ID**, **Customer name**, **Customer phone**, **Address**, **City**, **Date**, **Time**, **Inspection type**, **Car make/model**.
  - Car variant (text), OBD scanning (Y/N), OBD amount.
  - Final amount, Advance amount, Pending amount, Extra conveyance *(hidden from expert)*.
  - Any offer given (Y/N), Service history taken (Y/N).
  - **Lead owner**, **Assigned expert**.
- **Ops form**: one form with 3 pages, using stage access:
  1. **Check-in** (expert, at Start): GPS + time *(auto)*, Selfie, Coming from (Home / Previous booking), Previous booking, Is last booking today (Y/N).
  2. **Wrap-up** (expert, before submit): Taking payment / Pay later, Payment slots 1–2, Google review taken (Y/N), Review screenshot, Car perfume given (Y/N), Perfume photo.
  3. **Ops** (Ops/API only):
     - Status: Ops status, Handled by, Cancellation on arrival (Y/N), Delayed > 45 min (Y/N), Delayed > 1 h (Y/N).
     - Amounts: Booking amount, Total inspection fee, Booking conveyance, Final conveyance, Adjustment amount.
     - Distance: Distance travelled, Cumulative distance, Distance to home.
     - Bonuses: On-time bonus, Testimonial bonus, T-shirt bonus.
- **Inspection forms**: PDI, Used Car and EV, seeded from the SA37926 report sections and the Clappia section lists.

## 11a. Non-functional targets
- PDF render ≤ 2 min for a 150-photo report (one render at a time).
- API p95 < 500 ms for list, open and save.
- Upload chunks of 8 MB, resumable.
- Zero answers lost when the app is killed; zero media lost before checksum verification.

## 11b. Setup checklist (you create, under the company account)
DigitalOcean (prod + staging droplets) · Cloudflare R2 (prod + staging buckets, **CORS allowing app/staging origins**) · GitHub repo · Firebase project (FCM) · Sentry (3 projects: server, web, android) · DNS records for app/verify/staging.carcid.in · Android signing keystore, backed up offline.

## 12. Accepted risks
- **3 months, solo, at a scope estimated at 5–6 months:** very likely to slip, and the offline edge cases and PDF designer are where shortcuts would hurt correctness.
- Big bang with no pilot; the Clappia fallback is manual and can split data across two systems.
- Phone-only drafts: a lost or broken phone mid-job means redoing the inspection.
- Simple overwrite with only the latest PDF kept: no proof of what an earlier report revision said in a dispute.
- Permanent deletes (Admin only), with no trash.
- No test mode in production: all testing depends on staging matching production.
- Single VPS: no high availability. No uptime alerts.
- No PDF size limit: large PDFs may be too big for email.
- APK sideloading: the update UX is yours to run.
- DPDP compliance deferred to an external legal review.
