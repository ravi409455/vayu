# Manual test on real hardware — 26 Nov 2026

Code under test: `main` at f4b577e, run from a separate worktree (`/Users/ravi/DevSpace/inspex-test`) with
`scripts/local.sh up` against the kept `vayu_local` database (backed up first to
`backups/vayu_local-before-manual-test-2026-11-26.sql.gz`). Debug app built with
`-Pvayu.apiUrl=http://localhost:8000/api/v1/`, reached over `adb reverse` (8000 API, 9000 files).

Hardware: the owner's phone (model IV2201, Android 13, 1080×2400 at 480 dpi) over adb Wi-Fi; this Mac
with Safari and Chrome; Playwright's WebKit and Firefox; an Android emulator for the small/low-end phone.
Screenshots are in [`manual-test-2026-11/`](manual-test-2026-11/).

Result words: **PASS**, **FAIL** (listed again under *Failures* with an id), **SKIPPED** (with why).

## Summary

**8 checks failed, 11 failures found (F-1 to F-11; F-11 turned up when the WebKit/Firefox suites were re-run);
everything else passed or was skipped by the owner.** All fixed afterwards in one PR (see *Fixes* at the end).

- Web: names and focus order fine; Safari's engine handles photo upload, PDF, filters and tablet width. One real
  Safari/Firefox bug (F-6) breaks navigation while a page is loading and causes almost every WebKit/Firefox e2e failure.
- Phone: survives reboots (drafts and sending), offline/online, battery saver and deep sleep (uploads go on unlock,
  pushes arrive). Fails: cut-off text at the largest font (F-1 to F-4), "server is checking it" lingering (F-5),
  1-hour reminder late in deep sleep (F-8).
- Small 2 GB phone: 31-photo lead, memory and cold start fine.
- Two phones: user swap leaves nothing behind, pushes follow the right person. Fails: a second phone does not show
  a lead's check-in done on the first (F-10); an Ops-finished booking blocks sign-out (F-9).

Everything changed on the phone was put back: TalkBack off, font 1.0× and display 480 dpi, battery saver off, deep
sleep released, screen timeout unchanged (30 min). Vayu on the phone is left signed in as `expert2`
(it was `ops` before). Test bookings MT-1 to MT-12 were added to `vayu_local`.

## 1. Web: accessibility and browsers

| # | Check | Result | Evidence / note |
|---|---|---|---|
| 1.1a | VoiceOver with Safari (sign in, Ops Today, open a booking and assign, Admin builder, Roles, API keys, customer report) | SKIPPED | Owner chose not to listen with VoiceOver. The names and focus order below were checked instead. |
| 1.1b | Accessibility tree and Tab order in WebKit for the same 8 pages | PASS | Every button, link, field and tab on all 8 pages has a name; page titles and one `h1` each; Roles switches are labelled groups ("See the user list (Ops)" → Off/All); the assign dialog takes focus (Expert → Back → Assign an expert) and gives it back. Safari's default Tab skips plain links (a Safari setting), so menu links and the report page's links are reached with VoiceOver keys, not Tab. Walk: [webkit-a11y-walk.txt](manual-test-2026-11/webkit-a11y-walk.txt) |
| 1.2 | Full Playwright suite in WebKit and Firefox (own DB `vayu_e2e_x`, ports 5499/8499) | FAIL | WebKit 19 passed / 52 failed; Firefox 11 passed / 60 failed. Nearly all fail with "page.goto … interrupted by another navigation" (WebKit) / `NS_BINDING_ABORTED` (Firefox): a real app bug, F-6. Firefox also cannot run the 3 camera tests: F-7. To be re-run after the fix. |
| 1.3a | Safari engine: photo upload (expert check-in, MT-4) | PASS | Done in Playwright WebKit (Safari's engine, not the Safari app; owner's choice). "files 1/1 sent". [shot](manual-test-2026-11/wk-photo-upload.jpg) |
| 1.3b | Safari engine: PDF download (Ops, TST-1030 Report tab) | PASS | 1.3 MB file starting `%PDF-`, named `TST-1030PPI.pdf` (from the template's file-name setting). [shot](manual-test-2026-11/wk-report-tab.jpg) |
| 1.3c | Safari engine: Bookings filters | PASS | City + Stage kept after a reload, "Clear filters" empties them. [shot](manual-test-2026-11/wk-filters.jpg) |
| 1.3d | Safari engine: tablet width 768×1024 | PASS | No sideways scrolling on Today, Bookings, a booking, the PDI builder, Roles, API keys, My leads, a lead. [today](manual-test-2026-11/wk-tablet-ops-today.jpg), [booking](manual-test-2026-11/wk-tablet-ops-booking.jpg), [builder](manual-test-2026-11/wk-tablet-admin-forms.jpg), [lead](manual-test-2026-11/wk-tablet-expert-jobs.jpg) |

## 2. Phone

| # | Check | Result | Evidence / note |
|---|---|---|---|
| 2.1a | TalkBack: Ops Today (rows, filters, expand an expert, tab bar) | PASS | Owner listened; every stop read clearly, sensible order. Tree names checked too (`Notifications, 22`, `Test Expert, Next at 11:00 am, expand`, `Status: any`). [ph-ops-today](manual-test-2026-11/ph-ops-today.jpg) |
| 2.1b | TalkBack: expert lead flow | SKIPPED | Owner decided TalkBack on the expert flow is not needed. Tree names checked only: close = "Close and keep the draft", page button = "Page 1 of 23, open the page list", required star = "required", photo tile = "Take a photo". |
| 2.2 | Largest font (1.3×) and largest display size (620 dpi): nothing cut off | FAIL | F-1 to F-4 below. Restored to 1.0× / 480 dpi after. [check-in](manual-test-2026-11/ph-big-checkin-2.jpg), [lead](manual-test-2026-11/ph-big-detail.jpg), [leads](manual-test-2026-11/ph-big-leads.jpg), [profile](manual-test-2026-11/ph-big-profile.jpg); fine: [pages](manual-test-2026-11/ph-big-pagelist.jpg), [uploads](manual-test-2026-11/ph-big-uploads.jpg), [bell](manual-test-2026-11/ph-big-bell.jpg) |
| 2.3 | Reboot in the middle of a draft (MT-2: check-in photo, chassis, registration, odometer typed) | PASS | After the restart the draft opened with the photo (sent) and all three values. [before](manual-test-2026-11/ph-draft-before-reboot.jpg), [after](manual-test-2026-11/ph-draft-after-reboot.jpg), [after, page 2](manual-test-2026-11/ph-draft-after-reboot-car.jpg) |
| 2.4 | Reboot while files are sending after submit | PASS, with F-5 | MT-2 submitted with the engine video unsent (route to file storage cut on purpose). Phone restarted 08:17; the app's background job came back by itself and, with Vayu never opened, sent the video at 08:26:13 (it waited out the retry pause it had built up before the restart); MT-2 became Completed. But the phone then kept saying "Sent · the server is checking it" for ~16 more minutes: see F-5. [submitted](manual-test-2026-11/ph-submitted-pending.jpg), [stuck on checking](manual-test-2026-11/ph-checking-stuck.jpg) |
| 2.5 | Battery saver on + `dumpsys deviceidle force-idle`, screen locked: uploads, 1-hour reminder, pushes | PASS for uploads and pushes; FAIL for the reminder (F-8) | MT-3 submitted 08:33 with its 5 photos held back; then cable out, screen locked, battery saver on, deep sleep forced, route to files restored. **Uploads:** held the whole time the phone was asleep (Android gives the app no network then, even in a forced maintenance window at 08:53), and all 5 went in 2 s when the owner unlocked at 08:58:38; MT-3 Completed. (Vayu was the app on screen when the phone was locked, so it was in front again after the unlock.) **Pushes:** with the phone in deep sleep and battery saver on, assigning MT-6 at 08:45:45 put "New lead" on the phone 2 s later and refreshed the lead list in the background; the owner saw it on the lock screen. (An earlier round at 08:34–08:36 showed nothing because the USB cable coming out had dropped the test link to the API, not because of the app: re-run after restoring the link.) **Reminder:** MT-4's 08:42 reminder showed only at 08:44:22, when a maintenance window was forced: F-8. Battery saver turned off again after. |
| 2.6 | Offline, then online: the lead sends | PASS | Done on the emulator (airplane mode on the real phone would also cut the wireless test link): Wi-Fi and data off and the API route removed, then MT-8 started, filled (4 photos) and submitted with no network: "Answers locked; sending when there is signal". App sent to the background, network back at 09:10:52: answers and all 4 files on the server by 09:10:54; MT-8 Completed. [offline review](manual-test-2026-11/emu-offline-review.jpg), [submitted offline](manual-test-2026-11/emu-offline-submitted.jpg) |

## 3. Emulator as a small, low-end phone

AVD `vayu_small`: Nexus 4 profile (4.7 inch, 768×1280, 320 dpi), 2 GB RAM, Android 15 Google APIs image, 4 GB data disk
(the Mac had only 12 GB free). An emulator on this Mac has a fast CPU, so this checks memory and the small screen, not a slow processor.

| # | Check | Result | Evidence / note |
|---|---|---|---|
| 3.1 | 4.7-inch 2 GB phone: sign in, leads, a lead, the wizard, page list | PASS | Everything fits and works. On the small screen the "N still needed · Show me" line plus the Back/Next bar take about a third of the height, and "Show me" can park the needed field just under that line (you scroll a little to reach the camera tile). Usable; not counted as a failure. [leads](manual-test-2026-11/emu-leads.jpg) |
| 3.2 | A lead with 30+ photos (PDI MT-9) | PASS | 31 photos taken on 13 pages of the PDI; all 31 on the server and checked (`verified`). App memory (PSS) stayed 176–226 MB, phone kept 1.26 GB free; scrolling a 31-photo page: 168 frames, 1 janky (0.6 %), 95th percentile 27 ms. [shot](manual-test-2026-11/emu-30-photos.jpg) |
| 3.3 | Cold start time | PASS | `am start -W` after `force-stop`, 5 runs each: signed out 1.28–2.62 s; signed in with the 31-photo draft 0.63–1.65 s. |

## 4. Two phones

Phone 1 = the owner's phone, phone 2 = the emulator. Expert A = `expert`, Expert B = `expert2`.

| # | Check | Result | Evidence / note |
|---|---|---|---|
| 4.1 | A signs out of phone 1, B signs in on phone 1: B sees none of A's drafts or photos | PASS | After A's sign-out the app's storage held no draft, photo, notice or sign-in of A (`run-as` listing: only Firebase/WorkManager files and cached form pictures; `vayu.auth` empty; no Vayu notices). B's leads show only B's MT-9, Uploads "Everything is sent.", bell shows B's notices only. [B's leads](manual-test-2026-11/ph-b-leads.jpg), [B's uploads](manual-test-2026-11/ph-b-uploads.jpg) |
| 4.1b | (found on the way) B signing in on phone 1 while B's other phone still held an unsent draft | PASS | Refused with "Your other phone still has work that hasn't been sent. Open the app there and let it sync, or ask an Admin to sign that phone out." (HTTP 409). Worked after the draft on phone 2 was discarded and phone 2 had reported in. [shot](manual-test-2026-11/ph-b-signin-409.jpg) |
| 4.2 | A carries on from phone 2 | FAIL (F-10) | A dropped MT-1's draft on phone 1 after its check-in reached the server (answer "No", plate photo, place, time), signed in on the emulator and opened MT-1: the check-in was empty ("1 of 4", photo "0 of 1"). Only after A took a new plate photo did the old one appear, as "2 of 1" with the new one blocked. [empty check-in](manual-test-2026-11/emu-a-continues-mt1.jpg), [after a new photo](manual-test-2026-11/emu-a-mt1-from-before.jpg) |
| 4.3 | Signing out with unsent files warns or blocks, and never loses them | PASS | With MT-1 (draft) and MT-10 (submitted, 2 photos held back) on the phone: "Not sent yet: MT-1, MT-10. Open Uploads to send, finish or discard them, then sign out." Nothing was deleted; MT-10's photos were sent later. [shot](manual-test-2026-11/ph-signout-blocked.jpg) |
| 4.4 | Live pushes for assign, reschedule, cancel with the app closed (process killed) and the screen locked | PASS | Phone 1 (B): "New lead: MT-12", "MT-12 moved · 2:30 pm → 3:30 pm", "MT-12 cancelled · Customer cancelled", all on the phone within seconds while Vayu was not running and the screen was off. Phone 2 (A, also closed and locked): "New lead: MT-11". |
| 4.5 | After the user swap the old user's pushes do not reach the new user | PASS | MT-11 (A's) and A's notices about MT-12 went only to phone 2; phone 1 (now B) got none of them. |
| 4.6 | Ops "finish without the missing files": the phone's files, and sign-out | FAIL (F-9) | Ops pressed it on the web for MT-10 (2 optional front photos still on the phone): MT-10 Completed, history line "Finished by Test Ops without 2 files: Front photos". [web](manual-test-2026-11/web-ops-finish-after.jpg). The phone kept the 2 photos as "Waiting" and kept sending them; once the route was back they arrived and were added (3 of 3 verified), as agreed on 24 Nov. But until then sign-out stayed blocked by MT-10. The owner decided (26 Nov): keep sending and adding them, but a booking Ops has finished must not block sign-out; any other unsent work still blocks. [phone](manual-test-2026-11/ph-mt10-waiting-after-finish.jpg) |

## Failures

| Id | Where | What is wrong |
|---|---|---|
| F-1 | Android wizard, photo field label | At the largest font the "0 of 1" count beside a photo field's label is squeezed into a column one letter wide (`0`/`o`/`f`/`1` stacked) and the red required star sits on top of it. |
| F-2 | Android lead page (Call / WhatsApp / Directions) | At the largest font the button words break mid-word: "WhatsAp / p", "Direction / s". |
| F-3 | Android My leads | At the largest font the customer name is cut to 4–5 letters ("Preeti…", "Qasi…", "Same…") because the status stays full width; the tabs read "Today…", "Upco…", "Comp…". |
| F-4 | Android profile, theme switch | At the largest font "Match phone" shows as "Match…". |
| F-5 | Android uploads: "the server is checking it" | The server checked the video 0.6 s after it arrived (`verify_asset … 'verified'` at 08:26:13), but the phone asked at the same instant, got "still checking", and its next question waits on the same growing retry pause the earlier failed sends built up (15 minutes here; it grows to hours after more failures). Meanwhile the lead stays in Uploads as "1 file to send" and sign-out is blocked. Tapping Refresh does not help: it reloads leads but never asks about the files. |
| F-6 | Web, Safari and Firefox: leaving a page while its code is loading | When the browser leaves a page while a page's code file is still loading, Safari (WebKit) and Firefox cancel that load. `lazyPage` (`web/src/ui/ErrorBoundary.tsx`) takes the cancel for "the app was updated, its files are gone" and calls `location.reload()`, which reloads the old page and throws away where the person was going (a typed address, a bookmark, a download link, a sign-in redirect). Chrome does not cancel the load, so it never shows there. Seen with a WebKit probe: `goto /users` right after sign-in → a second navigation request to `/forms` 2 ms later → "Navigation to /users is interrupted by another navigation to /forms". This one bug causes almost every WebKit and Firefox e2e failure (52 of 52 WebKit, 56 of 60 Firefox start with that error). |
| F-7 | e2e on Firefox | `camera.spec.ts` asks Playwright for the `camera` permission, which Firefox does not know (`browser.newContext: Unknown permission: camera`), so the three camera tests cannot run on Firefox at all. |
| F-8 | Android 1-hour reminder in deep sleep | The "In 1 hour" reminder is a WorkManager job with a delay, and Android holds such jobs while the phone is in deep sleep. MT-4's reminder was due 08:42:00; with the phone locked, battery saver on and in deep sleep it did not show until I forced a maintenance window at 08:44:22. Left alone, deep sleep's windows come about an hour apart and further apart after that, so the reminder can arrive after the job has started. A reminder needs an alarm that may fire in deep sleep (`AlarmManager.setAndAllowWhileIdle`). |
| F-9 | Android sign-out after Ops finished a booking | Files of a booking Ops already finished "without the missing files" still block sign-out until they are sent. Owner's rule (26 Nov): keep sending them (they are added to the report when they arrive), but they do not block sign-out; unsent work of any other booking still blocks. |
| F-10 | Android: carrying on a lead on a second phone | A new phone opens a lead started on another phone with an empty check-in, although the server has its answers and photo (`inspection.answers.start`: selfie, place, time, "no"). The photo from before shows only when the expert takes a new one, and then as "2 of 1" with the new photo refused until one is deleted. The web already shows the sent photo straight away (e2e J3f). |
| F-11 | Web, Safari and Firefox: Admin → Promote → "Download bundle" (and the PDF template export) | Found once F-6 was fixed and the suites were re-run. Safari and Firefox ask for `text/html` when following a download link, and the API answered with its browsable HTML page, which was saved as `pdi-v1.json` (`<title>Promote Export – Django REST framework</title>`). Importing that file then fails. Chrome asks for anything, so it got JSON. |

## Fixes (one PR, after testing)

| Id | Fix | Checked |
|---|---|---|
| F-1 | Photo field label wraps; the star and "0 of 1" keep their width. | Emulator at 1.3× / largest size: [after](manual-test-2026-11/fix-big-checkin.jpg) |
| F-2 | Call / WhatsApp / Directions (expert lead page and Ops booking page): one line that shrinks to fit. | [after](manual-test-2026-11/fix-big-detail.jpg) |
| F-3 | Lead row: the name may take two lines; tabs shrink before they cut. | [after](manual-test-2026-11/fix-big-leads.jpg) |
| F-4 | Same for every switch row (Light / Dark / Match phone). | [after](manual-test-2026-11/fix-big-profile.jpg) |
| F-5 | When everything is on the server and only the server's check is left, the phone asks again in 20 s instead of waiting out the retry pause; Refresh also starts sending. | Emulator: photo held back through 3 failed tries, route back, Refresh → sent in 1 s, checked on the phone 30 s later (was ~16 min). Unit test `onlyCheckingMeansEverythingIsOnTheServer`. |
| F-6 | `lazyPage` doesn't reload when the page is being left (`beforeunload`/`pagehide`). | Unit test; WebKit/Firefox suites (below). |
| F-7 | e2e camera tests: no `camera` permission on Firefox; Firefox's fake camera instead. | Firefox camera tests pass. |
| F-8 | The 1-hour reminder is an `AlarmManager.setAndAllowWhileIdle` alarm (cancelled at sign-out). | Emulator forced into deep sleep: MT-13's 10:09 reminder showed by 10:10:43, still in deep sleep. Unit tests in `NoticesTest`. |
| F-9 | Sign-out skips submitted drafts whose booking is Completed (Ops finished it); they keep sending while signed in. | Flow test `aBookingOpsFinishedDoesNotBlockSignOut`. |
| F-10 | Opening a lead started on another phone fetches the server's files at once. | Emulator: MT-1's draft dropped and reopened → "Your photo with car's number plate (from before), sent", 1 of 1: [after](manual-test-2026-11/fix-f10-reopen.jpg). The check-in's typed answers (e.g. "No") are still not brought back; the web does not bring them back either. |
| F-11 | The bundle and PDF-template exports always answer JSON, and the bundle download is an attachment. | Backend test `test_the_download_is_json_even_when_the_browser_asks_for_html`; WebKit promote e2e passes. |

e2e test changes that are not app bugs (Safari's own rules): the skip-link test presses Option+Tab on WebKit
(Safari's Tab skips links); the dialog test opens it from the keyboard (Safari never focuses a clicked button); three
tests that keep files in IndexedDB are skipped on WebKit because Playwright's WebKit runs like a private window,
where Safari keeps no files there (a normal WebKit profile stores them: checked with a persistent profile); the
dark-mode test sets Dark through the API (Firefox left a rewritten request open).
