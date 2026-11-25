# Vayu Android app: agreed requirements (design gate)

Agreed with the product owner on 2026-11-24. These replace the Android parts of REQUIREMENTS.md
and plan.md (Phases 13–15) where they differ. **No app code is written until the clickable
prototype of every screen below is approved.**

## Who and what

- **One app** (`in.carcid.vayu`, home-screen name **Vayu**) for **Experts and Ops**. The screens
  shown depend on the role.
- **Admins are refused at sign-in:** "The app is for Ops and experts. Use the web." Admin tools
  (forms, library, master lists, users, roles, integrations, API keys, PDF designer, promotion,
  audit) stay web-only.
- **Ops get everything Ops web does** (changes REQUIREMENTS §2, which had "expert screens only"):
  Today, Bookings (create, edit, assign, reschedule, cancel, force-release, delete drafts), booking
  detail with answer editing, media view/add/replace/delete and ZIP, rating and Key Check
  overrides, payment verify/record, PDF view/regenerate/share, conflict resolution, activity,
  Needs you, Dashboard with CSV export, sign out a person's devices.
  - Cost accepted: every later Ops change on the web is built twice (web and app).
- **One active phone per person**, Ops included. Signing in on a new phone signs out the old one
  after its data syncs.
- No app lock. People stay signed in, and the phone's own screen lock is the protection.
- English only. Phones only, **portrait only** (rotation locked; the camera still takes
  landscape photos). Android 11+.

## Navigation

- **Ops:** bottom bar **Today · Bookings · Dashboard · Refresh** (kept clean, nothing else in it).
  Top bar: **bell** (opens Needs you, with a count badge) and **profile** avatar.
  **"+" New booking only in the top bar of the Bookings page.**
- **Expert:** bottom bar **Leads · Uploads (count) · Refresh**. Top bar: bell and profile.
- **Wizard:** one form page per screen, scrolling vertically; sticky Back / Next at the bottom;
  the "Step 3 of 14 · Exterior" title opens the page list (done ticks, "needed" counts,
  not-opened dots) to jump anywhere. Pages marked "must be finished" still hold the pages after
  them.

## Look and feel

- The web's look (colours, type, status pills, icons, light/dark/match-device theme; the theme
  choice is shared with the web profile), built from standard Android Material 3 parts so back
  gestures, sheets and pickers behave as Android users expect.

## Offline

- **Ops:** show the last-loaded data offline with a clear, always-visible
  "Offline · as of 10:42" highlight. Every Ops action needs a connection and is disabled offline.
- **Expert (from REQUIREMENTS §6, confirmed):**
  1. Leads and their forms are downloaded ahead of time; the whole inspection works with no signal.
  2. Answers are saved on the phone instantly. A draft lives only on the phone: a lost phone means
     redoing the inspection, and photos already uploaded survive.
  3. The lead becomes "in progress" only when the check-in is complete (offline: recorded with the
     check-in time and sent on the next sync).
  4. Photos upload in the background on any network, resume after a restart, and are
     checksum-verified.
  5. Submit locks the answers → "Submitted, uploading x/y" → Completed when every file has arrived.
  6. Reassigned with a draft → "Reassigned – submit or discard". Cancelled with a draft → the draft
     still syncs. Ops type change after an offline start → the expert's type wins.
  7. Sign-out is blocked while anything is unsynced; the message names the leads, and Uploads lists
     exactly those (answers not submitted, files to send or still being checked, files the server
     refused, drafts of leads no longer on the list with Send / Discard).
  7a. A file the server refuses (too large, wrong type) shows its reason in Uploads and can be
     removed, also after Submit; the rest of the inspection is sent without it.
  7b. After a sign-out nothing of that person stays: their drafts (answers, photos), notices, reminders
     and saved copies are deleted. Signed out without signal, the server's sign-in for that phone is
     ended at the next sign-in. Signed out by the server: sent drafts are deleted, unsent ones wait.
     Sign-in tokens are sealed with a key in the Android Keystore; an update moves tokens saved by an
     older version, so nobody is signed out by it. Ops' saved copies keep the latest 300.
  8. An app below the minimum version can't start new leads but can finish the current one.
  9. Times are corrected by the server clock; with no sync that day, or the phone restarted or its
     clock changed since the last sync, the time is marked "unverified" (stamp "(phone time)"), and the
     start and every submit tell the server (`unverified_time`; once true it stays true) so Ops see it.
  10. Under 2 GB free → warning; under 500 MB → Start is blocked.

## Camera and media (confirmed)

- Camera, microphone refused: after one "Don't allow" Android may never ask again, so the camera
  shows **Allow camera in Settings** (the app's page in Settings, checked again on coming back) and the
  video camera says **No sound: the microphone isn't allowed.** with **Allow**.
- A field without a "most files" setting takes **one** file (the agreed default, same as the server).

1. In-app camera with a burned-in stamp: booking ID, expert, corrected time, GPS or
   "GPS unavailable".
2. Gallery allowed unless the Admin set the field to camera-only (e.g. selfie); gallery photos are
   not stamped.
3. Photos ~2048 px / ~500 KB plus a preview; video up to 60 s at 720p, about 2.5 Mbps (~19 MB a minute)
   on every phone. Gallery videos go up as picked, within the server's 300 MB limit.
4. Tap the camera repeatedly up to the field's limit; full-screen review; delete and retake.
5. Photos start uploading the moment they are taken.
6. Local copies are cleared manually from Uploads; files the server has not yet received **and
   checked** can never be cleared (a file that fails the server's check is sent again).

## Phone-only extras

- Call and Google Maps directions (customer, expert).
- WhatsApp chat shortcut: opens a chat with the number; nothing is pre-written or sent by the app.
- Ops: share the PDF report through the phone's share sheet.
- Expert: scan text with the camera (on-device), e.g. chassis or registration number. **Which fields
  offer Scan is the Admin's choice:** the web form builder gets a "Let the expert scan this with the
  camera" switch on short-text fields (a small web change, like the existing "automatic" switch on
  date fields); the app shows a Scan button only on those fields. The scanned text is shown for
  confirmation and the field stays editable afterwards, so a wrong scan is simply typed over.

## Screen decisions from the first prototype review (2026-11-24)

- My leads rows show only time, booking ID, customer name and status; everything else is on the lead
  screen.
- Required fields show the red * right after the label text.
- No "camera only" or similar hints on fields; the Gallery button is simply absent when the Admin
  allows only the camera.
- Every banner can be closed with an X, except the offline strip (a status line that disappears by
  itself when signal returns).
- Scan is offered only on text fields where the Admin switched it on (agreed).
- Ops Today uses the "grouped by expert" layout (variant B) for now; may be revisited later.
- Sign-in: white page, illustration on top, soft rounded fields, Vayu logo mark (a V with two
  wind lines on a red rounded square) instead of a text logo; awaiting approval.
- Ops screens, second pass (less clutter): white page, one summary per screen (Today shows one
  day-progress bar instead of six number cards), plain rows with thin dividers, one main action
  per screen, other actions in the ⋮ menu. A booking opens on its customer and details; Answers,
  Photos, Ratings and payment, Report and History open as rows (no tabs). Bookings is a list with
  Today / Upcoming / All and one Filter button (board view parked).
- Expert screens, same calm style, tuned for filling big forms fast: one-tap answer buttons the
  full width of the screen; choosing a defect opens its photo and note right under the question;
  after each answer the page scrolls to the next unanswered one; per-section counts ("3 of 6");
  Scan icon inside text fields; multi-select as tap chips; the Next button names the next page;
  "1 still needed · Show me" jumps to the gap. Check-in is a big selfie button plus one-tap travel
  choices; GPS and time are recorded silently.
- Choice questions pick their layout automatically from their options (no Admin setting):
  up to 4 options with short labels (about 10 characters) → one row of buttons; 5 to 8
  options, or any longer label → stacked full-width rows that wrap to two lines, defect options
  carry a small severity tag (Minor / Major / Critical); 9 or more options (and master lists)
  → a field that opens a plain scrolling list from the bottom (no search, no "used recently").
  Multi-select follows the same sizes: chips up to 8, a checklist sheet beyond.
- Decided: no "All OK" shortcut. Every field starts blank and the expert answers each one
  (REQUIREMENTS §5.1 stands).

## Notifications

- **Expert pushes:** lead assigned, rescheduled, cancelled or reassigned away, booking details
  changed; plus a **reminder 60 min before each lead** (booking times are India time, whatever zone the phone is in); plus an on-phone alert when **photos have
  not sent for 2 hours**. Every push also triggers a sync.
- **Ops pushes:** Needs-you problems (stuck uploads, two-expert conflict, rejected type change,
  PDF failed, payment mismatch), inspection submitted and completed, booking started and **late start
  (30 min past its time, not started)**, new bookings (shown simply as "New bookings").
  - Every Ops person gets every type by default; **Profile → Notifications** mutes a type
    (problems can't be muted).
- The bell lists the person's recent notifications; tapping one opens the lead or booking, also when
  Android had closed the app in the background.
- Notices are private on the lock screen ("New notice. Unlock to see it."): no customer name or address.
- When Android blocks notices, Profile says so with **Turn on** (the app's notification settings).
- Words: experts read **lead**, Ops **booking**, nobody "job" (docs/plan-leads-bookings-words.md; `WordsTest`
  checks every text). The notification channel is named "Leads and updates" / "Bookings and updates" by role.

## Distribution

- APK download link on the web plus in-app self-update (Android asks the person to confirm).
  Needs "install unknown apps" allowed once per phone. Signing key backed up offline.

## Screens for the clickable prototype

Every screen in light and dark, at phone size, with demo data. Where a layout is undecided, the
prototype shows the variants side by side for a decision.

**Shared:** splash and update-required, sign in (Admin refused message), forced password change,
profile (picture, details, theme, password, notifications for Ops, sign out blocked while
unsynced), notifications list (bell), offline highlight, update available, devices signed out
notice.

**Expert:** My leads (Today / Upcoming / Completed, search), lead detail and Start (call, WhatsApp,
directions, storage check), check-in (GPS, time, selfie), wizard page with every field type,
page list sheet, camera with stamp, photo review / retake, chassis scan and confirm, review and
submit (gaps, pages not opened), submitted / uploading, Uploads tab (per file, storage, clear
local copies), banners (Ops changed old → new, reassigned – submit or discard, cancelled, low
storage, app too old).

**Ops:** Today (number cards + schedule: **variants: agenda by time, grouped by expert, timeline**),
Bookings (views, filters, search, list vs board variants, + New booking), new / edit booking,
booking detail (summary and actions, answers view and edit with "someone else saved" dialog,
media gallery with video and add / replace / delete / ZIP, ratings and Key Checks override,
payments verify and record, report view / regenerate / share, activity, conflict: choose which
inspection counts), assign / reschedule / cancel / force-release sheets, Needs you, Dashboard with
CSV export, notification settings.
