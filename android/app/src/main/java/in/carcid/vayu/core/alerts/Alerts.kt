package `in`.carcid.vayu.core.alerts

import `in`.carcid.vayu.core.draft.Draft
import `in`.carcid.vayu.core.sync.Job
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId

/** A reminder to show later: [at] is when, [title] and [body] what it says. */
data class Reminder(val jobId: String, val at: Instant, val title: String, val body: String)

/** Experts are reminded this long before each job's time. */
val REMIND_BEFORE: Duration = Duration.ofMinutes(60)

/** Photos still on the phone this long after they were taken get an alert. */
val STUCK_AFTER: Duration = Duration.ofHours(2)

/**
 * "In 1 hour: DEMO-8 at 11:00" for each job of mine not started yet whose reminder time is still
 * ahead. Jobs without a time, done or started, or already past, get none.
 */
fun reminders(jobs: List<Job>, now: Instant, zone: ZoneId = `in`.carcid.vayu.core.sync.IST): List<Reminder> =
    jobs.filter { it.assignedToMe && it.stage == "assigned" && it.myDraft == null }.mapNotNull { j ->
        val slot = runCatching { LocalDate.parse(j.date).atTime(LocalTime.parse(j.time)).atZone(zone).toInstant() }.getOrNull()
            ?: return@mapNotNull null
        val at = slot - REMIND_BEFORE
        if (at <= now) null
        else Reminder(j.id, at, "In 1 hour: ${j.bookingId} at ${j.time}",
            listOf(j.customer, j.address.ifBlank { j.city }).filter { it.isNotBlank() }.joinToString(" · "))
    }

/**
 * Jobs whose photos have sat unsent longer than [STUCK_AFTER] (oldest file's time from [takenAt]),
 * as (booking id, booking code).
 */
fun stuck(drafts: List<Draft>, now: Instant, takenAt: (String) -> Instant?): List<Pair<String, String>> =
    drafts.filter { d ->
        d.files.any { f -> !f.sent && takenAt(f.path)?.let { Duration.between(it, now) > STUCK_AFTER } == true }
    }.map { it.bookingId to it.code }
