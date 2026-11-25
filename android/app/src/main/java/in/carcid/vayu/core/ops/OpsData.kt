package `in`.carcid.vayu.core.ops

import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.writeAtomically
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.longOrNull
import java.io.File
import java.security.MessageDigest

/** A screen's data: fresh from the server, or the last copy when there is no signal. */
data class Loaded(val data: JsonElement, val offline: Boolean, val savedAt: Long)

/**
 * Ops read what the server has; every answer is also kept (one file per address) so the screens
 * still open without signal, read-only, with "Offline · as of 10:42". Actions always need signal.
 */
class OpsData(val api: Api, private val dir: File, private val clock: () -> Long = System::currentTimeMillis,
              /** Saved copies kept at most (each search or filter is one); the least recently saved go first. */
              private val keep: Int = 300) {
    private fun fileOf(path: String): File {
        val h = MessageDigest.getInstance("SHA-256").digest(path.toByteArray()).take(12).joinToString("") { "%02x".format(it) }
        return File(dir, "$h.json")
    }

    /** Fresh when possible; the saved copy when the server can't be reached. Throws if neither. */
    suspend fun load(path: String): Loaded = try {
        val data = api.get(path)
        writeAtomically(fileOf(path), buildJsonObject { put("at", JsonPrimitive(clock())); put("data", data) }.toString().toByteArray())
        trim()
        Loaded(data, false, clock())
    } catch (e: ApiError) {
        if (e.code != ApiError.NETWORK && e.status < 500) throw e
        val saved = runCatching { Json.parseToJsonElement(fileOf(path).readText()).jsonObject }.getOrNull() ?: throw e
        Loaded(saved["data"]!!, true, (saved["at"] as JsonPrimitive).longOrNull ?: 0L)
    }

    /** The saved copy only (for showing something at once). */
    fun saved(path: String): Loaded? = runCatching {
        val o = Json.parseToJsonElement(fileOf(path).readText()).jsonObject
        Loaded(o["data"]!!, true, (o["at"] as JsonPrimitive).longOrNull ?: 0L)
    }.getOrNull()

    suspend fun act(method: String, path: String, body: JsonObject? = null): JsonElement = api.act(method, path, body)

    fun clear() { dir.listFiles()?.forEach { it.delete() } }

    private fun trim() {
        val files = dir.listFiles { f -> f.name.endsWith(".json") }.orEmpty()
        if (files.size > keep) files.sortedBy { it.lastModified() }.take(files.size - keep).forEach { it.delete() }
    }
}

/** A list the API returns bare, as a page ({count, results}) or as {rows} (dashboards). */
fun JsonElement.rows(): List<JsonObject> = when (this) {
    is JsonArray -> map { it.jsonObject }
    is JsonObject -> ((this["results"] ?: this["rows"]) as? JsonArray)?.map { it.jsonObject }.orEmpty()
    else -> emptyList()
}

fun JsonElement.count(): Int = ((this as? JsonObject)?.get("count") as? JsonPrimitive)?.contentOrNull?.toIntOrNull() ?: rows().size

fun JsonObject.s(k: String): String = (this[k] as? JsonPrimitive)?.contentOrNull ?: ""
fun JsonObject.o(k: String): JsonObject = this[k] as? JsonObject ?: JsonObject(emptyMap())
fun JsonObject.a(k: String): JsonArray = this[k] as? JsonArray ?: JsonArray(emptyList())
