package `in`.carcid.vayu.core.draft

import `in`.carcid.vayu.core.rules.JsonLogic
import `in`.carcid.vayu.core.writeAtomically
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.longOrNull
import java.io.File
import java.util.UUID

/** A photo, video, file or signature taken for a job, kept on the phone until the server has it. */
data class LocalFile(
    /** Also the upload's client_uuid, so a retried upload is the same upload. */
    val id: String,
    val part: String, val field: String, val kind: String,
    val path: String, val contentType: String, val source: String,
    val size: Long, val sha256: String,
    /** "Door photo 2": what the Uploads tab calls it. */
    val label: String,
    /** The server's id once registered (answers sent to the server use it). */
    val serverId: String? = null,
    /** Every byte arrived on the server. */
    val sent: Boolean = false,
    val progress: Float = 0f,
    val error: String? = null,
    /** The server checked the bytes: only now may the phone's copy go. */
    val verified: Boolean = false,
    /** The server will not take this file ([error] says why): the answers go without it; the expert removes it. */
    val refused: Boolean = false,
)

/**
 * One job's inspection on this phone: answers by part, pages opened, files, and what still has to
 * reach the server (the start, the submit). Saved on every change (NF1).
 */
data class Draft(
    val bookingId: String, val code: String, val customer: String,
    /** Form versions pinned when the expert started (kept even if Ops changes the job's form). */
    val versions: Map<String, Int?>,
    val inspectionType: String,
    val answers: Map<String, Map<String, Any?>> = emptyMap(),
    val visited: List<String> = emptyList(),
    val step: Int = 0,
    val startUuid: String = UUID.randomUUID().toString(),
    /** Server time (corrected phone clock) when the check-in was complete; null until then. */
    val startedAt: String? = null,
    val startSent: Boolean = false,
    val submitUuid: String = UUID.randomUUID().toString(),
    /** Set when the expert taps Submit: answers are locked from then on. */
    val submittedAt: String? = null,
    val submitSent: Boolean = false,
    val files: List<LocalFile> = emptyList(),
    /** Last refusal from the server, in words (shown on the job). */
    val problem: String? = null,
    val problemCode: String? = null,
    /** The phone's clock was never checked against the server when this was stamped. */
    val unverifiedTime: Boolean = false,
    /** Answers the server refused, by field key (its code), until the expert changes them. */
    val fieldErrors: Map<String, String> = emptyMap(),
    /** Server files to take back (deleted or retaken after they were sent). */
    val discards: List<String> = emptyList(),
    /** Fetch the files the server already holds for this job (it was started before, elsewhere). */
    val reconcile: Boolean = false,
    /** The booking's own answers as they were on the lead list: visibility rules on booking.* still
     *  work once the lead has left the list (N-6). */
    val bookingAnswers: Map<String, Any?> = emptyMap(),
    /** When the server said it already had this work (the 7-day keep counts from then, N-10). */
    val problemAt: String? = null,
) {
    val locked: Boolean get() = submittedAt != null
    /** Something still has to reach the server (a file it refused for good never will). */
    val unsent: Boolean get() = !submitSent || files.any { !it.verified && !it.refused } || discards.isNotEmpty() || reconcile

    fun answer(part: String, key: String): Any? = answers[part]?.get(key)
    fun withAnswer(part: String, key: String, v: Any?): Draft =
        copy(answers = answers + (part to (answers[part].orEmpty() + (key to v))), fieldErrors = fieldErrors - key)

    fun toJson(): JsonObject = JsonLogic.toJson(mapOf(
        "booking" to bookingId, "code" to code, "customer" to customer, "versions" to versions,
        "inspection_type" to inspectionType, "answers" to answers, "visited" to visited, "step" to step,
        "start_uuid" to startUuid, "started_at" to startedAt, "start_sent" to startSent,
        "submit_uuid" to submitUuid, "submitted_at" to submittedAt, "submit_sent" to submitSent,
        "problem" to problem, "problem_code" to problemCode, "unverified_time" to unverifiedTime,
        "field_errors" to fieldErrors, "discards" to discards, "reconcile" to reconcile, "booking_answers" to bookingAnswers,
        "problem_at" to problemAt,
        "files" to files.map { f -> mapOf("id" to f.id, "part" to f.part, "field" to f.field, "kind" to f.kind,
            "path" to f.path, "content_type" to f.contentType, "source" to f.source, "size" to f.size,
            "sha256" to f.sha256, "label" to f.label, "server_id" to f.serverId, "sent" to f.sent,
            "progress" to f.progress.toDouble(), "error" to f.error, "verified" to f.verified, "refused" to f.refused) },
    )) as JsonObject

    companion object {
        @Suppress("UNCHECKED_CAST")
        fun fromJson(o: JsonObject): Draft {
            fun s(k: String) = (o[k] as? JsonPrimitive)?.contentOrNull
            fun b(k: String) = (o[k] as? JsonPrimitive)?.booleanOrNull ?: false
            return Draft(
                bookingId = s("booking")!!, code = s("code").orEmpty(), customer = s("customer").orEmpty(),
                versions = (o["versions"] as? JsonObject).orEmpty().mapValues { (it.value as? JsonPrimitive)?.intOrNull },
                inspectionType = s("inspection_type").orEmpty(),
                answers = (JsonLogic.fromJson(o["answers"]) as? Map<String, Map<String, Any?>>).orEmpty(),
                visited = (o["visited"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.contentOrNull },
                step = (o["step"] as? JsonPrimitive)?.intOrNull ?: 0,
                startUuid = s("start_uuid")!!, startedAt = s("started_at"), startSent = b("start_sent"),
                submitUuid = s("submit_uuid")!!, submittedAt = s("submitted_at"), submitSent = b("submit_sent"),
                problem = s("problem"), problemCode = s("problem_code"), unverifiedTime = b("unverified_time"),
                fieldErrors = (o["field_errors"] as? JsonObject).orEmpty().mapValues { (it.value as? JsonPrimitive)?.contentOrNull ?: "" },
                discards = (o["discards"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.contentOrNull },
                reconcile = b("reconcile"),
                bookingAnswers = (JsonLogic.fromJson(o["booking_answers"]) as? Map<String, Any?>).orEmpty(),
                problemAt = s("problem_at"),
                files = (o["files"] as? JsonArray).orEmpty().map { it.jsonObject }.map { f ->
                    fun fs(k: String) = (f[k] as? JsonPrimitive)?.contentOrNull
                    LocalFile(fs("id")!!, fs("part")!!, fs("field")!!, fs("kind")!!, fs("path")!!, fs("content_type")!!,
                        fs("source") ?: "camera", (f["size"] as? JsonPrimitive)?.longOrNull ?: 0L, fs("sha256").orEmpty(),
                        fs("label").orEmpty(), fs("server_id"), (f["sent"] as? JsonPrimitive)?.booleanOrNull ?: false,
                        fs("progress")?.toFloatOrNull() ?: 0f, fs("error"),
                        (f["verified"] as? JsonPrimitive)?.booleanOrNull ?: false, (f["refused"] as? JsonPrimitive)?.booleanOrNull ?: false)
                },
            )
        }
    }
}

/**
 * Drafts on this phone: one file per job in [dir], and the job's photos and files under [dir]/files.
 * A change is in memory at once (the screen and the outbox read it from there) and is written to
 * storage by [writer] (in the app, a thread of its own, so typing never waits on the disk); a crash
 * or power cut leaves the last whole save. Nothing here is deleted until the server has it, except
 * when the expert discards a draft.
 */
class DraftStore(private val dir: File,
                 private val writer: java.util.concurrent.Executor = java.util.concurrent.Executor { it.run() },
                 /** A draft file that can't be read (kept on the phone, never silently dropped). */
                 private val onDamaged: (File, Throwable) -> Unit = { _, _ -> }) {
    val filesDir: File get() = File(dir, "files").apply { mkdirs() }
    private val cache = HashMap<String, Draft>()
    /** Saves not written yet, by booking: only the newest is written. */
    private val pending = HashMap<String, Draft>()
    /** Held while a file is written or deleted, so a discard never races a late write. */
    private val disk = Any()
    private val damaged = HashSet<String>()
    /** Bumped on every change, so screens redraw when the outbox moves things along. */
    val changes = kotlinx.coroutines.flow.MutableStateFlow(0L)
    /** The last save could not be written (the phone is full); the answers are kept in memory. */
    val writeFailed = kotlinx.coroutines.flow.MutableStateFlow(false)

    private fun fileOf(bookingId: String): File {
        require(bookingId.matches(Regex("[0-9a-fA-F-]{36}"))) { "Not a booking id." }
        return File(dir, "$bookingId.json")
    }

    @Synchronized
    fun get(bookingId: String): Draft? = cache[bookingId] ?: fileOf(bookingId).takeIf { it.exists() }?.let { f ->
        runCatching { Draft.fromJson(Json.parseToJsonElement(f.readText()).jsonObject) }
            .onFailure { if (damaged.add(f.name)) onDamaged(f, it) }.getOrNull()
    }?.also { cache[bookingId] = it }

    @Synchronized
    fun all(): List<Draft> = ((dir.listFiles { f -> f.name.endsWith(".json") }.orEmpty().map { it.name.removeSuffix(".json") }) + cache.keys)
        .distinct().mapNotNull { get(it) }

    /** Draft files on the phone that can't be read (booking ids): never counted as sent, never deleted unseen. */
    @Synchronized
    fun unreadable(): List<String> = dir.listFiles { f -> f.name.endsWith(".json") }.orEmpty()
        .map { it.name.removeSuffix(".json") }.filter { it !in cache && get(it) == null } +
        setAside().map { it.name.removeSuffix(DAMAGED) }

    private fun setAside(): List<File> = dir.listFiles { f -> f.name.endsWith(DAMAGED) }.orEmpty().toList()

    /**
     * Before a new draft is started for a lead whose draft file can't be read: move the damaged one
     * aside (kept for Ops, never overwritten, N-4). It still counts as unreadable, so sign-out stops
     * and nothing is swept.
     */
    @Synchronized
    fun setAsideDamaged(bookingId: String) {
        val f = fileOf(bookingId)
        if (f.exists() && get(bookingId) == null) f.renameTo(File(dir, bookingId + DAMAGED))
    }

    /** Kept in memory and queued for writing; the newest save of a draft is always the one written. */
    fun save(d: Draft): Draft { stage(d); flushLater(d.bookingId); return d }

    @Synchronized
    private fun stage(d: Draft) {
        fileOf(d.bookingId)
        cache[d.bookingId] = d
        pending[d.bookingId] = d
        changes.value++
    }

    private fun flushLater(bookingId: String) = writer.execute {
        synchronized(disk) {
            val d = synchronized(this) { pending.remove(bookingId) } ?: return@execute
            try {
                writeAtomically(fileOf(bookingId), d.toJson().toString().toByteArray())
                writeFailed.value = false
            } catch (e: Exception) {
                writeFailed.value = true                 // disk full: kept in memory, written by the next save
            }
        }
    }

    /** Change one draft under the lock (so the outbox and the screen never overwrite each other). */
    fun update(bookingId: String, change: (Draft) -> Draft): Draft? =
        synchronized(this) { get(bookingId)?.let(change)?.also(::stage) }?.also { flushLater(bookingId) }

    /** Discard: the answers and every file of this job (also ones not sent). */
    fun discard(bookingId: String) = synchronized(disk) {
        synchronized(this) {
            get(bookingId)?.files?.forEach { if (it.path.isNotEmpty()) File(it.path).delete() }
            pending.remove(bookingId)
            fileOf(bookingId).delete()
            cache.remove(bookingId)
            changes.value++
        }
    }

    /** What the heartbeat and sign-out count: jobs not yet submitted to the server, and files it hasn't checked yet. */
    fun unsentCounts(): Pair<Int, Int> = all().let { d -> d.count { !it.submitSent } to d.sumOf { x -> x.files.count { !it.verified } } }

    /** Copies the phone may drop to free space: only ones the server has checked (never unsent ones). */
    @Synchronized
    fun clearSentCopies(): Long {
        var freed = 0L
        all().forEach { d -> d.files.filter { it.verified && it.path.isNotEmpty() }.forEach { f -> File(f.path).takeIf { it.exists() }?.let { freed += it.length(); it.delete() } } }
        return freed
    }

    fun sentBytes(): Long = all().sumOf { d -> d.files.filter { it.verified && it.path.isNotEmpty() }.sumOf { File(it.path).takeIf { f -> f.exists() }?.length() ?: 0L } }

    /**
     * Files no draft refers to (a shot never confirmed before the app died, leftovers) and
     * half-written saves, once they are an hour old. Nothing is touched while a draft can't be read.
     */
    @Synchronized
    fun sweep(now: Long = System.currentTimeMillis()) {
        val drafts = dir.listFiles { f -> f.name.endsWith(".json") }.orEmpty().map { get(it.name.removeSuffix(".json")) }
        if (drafts.any { it == null } || setAside().isNotEmpty()) return
        val used = all().flatMap { d -> d.files.map { File(it.path).name } }.toSet()
        val old = now - 60 * 60 * 1000
        filesDir.listFiles().orEmpty().filter { it.name !in used && it.lastModified() < old }.forEach { it.delete() }
        dir.listFiles { f -> f.name.endsWith(".tmp") && f.lastModified() < old }.orEmpty().forEach { it.delete() }
    }
}

/** The name ending of a draft file moved aside because it couldn't be read. */
private const val DAMAGED = ".damaged"
