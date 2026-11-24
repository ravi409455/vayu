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
    /** Every byte arrived and the server checked it. */
    val sent: Boolean = false,
    val progress: Float = 0f,
    val error: String? = null,
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
) {
    val locked: Boolean get() = submittedAt != null
    /** Something still has to reach the server. */
    val unsent: Boolean get() = !submitSent || files.any { !it.sent } || discards.isNotEmpty() || reconcile

    fun answer(part: String, key: String): Any? = answers[part]?.get(key)
    fun withAnswer(part: String, key: String, v: Any?): Draft =
        copy(answers = answers + (part to (answers[part].orEmpty() + (key to v))), fieldErrors = fieldErrors - key)

    fun toJson(): JsonObject = JsonLogic.toJson(mapOf(
        "booking" to bookingId, "code" to code, "customer" to customer, "versions" to versions,
        "inspection_type" to inspectionType, "answers" to answers, "visited" to visited, "step" to step,
        "start_uuid" to startUuid, "started_at" to startedAt, "start_sent" to startSent,
        "submit_uuid" to submitUuid, "submitted_at" to submittedAt, "submit_sent" to submitSent,
        "problem" to problem, "problem_code" to problemCode, "unverified_time" to unverifiedTime,
        "field_errors" to fieldErrors, "discards" to discards, "reconcile" to reconcile,
        "files" to files.map { f -> mapOf("id" to f.id, "part" to f.part, "field" to f.field, "kind" to f.kind,
            "path" to f.path, "content_type" to f.contentType, "source" to f.source, "size" to f.size,
            "sha256" to f.sha256, "label" to f.label, "server_id" to f.serverId, "sent" to f.sent,
            "progress" to f.progress.toDouble(), "error" to f.error) },
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
                files = (o["files"] as? JsonArray).orEmpty().map { it.jsonObject }.map { f ->
                    fun fs(k: String) = (f[k] as? JsonPrimitive)?.contentOrNull
                    LocalFile(fs("id")!!, fs("part")!!, fs("field")!!, fs("kind")!!, fs("path")!!, fs("content_type")!!,
                        fs("source") ?: "camera", (f["size"] as? JsonPrimitive)?.longOrNull ?: 0L, fs("sha256").orEmpty(),
                        fs("label").orEmpty(), fs("server_id"), (f["sent"] as? JsonPrimitive)?.booleanOrNull ?: false,
                        fs("progress")?.toFloatOrNull() ?: 0f, fs("error"))
                },
            )
        }
    }
}

/**
 * Drafts on this phone: one file per job in [dir], written atomically on every change, and the
 * job's photos and files under [dir]/files. Nothing here is deleted until the server has it,
 * except when the expert discards a draft.
 */
class DraftStore(private val dir: File) {
    val filesDir: File get() = File(dir, "files").apply { mkdirs() }
    private val cache = HashMap<String, Draft>()
    /** Bumped on every change, so screens redraw when the outbox moves things along. */
    val changes = kotlinx.coroutines.flow.MutableStateFlow(0L)

    private fun fileOf(bookingId: String): File {
        require(bookingId.matches(Regex("[0-9a-fA-F-]{36}"))) { "Not a booking id." }
        return File(dir, "$bookingId.json")
    }

    @Synchronized
    fun get(bookingId: String): Draft? = cache[bookingId] ?: fileOf(bookingId).takeIf { it.exists() }
        ?.let { f -> runCatching { Draft.fromJson(Json.parseToJsonElement(f.readText()).jsonObject) }.getOrNull() }
        ?.also { cache[bookingId] = it }

    @Synchronized
    fun all(): List<Draft> = (dir.listFiles { f -> f.name.endsWith(".json") }.orEmpty())
        .mapNotNull { get(it.name.removeSuffix(".json")) }

    /** Committed to storage before it returns (the screen acknowledges a change only after this). */
    @Synchronized
    fun save(d: Draft): Draft {
        writeAtomically(fileOf(d.bookingId), d.toJson().toString().toByteArray())
        cache[d.bookingId] = d
        changes.value++
        return d
    }

    /** Change one draft under the lock (so the outbox and the screen never overwrite each other). */
    @Synchronized
    fun update(bookingId: String, change: (Draft) -> Draft): Draft? = get(bookingId)?.let { save(change(it)) }

    /** Discard: the answers and every file of this job (also ones not sent). */
    @Synchronized
    fun discard(bookingId: String) {
        get(bookingId)?.files?.forEach { if (it.path.isNotEmpty()) File(it.path).delete() }
        fileOf(bookingId).delete()
        cache.remove(bookingId)
        changes.value++
    }

    /** What the heartbeat reports: jobs not yet submitted to the server, and files not yet sent. */
    fun unsentCounts(): Pair<Int, Int> = all().let { d -> d.count { !it.submitSent } to d.sumOf { x -> x.files.count { !it.sent } } }

    /** Sent copies the phone may drop to free space (never unsent ones). */
    @Synchronized
    fun clearSentCopies(): Long {
        var freed = 0L
        all().forEach { d -> d.files.filter { it.sent && it.path.isNotEmpty() }.forEach { f -> File(f.path).takeIf { it.exists() }?.let { freed += it.length(); it.delete() } } }
        return freed
    }

    fun sentBytes(): Long = all().sumOf { d -> d.files.filter { it.sent && it.path.isNotEmpty() }.sumOf { File(it.path).takeIf { f -> f.exists() }?.length() ?: 0L } }
}
