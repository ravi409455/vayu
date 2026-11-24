package `in`.carcid.vayu.core.draft

import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.forms.Filled
import `in`.carcid.vayu.core.forms.PARTS
import `in`.carcid.vayu.core.rules.JsonLogic
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import java.io.File
import java.io.RandomAccessFile

/**
 * Sends what the phone holds, in an order that never waits on big files: register every file
 * (the server's id goes into the answers), send the start with its check-in, send the submit,
 * then upload the bytes. Every step is safe to repeat (client UUIDs), so a run can stop anywhere.
 */
/** The draft's job is closed on the server: its work can't be sent; the expert discards it. */
const val JOB_CLOSED = "JOB_CLOSED"
const val CLOSED_TEXT = "This job is closed on the server, so this work can't be sent. Discard the draft."

class Outbox(
    private val api: Api,
    private val drafts: DraftStore,
    private val appVersion: Int,
    /** The forms and booking answers of a draft (null when the phone no longer has its forms). */
    private val filledOf: (Draft) -> Filled?,
) {
    /** Statuses that mean "the server has every byte". */
    private val arrived = setOf("uploaded", "verified")

    /** Returns false when the server could not be reached (try again later), true when done. */
    suspend fun run(): Boolean {
        for (d in drafts.all().filter { it.unsent }) {
            try {
                push(d.bookingId)
            } catch (e: ApiError) {
                if (e.code == ApiError.NETWORK || e.status >= 500) return false
                if (e.code == "DEVICE_REVOKED") throw e
            }
        }
        return true
    }

    private fun note(id: String, e: ApiError?) = drafts.update(id) { d ->
        if (e != null && closed(e)) d.copy(problem = CLOSED_TEXT, problemCode = JOB_CLOSED)
        else d.copy(problem = e?.message, problemCode = e?.code)
    }

    /** The server no longer takes this job's work (closed more than a week ago, or not theirs). */
    private fun closed(e: ApiError) = e.code == "NOT_FOUND" || e.code == "BOOKING_CLOSED"

    private suspend fun push(id: String) {
        if (drafts.get(id)!!.problemCode == JOB_CLOSED) return     // waits for the expert to discard it
        takeBack(id)
        if (drafts.get(id)!!.reconcile) reconcile(id)
        register(id)
        // a field was full on the server: pick up what is there, then register what is left
        if (drafts.get(id)!!.reconcile) { reconcile(id); register(id) }
        if (drafts.get(id)!!.problemCode == JOB_CLOSED) return
        sendStart(id)
        if (drafts.get(id)!!.problemCode == JOB_CLOSED) return
        sendSubmit(id)
        upload(id)
    }

    private suspend fun register(id: String) {
        for (f in drafts.get(id)!!.files.filter { it.serverId == null }) {
            if (!File(f.path).exists()) continue
            try {
                val r = api.mediaInitiate(id, f.id, f.field, f.kind, f.contentType, f.size, f.sha256, f.source)
                val server = r.str("id").takeIf { it.matches(SERVER_ID) } ?: throw ApiError("BAD_ID", "The server sent an odd file id.", 0)
                val done = r.str("status") in arrived
                drafts.update(id) { d -> d.copy(files = d.files.map { if (it.id == f.id) it.copy(serverId = server, sent = done, error = null) else it }) }
            } catch (e: ApiError) {
                if (e.code == ApiError.NETWORK || e.status >= 500 || e.code == "DEVICE_REVOKED") throw e
                // the field is full on the server: files from before; pick them up and try again next run
                if (e.code == "TOO_MANY") {
                    drafts.update(id) { d -> d.copy(reconcile = true, files = d.files.map {
                        if (it.id == f.id) it.copy(error = "This field already has its photos from before. Delete one to send this.") else it }) }
                    continue
                }
                if (closed(e)) { note(id, e); return }
                drafts.update(id) { d -> d.copy(files = d.files.map { if (it.id == f.id) it.copy(error = e.message) else it }) }
            }
        }
    }

    /** Delete on the server the files the expert removed or replaced after they were sent. */
    private suspend fun takeBack(id: String) {
        for (server in drafts.get(id)!!.discards) {
            if (!server.matches(SERVER_ID)) { drafts.update(id) { it.copy(discards = it.discards - server) }; continue }
            try {
                api.act("DELETE", "media/$server")
            } catch (e: ApiError) {
                if (e.code == ApiError.NETWORK || e.status >= 500 || e.code == "DEVICE_REVOKED") throw e
                // gone already, or no longer ours to take back: nothing more to do
            }
            drafts.update(id) { it.copy(discards = it.discards - server) }
        }
    }

    /**
     * The job was started before (another phone, cleared storage): the server's finished files go
     * back into the answers (marked sent), even past the field's limit, so the expert sees them and
     * chooses which to delete; finished files are never deleted here. Only half-sent leftovers of
     * the expert's own are taken back (web: reconcileMedia). Applied to the draft as it is now.
     */
    private suspend fun reconcile(id: String) {
        val rows = (api.get("bookings/$id/media") as? JsonArray).orEmpty().map { it.jsonObject }
            .filter { it.str("id").matches(SERVER_ID) }
        val fields = filledOf(drafts.get(id)!!)?.trees.orEmpty()
            .flatMap { (p, t) -> t?.fields.orEmpty().map { p to it } }.associateBy { it.second.key }
        drafts.update(id) { cur ->
            val known = cur.files.mapNotNull { it.serverId }.toSet() + cur.discards
            var next = cur
            val drop = mutableListOf<String>()
            for (r in rows) {
                val server = r.str("id")
                if (server in known) continue
                val (part, f) = fields[r.str("field_key")] ?: continue
                if (r.str("status") !in arrived) { drop += server; continue }
                val file = LocalFile(java.util.UUID.randomUUID().toString(), part, f.key, r.str("kind"), "", "", "server", 0, "",
                    "${f.label} (from before)", serverId = server, sent = true, progress = 1f)
                val value: Any? = if (f.type == "signature") (next.answer(part, f.key) ?: file.id)
                    else ((next.answer(part, f.key) as? List<*>).orEmpty() + file.id)
                next = next.copy(files = next.files + file).withAnswer(part, f.key, value)
            }
            next.copy(reconcile = false, discards = next.discards + drop)
        }
        takeBack(id)
    }


    /** The answers of one part as the server takes them: visible ones only, file ids swapped for the server's. */
    private fun outgoing(d: Draft, filled: Filled, part: String): JsonObject? {
        if (filled.trees[part] == null) return JsonObject(emptyMap())
        val server = d.files.associate { it.id to it.serverId }
        val values = filled.submittable(part).mapValues { (_, v) ->
            when (v) {
                is String -> if (v in server) server[v] ?: return null else v
                is List<*> -> v.map { x -> if (x is String && x in server) server[x] ?: return null else x }
                else -> v
            }
        }
        return JsonLogic.toJson(values) as JsonObject
    }

    private suspend fun sendStart(id: String) {
        val d = drafts.get(id)!!
        if (d.startSent || d.startedAt == null) return
        val filled = filledOf(d) ?: return
        val start = outgoing(d, filled, "start") ?: return          // a check-in file not registered yet
        try {
            api.start(id, d.startUuid, d.startedAt, d.inspectionType, start, appVersion)
            drafts.update(id) { it.copy(startSent = true, problem = null, problemCode = null) }
        } catch (e: ApiError) {
            if (e.code == ApiError.NETWORK || e.status >= 500 || e.code == "DEVICE_REVOKED") throw e
            if (closed(e)) { note(id, e); return }
            val errors = (e.extra["errors"] as? JsonObject).orEmpty().mapValues { (it.value as? JsonPrimitive)?.contentOrNull ?: "" }
            drafts.update(id) { it.copy(problem = if (errors.isEmpty()) e.message else "The check-in was refused. Fix the answers marked in red.",
                problemCode = e.code, fieldErrors = it.fieldErrors + errors, startedAt = if (errors.isEmpty()) it.startedAt else null) }
        }
    }

    private suspend fun sendSubmit(id: String) {
        val d = drafts.get(id)!!
        if (d.submittedAt == null || d.submitSent) return
        // the start must have reached the server, unless the job was taken away or cancelled meanwhile
        // (then the submit goes alone and the server records the conflict for Ops)
        if (!d.startSent && d.problemCode !in setOf("NOT_ASSIGNED", "INVALID_STAGE")) return
        val filled = filledOf(d) ?: return
        val parts = PARTS.associateWith { outgoing(d, filled, it) ?: return }
        try {
            api.submit(id, d.submitUuid, d.versions["inspection"], JsonObject(parts))
            drafts.update(id) { it.copy(submitSent = true, problem = null, problemCode = null, fieldErrors = emptyMap()) }
        } catch (e: ApiError) {
            if (e.code == ApiError.NETWORK || e.status >= 500 || e.code == "DEVICE_REVOKED") throw e
            val errors = (e.extra["errors"] as? JsonObject).orEmpty().mapValues { (it.value as? JsonPrimitive)?.contentOrNull ?: "" }
            if (e.code == "INVALID_ANSWERS" || e.code == "FIELD_ACCESS") drafts.update(id) {
                // back to the expert: the answers open again with the refused ones marked
                it.copy(submittedAt = null, problemCode = e.code, fieldErrors = errors,
                    problem = "The server refused some answers. Fix the ones marked in red and submit again.")
            } else note(id, e)
        }
    }

    private suspend fun upload(id: String) {
        for (f in drafts.get(id)!!.files.filter { it.serverId != null && !it.sent }) {
            try {
                send(id, f)
            } catch (e: ApiError) {
                if (e.code == ApiError.NETWORK || e.status >= 500 || e.code == "DEVICE_REVOKED") throw e
                mark(id, f.id) { it.copy(error = e.message) }
            }
        }
    }

    private suspend fun send(id: String, f: LocalFile) {
        val file = File(f.path)
        if (!file.exists()) return
        val init = api.mediaInitiate(id, f.id, f.field, f.kind, f.contentType, f.size, f.sha256, f.source)
        val ok = transfer(api, init, file, f.contentType) { p -> mark(id, f.id) { it.copy(progress = p) } }
        // a checksum that did not match: the next run registers and sends it again
        mark(id, f.id) { if (ok) it.copy(sent = true, progress = 1f, error = null) else it.copy(progress = 0f, error = "Arrived damaged; sending again.") }
    }

    private fun mark(id: String, fileId: String, change: (LocalFile) -> LocalFile) =
        drafts.update(id) { d -> d.copy(files = d.files.map { if (it.id == fileId) change(it) else it }) }
}

/** A server file id (a UUID): checked before it goes into a request path. */
private val SERVER_ID = Regex("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

private fun JsonObject.str(k: String) = (this[k] as? JsonPrimitive)?.contentOrNull ?: ""

/**
 * Send a registered file's missing parts straight to storage and finish it. [init] is the
 * media/initiate answer. True when the server has every byte; false if it arrived damaged.
 */
suspend fun transfer(api: Api, init: JsonObject, file: File, contentType: String, progress: (Float) -> Unit = {}): Boolean {
    val arrived = setOf("uploaded", "verified")
    if (init.str("status") in arrived) return true
    val id = init.str("id")
    val partSize = (init["part_size"] as? JsonPrimitive)?.intOrNull ?: (8 * 1024 * 1024)
    val have = (api.media(id)["uploaded_parts"] as? JsonArray).orEmpty().map { it.jsonObject }
        .associate { (it["part_number"] as JsonPrimitive).intOrNull!! to it.str("etag") }.toMutableMap()
    val urls = (init["parts"] as? JsonArray).orEmpty().map { it.jsonObject }
        .associate { (it["part_number"] as JsonPrimitive).intOrNull!! to it.str("url") }
    RandomAccessFile(file, "r").use { raf ->
        for ((n, url) in urls.toSortedMap()) {
            if (n in have || url.isEmpty()) continue
            val from = (n - 1).toLong() * partSize
            val bytes = ByteArray(minOf(partSize.toLong(), file.length() - from).toInt())
            raf.seek(from); raf.readFully(bytes)
            have[n] = api.putPart(url, bytes, contentType)
            progress(minOf(1f, (n.toLong() * partSize).toFloat() / file.length()))
        }
    }
    return api.mediaComplete(id, have.toSortedMap().map { it.key to it.value }).str("status") in arrived
}
