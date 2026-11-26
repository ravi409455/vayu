package `in`.carcid.vayu.ui.expert

import `in`.carcid.vayu.core.draft.Draft
import `in`.carcid.vayu.core.draft.DraftStore
import `in`.carcid.vayu.core.draft.LocalFile
import `in`.carcid.vayu.core.forms.Filled
import `in`.carcid.vayu.core.forms.Page
import `in`.carcid.vayu.core.forms.PARTS
import `in`.carcid.vayu.core.sync.Job
import `in`.carcid.vayu.core.sync.JobStore
import java.io.File
import java.security.MessageDigest
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID

/** One screen of the wizard: a page of the check-in, the custom form or the wrap-up, or the review. */
data class Step(val id: String, val title: String, val part: String?, val page: Page?) {
    val isReview: Boolean get() = part == null
}

/** "Now" in the shapes the server stores (2026-11-23, 15:30, 2026-11-23T15:30:00+05:30). */
fun stamp(type: String, at: Instant): String {
    val t = at.atZone(ZoneId.systemDefault())
    return when (type) {
        "date" -> t.toLocalDate().toString()
        "time" -> "%02d:%02d".format(t.hour, t.minute)
        else -> t.toOffsetDateTime().withNano(0).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
    }
}

/**
 * One job's inspection on this phone: the draft, its forms, and every change the expert makes.
 * Each change is written to storage before the screen shows it (NF1).
 */
class InspectionModel(
    private val drafts: DraftStore,
    private val jobs: JobStore,
    val bookingId: String,
    /** Server-corrected time. */
    private val now: () -> Instant,
    /** Ask the outbox to send. */
    private val kick: () -> Unit,
    /** The phone's time is checked right now (synced today, clock not changed since). */
    private val verified: () -> Boolean = { true },
    /** Copies outside the app that survive an uninstall (docs/plan-media-backup.md); null: none. */
    private val backup: `in`.carcid.vayu.core.backup.BackupCopies? = null,
) {
    val draft: Draft get() = drafts.get(bookingId)!!

    companion object {
        /** Open the job's draft, creating it (pinning today's forms) on first Start. */
        fun begin(drafts: DraftStore, job: Job, verified: Boolean, bookingAnswers: Map<String, Any?> = emptyMap()): Draft =
            drafts.also { it.setAsideDamaged(job.id) }.get(job.id)
                ?.let { d -> if (bookingAnswers.isEmpty() || d.bookingAnswers == bookingAnswers) d
                    else drafts.update(job.id) { it.copy(bookingAnswers = bookingAnswers) }!! }
                ?: drafts.save(Draft(
            bookingId = job.id, code = job.bookingId, customer = job.customer, versions = job.versions,
            inspectionType = job.typeKey, unverifiedTime = !verified, bookingAnswers = bookingAnswers,
            // started before (another phone, cleared storage): pick up the files the server holds
            reconcile = job.stage != "assigned"))
    }

    fun filled(d: Draft = draft): Filled? = jobs.filled(bookingId, d.versions, d.answers, now().atZone(ZoneId.systemDefault()).toLocalDate().toString(), d.bookingAnswers)

    fun steps(f: Filled): List<Step> = PARTS.flatMap { part ->
        f.visiblePages(part).map { Step("${part[0]}${it.id}", it.title, part, it) }
    } + Step("review", "Review", null, null)

    /** The check-in is complete: the job may become "in progress" (sent with this time). */
    private fun checkInDone(d: Draft, f: Filled) = f.trees["start"] == null || f.gaps("start").isEmpty()

    private fun commit(change: (Draft) -> Draft): Draft {
        val d = drafts.update(bookingId, change)!!
        if (d.startedAt == null && !d.locked) {
            val f = filled(d)
            if (f != null && checkInDone(d, f)) {
                drafts.update(bookingId) { it.copy(startedAt = stamp("datetime", now()), unverifiedTime = it.unverifiedTime || !verified()) }
                kick()
            }
        }
        return draft
    }

    /** First open: a job without a check-in form starts at once. */
    fun open() { commit { it } }

    fun set(part: String, key: String, value: Any?) {
        if (draft.locked) return
        commit { it.withAnswer(part, key, value) }
    }

    fun go(index: Int, step: Step) {
        commit { d -> d.copy(step = index, visited = if (step.id in d.visited) d.visited else d.visited + step.id) }
    }

    /**
     * Keep a taken photo, video, file or signature and put it in the answer (hashed off the main
     * thread), then its backup copy outside the app, named after [page] and [label].
     */
    suspend fun addFile(part: String, field: String, kind: String, file: File, contentType: String, source: String, label: String, single: Boolean,
                        max: Int = Int.MAX_VALUE, page: String = "") {
        // locked, or the field already holds its most: not kept
        if (draft.locked || (!single && ((draft.answer(part, field) as? List<*>)?.size ?: 0) >= max)) { file.delete(); return }
        val hash = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { sha256(file) }
        val f = LocalFile(UUID.randomUUID().toString(), part, field, kind, file.path, contentType, source, file.length(), hash, label)
        commit { d ->
            val cur = d.answer(part, field)
            val value: Any? = if (single) f.id else ((cur as? List<*>).orEmpty() + f.id)
            val replaced = if (single) d.files.firstOrNull { it.id == cur } else null
            replaced?.path?.takeIf { it.isNotEmpty() && !replaced.sent }?.let { File(it).delete() }
            replaced?.let { backup?.drop(it.id) }
            d.copy(files = d.files.filterNot { single && it.id == cur } + f, discards = d.discards + listOfNotNull(replaced?.serverId))
                .withAnswer(part, field, value)
        }
        kick()
        backup?.let { b -> kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            b.copy(`in`.carcid.vayu.core.backup.BackupCopies.Copy(bookingId, draft.code, f.id, page, label, contentType), file)
        } }
    }

    /** Remove a file; after Submit only one the server refused (the answers went without it). */
    fun removeFile(part: String, field: String, id: String) {
        if (draft.locked && draft.files.none { it.id == id && it.refused }) return
        commit { d ->
            val f = d.files.firstOrNull { it.id == id }
            f?.path?.takeIf { it.isNotEmpty() }?.let { File(it).delete() }
            backup?.drop(id)
            val cur = d.answer(part, field)
            val value: Any? = if (cur is List<*>) cur.filter { it != id } else null
            // a file the server already has is taken back there too, or it keeps its place
            d.copy(files = d.files.filterNot { it.id == id }, discards = d.discards + listOfNotNull(f?.serverId))
                .withAnswer(part, field, value)
        }
        kick()
    }

    /** Lock the answers and queue them for sending. */
    fun submit() {
        commit { it.copy(submittedAt = stamp("datetime", now()), unverifiedTime = it.unverifiedTime || !verified()) }
        kick()
    }

    fun discard() { drafts.discard(bookingId); backup?.dropBooking(bookingId) }
}

fun sha256(file: File): String {
    val md = MessageDigest.getInstance("SHA-256")
    file.inputStream().use { input ->
        val buf = ByteArray(1 shl 16)
        while (true) { val n = input.read(buf); if (n < 0) break; md.update(buf, 0, n) }
    }
    return md.digest().joinToString("") { "%02x".format(it) }
}

/** The time a draft-stamped value shows: "3:28 pm" for today's datetimes. */
fun shortTime(iso: String): String = runCatching {
    val t = OffsetDateTime.parse(iso).atZoneSameInstant(ZoneId.systemDefault())
    time12("%02d:%02d".format(t.hour, t.minute))
}.getOrDefault(iso)
