package `in`.carcid.vayu.core.sync

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.io.File
import java.io.FileOutputStream
import java.time.OffsetDateTime

/** One job as My jobs and Job details show it. */
data class Job(
    val id: String, val bookingId: String, val stage: String, val customer: String, val phone: String,
    val address: String, val city: String, val car: String, val type: String,
    /** yyyy-MM-dd and HH:mm, as the booking form stores them ("" when missing). */
    val date: String, val time: String,
    val assignedToMe: Boolean, val myDraft: String?,
    /** Form version per part (start, inspection, end); null = that part has no form. */
    val versions: Map<String, Int?>,
) {
    val open: Boolean get() = stage in OPEN
    companion object { val OPEN = setOf("assigned", "in_progress", "submitted") }
}

/**
 * What the last sync downloaded (GET sync/jobs), kept in one app-private file so My jobs, details and
 * forms work without signal. Form versions are kept across syncs (the server sends only new ones) and
 * dropped once no job uses them. Writes are atomic: a crash never leaves half a file.
 */
class JobStore(private val file: File) {
    private var cache: JsonObject? = null

    @Synchronized
    fun data(): JsonObject = cache ?: (runCatching { Json.parseToJsonElement(file.readText()).jsonObject }
        .getOrNull() ?: JsonObject(emptyMap())).also { cache = it }

    fun haveVersions(): Set<Int> = data().obj("forms").keys.mapNotNull { it.toIntOrNull() }.toSet()
    fun since(): String? = data()["server_time"]?.jsonPrimitive?.contentOrNull

    /** Phone time of the last good sync (ms), or null if it never synced. */
    fun syncedAt(): Long? = data()["synced_at"]?.jsonPrimitive?.longOrNull

    /** Server minus phone clock (ms): add it to the phone's time to get the server's. */
    fun clockOffset(): Long = data()["clock_offset"]?.jsonPrimitive?.longOrNull ?: 0L

    fun form(version: Int): JsonObject? = data().obj("forms")[version.toString()] as? JsonObject

    @Synchronized
    fun apply(payload: JsonObject, phoneNow: Long) {
        val jobs = payload["jobs"] as? JsonArray ?: JsonArray(emptyList())
        val used = jobs.flatMap { j -> j.jsonObject.obj("versions").values.mapNotNull { it.jsonPrimitive.intOrNull?.toString() } }.toSet()
        val forms = (data().obj("forms") + payload.obj("forms")).filterKeys { it in used }
        val server = payload["server_time"]?.jsonPrimitive?.contentOrNull
        val offset = server?.let { runCatching { OffsetDateTime.parse(it).toInstant().toEpochMilli() - phoneNow }.getOrNull() } ?: 0L
        val next = buildJsonObject {
            put("jobs", jobs)
            put("forms", JsonObject(forms))
            put("lists", payload.obj("lists"))
            put("types", payload.obj("types"))
            put("changes", payload["changes"] ?: JsonArray(emptyList()))
            if (server != null) put("server_time", server)
            put("synced_at", phoneNow)
            put("clock_offset", offset)
        }
        write(next)
        cache = next
    }

    @Synchronized
    fun clear() { file.delete(); cache = null }

    fun jobs(): List<Job> {
        val d = data()
        val lists = d.obj("lists")
        fun label(list: String, key: String) = (lists[list] as? JsonArray)?.firstOrNull {
            it.jsonObject.str("key") == key
        }?.jsonObject?.str("label") ?: key
        val types = d.obj("types")
        return (d["jobs"] as? JsonArray ?: JsonArray(emptyList())).map { it.jsonObject }.map { j ->
            val a = j.obj("answers")
            val type = j.str("inspection_type")
            Job(
                id = j.str("id"), bookingId = j.str("booking_id"), stage = j.str("stage"),
                customer = a.str("customer_name"), phone = a.str("customer_phone"),
                address = a.str("address"), city = label("city", a.str("city")),
                car = label("car_make_model", a.str("car_make_model")),
                type = types[type]?.jsonPrimitive?.contentOrNull ?: type,
                date = a.str("inspection_date").take(10), time = a.str("inspection_time").take(5),
                assignedToMe = j["assigned_to_me"]?.jsonPrimitive?.booleanOrNull ?: false,
                myDraft = j["my_draft"]?.jsonPrimitive?.contentOrNull,
                versions = j.obj("versions").mapValues { it.value.jsonPrimitive.intOrNull },
            )
        }.sortedWith(compareBy({ it.date }, { it.time }))
    }

    /** Every form this job needs is on the phone, so it can be done without signal. */
    fun readyOffline(job: Job): Boolean =
        job.versions["inspection"] != null && job.versions.values.filterNotNull().all { form(it) != null }

    private fun write(o: JsonObject) {
        file.parentFile?.mkdirs()
        val tmp = File(file.path + ".tmp")
        FileOutputStream(tmp).use { it.write(o.toString().toByteArray()); it.fd.sync() }
        check(tmp.renameTo(file)) { "Could not save the jobs file." }
    }
}

private fun JsonObject.obj(k: String): JsonObject = this[k] as? JsonObject ?: JsonObject(emptyMap())
private fun JsonObject.str(k: String): String = (this[k] as? JsonPrimitive)?.contentOrNull ?: ""
