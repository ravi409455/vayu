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

    private fun note(id: String, e: ApiError?) = drafts.update(id) { it.copy(problem = e?.message, problemCode = e?.code) }

    private suspend fun push(id: String) {
        register(id)
        sendStart(id)
        sendSubmit(id)
        upload(id)
    }

    private suspend fun register(id: String) {
        for (f in drafts.get(id)!!.files.filter { it.serverId == null }) {
            if (!File(f.path).exists()) continue
            try {
                val r = api.mediaInitiate(id, f.id, f.field, f.kind, f.contentType, f.size, f.sha256, f.source)
                val server = r.str("id")
                val done = r.str("status") in arrived
                drafts.update(id) { d -> d.copy(files = d.files.map { if (it.id == f.id) it.copy(serverId = server, sent = done, error = null) else it }) }
            } catch (e: ApiError) {
                if (e.code == ApiError.NETWORK || e.status >= 500 || e.code == "DEVICE_REVOKED") throw e
                drafts.update(id) { d -> d.copy(files = d.files.map { if (it.id == f.id) it.copy(error = e.message) else it }) }
            }
        }
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
            note(id, e)
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
            drafts.update(id) { it.copy(submitSent = true, problem = null, problemCode = null) }
        } catch (e: ApiError) {
            if (e.code == ApiError.NETWORK || e.status >= 500 || e.code == "DEVICE_REVOKED") throw e
            note(id, e)
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
        if (init.str("status") in arrived) { mark(id, f.id) { it.copy(sent = true, progress = 1f) }; return }
        val partSize = (init["part_size"] as? JsonPrimitive)?.intOrNull ?: (8 * 1024 * 1024)
        val have = (api.media(f.serverId!!)["uploaded_parts"] as? JsonArray).orEmpty().map { it.jsonObject }
            .associate { (it["part_number"] as JsonPrimitive).intOrNull!! to it.str("etag") }.toMutableMap()
        val urls = (init["parts"] as? JsonArray).orEmpty().map { it.jsonObject }
            .associate { (it["part_number"] as JsonPrimitive).intOrNull!! to it.str("url") }
        RandomAccessFile(file, "r").use { raf ->
            for ((n, url) in urls.toSortedMap()) {
                if (n in have || url.isEmpty()) continue
                val from = (n - 1).toLong() * partSize
                val bytes = ByteArray(minOf(partSize.toLong(), file.length() - from).toInt())
                raf.seek(from); raf.readFully(bytes)
                have[n] = api.putPart(url, bytes, f.contentType)
                mark(id, f.id) { it.copy(progress = minOf(1f, (n.toLong() * partSize).toFloat() / file.length())) }
            }
        }
        val done = api.mediaComplete(f.serverId, have.toSortedMap().map { it.key to it.value })
        when (done.str("status")) {
            in arrived -> mark(id, f.id) { it.copy(sent = true, progress = 1f, error = null) }
            // the server's checksum did not match: the next run registers and sends it again
            else -> mark(id, f.id) { it.copy(progress = 0f, error = "Arrived damaged; sending again.") }
        }
    }

    private fun mark(id: String, fileId: String, change: (LocalFile) -> LocalFile) =
        drafts.update(id) { d -> d.copy(files = d.files.map { if (it.id == fileId) change(it) else it }) }
}

private fun JsonObject.str(k: String) = (this[k] as? JsonPrimitive)?.contentOrNull ?: ""
