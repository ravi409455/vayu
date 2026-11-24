package `in`.carcid.vayu.core.alerts

import `in`.carcid.vayu.core.writeAtomically
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import kotlinx.serialization.json.put
import java.io.File
import java.time.Instant

/** A notice the phone made itself (a job reminder, photos not sending); ids are negative. */
data class LocalNote(val id: Long, val kind: String, val title: String, val body: String, val booking: String?,
                     val at: Instant, val read: Boolean = false)

/** The phone's own notices, kept beside the server's in the bell (latest 30; cleared at sign-out). */
class LocalNotes(private val file: File, private val now: () -> Instant = Instant::now) {
    @Synchronized fun all(): List<LocalNote> = runCatching {
        Json.parseToJsonElement(file.readText()).jsonArray.map { e ->
            val o = e.jsonObject
            LocalNote(o.getValue("id").jsonPrimitive.long, o["kind"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                o["title"]?.jsonPrimitive?.contentOrNull.orEmpty(), o["body"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                o["booking"]?.jsonPrimitive?.contentOrNull, Instant.ofEpochMilli(o.getValue("at").jsonPrimitive.long),
                o["read"]?.jsonPrimitive?.boolean ?: false)
        }
    }.getOrDefault(emptyList())

    @Synchronized fun add(kind: String, title: String, body: String, booking: String?) {
        val t = now()
        val kept = all()
        var id = -t.toEpochMilli()
        while (kept.any { it.id == id }) id--          // two in the same millisecond: still unique
        save(listOf(LocalNote(id, kind, title, body, booking, t)) + kept.take(29))
    }

    /** Mark these read (all when [ids] is null). */
    @Synchronized fun read(ids: List<Long>?) = save(all().map { if (ids == null || it.id in ids) it.copy(read = true) else it })

    @Synchronized fun clear() { file.delete() }

    private fun save(notes: List<LocalNote>) {
        file.parentFile?.mkdirs()
        writeAtomically(file, JsonArray(notes.map { n -> buildJsonObject {
            put("id", n.id); put("kind", n.kind); put("title", n.title); put("body", n.body)
            put("booking", n.booking?.let { JsonPrimitive(it) } ?: JsonPrimitive(null as String?)); put("at", n.at.toEpochMilli()); put("read", n.read)
        } }).toString().toByteArray())
    }
}
