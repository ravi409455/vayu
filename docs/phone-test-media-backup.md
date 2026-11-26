# Phone test: photos and work survive sign-out and uninstall (PR #25)

What `docs/plan-media-backup.md` needs checked on a real phone before PR #25 may be merged.
Each step says what to do and what you should see. Mark ✅ / ❌ and note anything odd.

**Setup**
- The debug app from branch `feat/media-backup` on the phone, talking to this branch's server.
- Two expert logins (e.g. `expert` Ravi and `expert2`), the Ops web open as `ops`, and the Admin web
  as `admin`. Password `Vayu-local-1` (local only).
- Ravi has at least two leads assigned for today (e.g. TST-1015, TST-1016).

## A. First sign-in: file access
| # | Do | You should see |
|---|---|---|
| A1 | Sign in as Ravi (expert) on the fresh install | "Turn on file access" screen, nothing else; no way past it |
| A2 | Tap **Open settings** | Android's "All files access" page **for Vayu** (if it opens the list of all apps, note the phone make) |
| A3 | Turn the switch on, press Back | My leads opens |
| A4 | Sign in as Ops on a fresh install | No file-access screen |

## B. Backup copies while inspecting
| # | Do | You should see |
|---|---|---|
| B1 | Start TST-1015, take 2 photos on a page (e.g. Exterior) | Photos show as usual |
| B2 | Files app → Documents → Vayu → TST-1015 | `Exterior - <field> 1.jpg`, `… 2.jpg` (same photos, with the stamp) |
| B3 | Open the phone's Gallery / Google Photos | **No** Vayu folder or these photos |
| B4 | Pick a PDF into a document field | `…/TST-1015/<page> - <field> 1.pdf` opens as a PDF |
| B5 | Take a video and a signature | `.mp4` and `.png` copies appear |
| B6 | Delete one photo in the app | Its copy is gone from the folder |
| B7 | Settings → turn **off** All files access for Vayu, come back to the inspection | Red line "Backups are off…" with **Turn on**; camera still works; new photo has **no** copy |
| B8 | Tap **Turn on**, switch on, come back | Red line gone; the next photo gets a copy |

## C. Sign-out keeps unsent work
| # | Do | You should see |
|---|---|---|
| C1 | Airplane mode on. Take 2 more photos on TST-1015 | Uploads shows them waiting |
| C2 | Profile → **Sign out** | Sheet "Sign out with unsent work?" naming TST-1015 |
| C3 | **Stay signed in** | Sheet closes, still on Profile, still signed in |
| C4 | **Sign out** → **Sign out** | Sign-in screen |
| C5 | Airplane mode off. Ops web: Users → Ravi → Deactivate (don't confirm) | Warning says "Their phone signed out but still holds …"; cancel |
| C6 | Try Ravi on another phone or the emulator (if you have one) | Refused: "Your other phone still has work…" |
| C7 | Sign in as Ravi again on this phone | My leads; TST-1015 still in progress; Uploads sends the waiting photos; Ops web shows them |

## D. Another person on the same phone
| # | Do | You should see |
|---|---|---|
| D1 | Airplane on, take a photo on TST-1016 as Ravi, sign out (confirm) | Sign-in screen |
| D2 | Airplane off, sign in as `expert2` | Their own leads only; nothing of TST-1016 anywhere |
| D3 | Sign out expert2, sign in as Ravi | TST-1016 photo is there and sends |

## E. Uninstall and reinstall
| # | Do | You should see |
|---|---|---|
| E1 | Airplane on, take 2 photos on a lead, **don't** sign out, uninstall Vayu | — |
| E2 | Files app → Documents → Vayu → that lead | The photos are still there |
| E3 | Share them to yourself on WhatsApp from the Files app | They send |
| E4 | Reinstall, airplane off, sign in as Ravi | Refused (the server still thinks the old install holds work) |
| E5 | Admin web: Users → Ravi → Sign out devices; sign in again | Signed in; "Turn on file access" screen again |
| E6 | Turn it on | My leads shows "Found copies from your earlier install: <lead>" with the delete date 2 days later |
| E7 | Ops web: open that booking, add the shared photos by hand | They are added |
| E8 | On the notice tap **Sent to Ops, delete now** → **Cancel**, then again → **Delete** | Cancel changes nothing; Delete removes the folder's found copies and the notice |

## F. Clean-up (2 days)
Change the phone's date (Settings → System → Date & time, automatic off), then open the app.
| # | Do | You should see |
|---|---|---|
| F1 | +1 day | Copies of sent photos still there; found copies still there |
| F2 | +2 days | Copies of sent photos gone; found copies gone and the notice with them; copies of anything **unsent** still there |
| F3 | Discard a lead that has photos | Its folder is gone at once |
| F4 | Set the date back to automatic | — |

## G. Phone full (optional)
Fill the phone until under ~250 MB free, take a photo: the inspection shows "Phone is full. New
photos have no backup copy." with **Free space**; the photo itself is still kept and sent.

## Results: first run (2026-11-26, iQOO IV2201, Android 13, run over adb)
| Step | Result |
|---|---|
| A1 file-access screen after sign-in | ✅ |
| A2 Open settings → Vayu's own All files access page | ✅ (iQOO opens the per-app page) |
| A3 switch on → My leads | ✅ |
| A4 Ops: no file-access screen | not run (Ops never routes there; covered by code: experts only) |
| B1/B2 copies named `<page> - <field> <n>` in `Documents/Vayu/<code>/` | ✅ (`Check-in - …jpg`, `Photos and more - Front photos 1/2.jpg`) |
| B3 not in the Gallery | ✅ (no image rows for `Documents/Vayu` in the media index; `.nomedia` present) |
| B4 picked PDF | ✅ `Documents 1.pdf` (was `.file` before a fix in this PR) |
| B5 video / signature | ✅ video `.mp4`; signature not on this form (automated test only) |
| B6 photo deleted in app → copy gone | ✅ |
| B7 access off → red line, camera works, no copy | ✅ (with the Settings switch; turning it off with `adb appops` does not change what Android reports) |
| B8 Turn on → next photo copied | ✅ |
| C2 sheet names the unsent leads | ✅ (TST-1014, TST-1018) |
| C3 Stay signed in | ✅ |
| C4 sign out keeps drafts and files in the app | ✅ (this run reached the server; the no-signal path is the automated test) |
| C5 server: signed out, holding 2 drafts / 1 file | ✅ (`phone_state`); Users page words: unit test |
| C6 another install refused | ✅ `DEVICE_HAS_UNSYNCED_DATA` |
| C7 same install signs back in, old device released, odometer photo verified | ✅ |
| D1–D3 second expert on the phone sees nothing; Ravi's work back after | ✅ |
| E1/E2 uninstall without sign-out: 7 copies + `.nomedia` stay | ✅ |
| E3 share on WhatsApp from the Files app | ✅ (owner, 2026-11-26) |
| E4 reinstall refused while the old install holds work | ✅ |
| E5 Admin sign-out devices → sign in → file-access screen again | ✅ |
| E6 Found copies notice (TST-1018, 7 files, deleted 28 Nov) | ❌ then ✅: it showed only after an app restart; fixed in this PR (looks again when access is turned on), re-tested ✅ |
| E7 Ops adds the shared files on the web | ✅ (owner, on TST-1028: added by ops, verified). Ops can add files only once the expert has **submitted** (existing rule): after an uninstall before submit, the booking must be submitted or reassigned first |
| F2 date +2 days: found copies deleted, folder and notice gone | ✅ |
| F1, F3 (+1 day keeps; discard removes at once), copies of sent/unsent files over days | automated tests only |
| G phone full | not run (automated test only) |
| E8 (second run) offline photo on TST-1015 → sign out with unsent work → **uninstall from the phone's own app-info screen** | ✅ server: signed out holding 1 draft / 1 file; copy and `.nomedia` stay; the phone's dialog has no "keep data" option (as designed) |
| E9 reinstall refused → Admin sign-out → file access → "Found copies: TST-1015, 1 file" | ✅ (fixed the one-file wording: "Send it to Ops") |
| E8 "Sent to Ops, delete now" → Cancel keeps all; → Delete | ✅ Cancel (me), Delete (owner): folder empty, index empty, notice gone |
| Unexplained loss | Once (between 16:46 and 21:45) the TST-1015 found copy disappeared with nobody pressing Delete. Retest over USB and Wi-Fi: normal use plus a 30-minute watch, the app never deleted it. Likely outside the app (another tool on this Mac kept resetting the phone connection; Files by Google was open). Watch for it in the staging trial |
Phone left with: Vayu debug (talks to this branch's server on port 8001), All files access on,
date automatic, test PDF removed.
