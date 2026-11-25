# Ops guide

For the team that runs the day: bookings, experts, reviews and reports. Works on the web (and, for
the main tasks, the Android app). Stage words everywhere: **Unassigned · Assigned · In progress ·
Uploading · Completed · Cancelled**.

## Your day: Today

**Today** is the home page: the day's numbers ("11 of 26 completed", in progress, assigned,
unassigned), the schedule by expert with a line for now, and filters for status and experts.
**Needs you** (left menu) lists what waits for a person:

- **Conflict** — two experts submitted the same booking: choose the inspection that counts.
- **Photos stuck** — a file has not finished uploading for hours (checked every hour).
- **Started late / Too quick** — a start long after the booked time, or a submit sooner than the
  type's minimum time. Open the booking, look, press **Mark reviewed**.
- A type change the expert's phone refused, a PDF that failed, a report that is out of date, and
  times the phone could not check.

## Bookings

**New booking** — Bookings → New booking: fill the booking form (Booking ID, customer, car, city,
date and time, inspection type). The Booking ID must be new (case does not matter).

**Find one** — the search box finds a Booking ID, a customer name, the last 4+ digits of a phone
number, a chassis number or a car. Tabs: Today, Unassigned, In progress, Uploading, Upcoming,
Completed, Started late, Too quick, All; plus filters (city, expert, type, stage, dates, and any
answer: "Payment mode = Pay later", "not filled"). Switch between **List** and **Board**.

**Assign an expert** — the **Assign expert** button in the row, or on the booking. Assigning again
reassigns. A booking the expert has started cannot be reassigned until you **Force release** it
(the expert's unsent draft is then lost; if it still arrives, it shows as a conflict).

**Reschedule** — choose the new date and time and a reason; the old slots stay in the history.
**Cancel booking** — needs a reason ("On arrival" is one). **Change type** — only before the expert
starts.

If someone saved the booking after you opened it, your save stops and says who changed what; reload
and save again (only your own changes are applied).

## Reviewing an inspection

Open the booking. Tabs: **Booking**, **Inspection**, **Media**, **Review**, **Report**.

- **Inspection** — every answer the expert gave, with filters (Defects, Edited by Ops, Not answered).
  You can edit answers after submit; the expert is not told.
- **Media** — photos and videos full size, replace, add or remove a file, and **Download all photos
  / videos** (a ZIP).
- **Review** — the suggested **Ratings** and **Key Checks**. Change any of them; what you set stays,
  even when answers change later.
- **Report** — the PDF (see below).

**Two experts submitted this booking** — the Review shows both; pick the **Inspection to keep**.
Nothing completes and no report is made until you do.

## Reports (PDF)

The PDF is made once, by itself, when the booking completes (all files checked). After that,
changes only mark it **Out of date**: press **Regenerate** when you are done editing (one new PDF;
only the newest is kept). Report words: Ready · Updating… · Out of date · Failed. A completed booking
whose PDF never came shows **No report yet** with **Make the PDF**, and is listed in Needs you. If Regenerate is
off, the page says why (for example during a conflict, or after old photos were removed by the
retention setting).

## Dashboard

**Dashboard**: bookings by day, week or month, split by type, city, expert or lead owner, plus
started-late and too-quick counts. **Export CSV** downloads the numbers.

## Experts' phones

A person has one phone signed in at a time. If a phone is lost, an Admin (or Ops, if allowed) signs
it out; anything not yet sent from that phone is lost.
