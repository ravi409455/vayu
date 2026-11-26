package `in`.carcid.vayu.core.ops

import `in`.carcid.vayu.core.s

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

    /** Fresh when possible; the saved copy when the server can't be reached. Throws if neither.
     *  A path made with [allPages] reads every page (the server pages at 50). */
    suspend fun load(path: String): Loaded = try {
        val data = if (ALL_PAGES in path) everyPage(path) else api.get(path)
        // a full phone only loses the offline copy: the fresh answer is still shown (N-3)
        runCatching {
            writeAtomically(fileOf(path), buildJsonObject { put("at", JsonPrimitive(clock())); put("data", data) }.toString().toByteArray())
            trim()
        }
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

    /** Follows the server's pages to the end, as one {count, results} (H-14 on the phone, N-2). */
    private suspend fun everyPage(path: String): JsonElement {
        val out = mutableListOf<JsonElement>()
        for (page in 1..MAX_PAGES) {
            val r = api.get(if (page == 1) path else "$path&page=$page")
            if (r !is JsonObject) return r
            out += (r["results"] as? JsonArray).orEmpty()
            if (r["next"] == null || r["next"] is kotlinx.serialization.json.JsonNull) break
        }
        return buildJsonObject { put("count", JsonPrimitive(out.size)); put("results", JsonArray(out)) }
    }

    private fun trim() {
        val files = dir.listFiles { f -> f.name.endsWith(".json") }.orEmpty()
        if (files.size > keep) files.sortedBy { it.lastModified() }.take(files.size - keep).forEach { it.delete() }
    }
}

private const val ALL_PAGES = "page_size=200"
private const val MAX_PAGES = 40     // ponytail: 8000 rows; lists past that need paging on screen

/** [path] read whole: every page, 200 at a time (Today, a day's bookings, the users). */
fun allPages(path: String) = path + (if ('?' in path) "&" else "?") + ALL_PAGES

/** A list the API returns bare, as a page ({count, results}) or as {rows} (dashboards). */
fun JsonElement.rows(): List<JsonObject> = when (this) {
    is JsonArray -> map { it.jsonObject }
    is JsonObject -> ((this["results"] ?: this["rows"]) as? JsonArray)?.map { it.jsonObject }.orEmpty()
    else -> emptyList()
}

fun JsonElement.count(): Int = ((this as? JsonObject)?.get("count") as? JsonPrimitive)?.contentOrNull?.toIntOrNull() ?: rows().size

fun JsonObject.o(k: String): JsonObject = this[k] as? JsonObject ?: JsonObject(emptyMap())
fun JsonObject.a(k: String): JsonArray = this[k] as? JsonArray ?: JsonArray(emptyList())
