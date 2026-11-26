package `in`.carcid.vayu.core.sync

import `in`.carcid.vayu.core.s

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
import `in`.carcid.vayu.core.forms.Filled
import `in`.carcid.vayu.core.forms.FormTree
import `in`.carcid.vayu.core.forms.PARTS
import `in`.carcid.vayu.core.rules.JsonLogic
import `in`.carcid.vayu.core.writeAtomically
import java.time.OffsetDateTime

/** Booking dates and times are India time (the server's zone), whatever zone the phone is set to. */
val IST: java.time.ZoneId = java.time.ZoneId.of("Asia/Kolkata")

/** One lead as My leads and the lead page show it. */
data class Job(
    val id: String, val bookingId: String, val stage: String, val customer: String, val phone: String,
    val address: String, val city: String, val car: String, val type: String,
    /** yyyy-MM-dd and HH:mm, as the booking form stores them ("" when missing). */
    val date: String, val time: String,
    val assignedToMe: Boolean, val myDraft: String?,
    /** The inspection type's key (type is its name). */
    val typeKey: String = "",
    /** The finished job's PDF: "ready", "pending", "failed", or null before it is completed. */
    val report: String? = null,
    /** Form version per part (start, inspection, end); null = that part has no form. */
    val versions: Map<String, Int?>,
    /** Why Ops cancelled it, as its list label ("" when not cancelled). */
    val cancelReason: String = "",
) {
    val open: Boolean get() = stage in OPEN
    companion object { val OPEN = setOf("assigned", "in_progress", "submitted") }
}

/**
 * What the last sync downloaded (GET sync/jobs), kept in one app-private file so My jobs, details and
 * forms work without signal. Form versions are kept across syncs (the server sends only new ones) and
 * dropped once no job and no draft on the phone uses them. Writes are atomic: a crash never leaves half a file.
 */
class JobStore(private val file: File) {
    private var cache: JsonObject? = null
    /** Set by clear(): this store never writes again (a late sync can't bring the data back). */
    private var cleared = false

    @Synchronized
    fun data(): JsonObject = cache ?: (runCatching { Json.parseToJsonElement(file.readText()).jsonObject }
        .getOrNull() ?: JsonObject(emptyMap())).also { cache = it }

    fun haveVersions(): Set<Int> = data().obj("forms").keys.mapNotNull { it.toIntOrNull() }.toSet()
    fun since(): String? = data()["server_time"]?.jsonPrimitive?.contentOrNull

    /** Phone time of the last good sync (ms), or null if it never synced. */
    fun syncedAt(): Long? = data()["synced_at"]?.jsonPrimitive?.longOrNull

    /** Time since the phone booted (ms) at the last good sync, to notice a clock changed since. */
    fun syncedElapsed(): Long? = data()["synced_elapsed"]?.jsonPrimitive?.longOrNull

    /** Server minus phone clock (ms): add it to the phone's time to get the server's. */
    fun clockOffset(): Long = data()["clock_offset"]?.jsonPrimitive?.longOrNull ?: 0L

    /** A master list's items (key, label) for list fields. */
    fun list(key: String): List<Pair<String, String>> = (data().obj("lists")[key] as? JsonArray).orEmpty()
        .map { it.jsonObject }.map { it.s("key") to it.s("label") }

    /** Inspection types (key, name) the phone knows. */
    fun types(): List<Pair<String, String>> = data().obj("types").map { it.key to (it.value.jsonPrimitive.contentOrNull ?: it.key) }

    /** What Ops changed on this booking since the last sync ("old -> new" banners). */
    fun changes(bookingId: String): List<JsonObject> = (data()["changes"] as? JsonArray).orEmpty().map { it.jsonObject }
        .filter { it.s("booking") == bookingId }

    fun form(version: Int): JsonObject? = data().obj("forms")[version.toString()] as? JsonObject

    /** [keep]: form versions the phone's drafts are pinned to (kept even when no listed job uses them). */
    @Synchronized
    fun apply(payload: JsonObject, phoneNow: Long, keep: Set<Int> = emptySet(), elapsed: Long? = null) {
        if (cleared) return
        val jobs = payload["jobs"] as? JsonArray ?: JsonArray(emptyList())
        val used = jobs.flatMap { j -> j.jsonObject.obj("versions").values.mapNotNull { it.jsonPrimitive.intOrNull?.toString() } }.toSet() +
            keep.map { it.toString() }
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
            if (elapsed != null) put("synced_elapsed", elapsed)
            put("clock_offset", offset)
        }
        write(next)
        cache = next
    }

    /** Forget the jobs; [keep]: form versions unsent drafts still need (no customer data in them). */
    @Synchronized
    fun clear(keep: Set<Int> = emptySet()) {
        cleared = true
        val forms = data().obj("forms").filterKeys { it.toIntOrNull() in keep }
        file.delete(); file.parentFile?.listFiles { f -> f.name.startsWith(file.name + ".") && f.name.endsWith(".tmp") }?.forEach { it.delete() }
        if (forms.isNotEmpty()) write(buildJsonObject { put("forms", JsonObject(forms)) })
        cache = JsonObject(emptyMap())
    }

    fun jobs(): List<Job> {
        val d = data()
        val lists = d.obj("lists")
        fun label(list: String, key: String) = (lists[list] as? JsonArray)?.firstOrNull {
            it.jsonObject.s("key") == key
        }?.jsonObject?.s("label") ?: key
        val types = d.obj("types")
        return (d["jobs"] as? JsonArray ?: JsonArray(emptyList())).map { it.jsonObject }.map { j ->
            val a = j.obj("answers")
            val type = j.s("inspection_type")
            Job(
                id = j.s("id"), bookingId = j.s("booking_id"), stage = j.s("stage"),
                customer = a.s("customer_name"), phone = a.s("customer_phone"),
                address = a.s("address"), city = label("city", a.s("city")),
                car = label("car_make_model", a.s("car_make_model")),
                type = types[type]?.jsonPrimitive?.contentOrNull ?: type,
                date = a.s("inspection_date").take(10), time = a.s("inspection_time").take(5),
                assignedToMe = j["assigned_to_me"]?.jsonPrimitive?.booleanOrNull ?: false,
                myDraft = j["my_draft"]?.jsonPrimitive?.contentOrNull,
                versions = j.obj("versions").mapValues { it.value.jsonPrimitive.intOrNull },
                typeKey = type,
                report = j["report"]?.jsonPrimitive?.contentOrNull,
                cancelReason = j.s("cancel_reason").let { if (it.isEmpty()) "" else label("cancel_reason", it) },
            )
        }.sortedWith(compareBy({ it.date }, { it.time }))
    }

    /** The booking's own answers (rules may refer to them, e.g. booking.city). */
    fun bookingAnswers(bookingId: String): Map<String, Any?> =
        @Suppress("UNCHECKED_CAST")
        ((data()["jobs"] as? JsonArray)?.map { it.jsonObject }?.firstOrNull { it.s("id") == bookingId }
            ?.get("answers")?.let { JsonLogic.fromJson(it) } as? Map<String, Any?>).orEmpty()

    /** Parsed form versions: a published version never changes, so each is parsed once (F-052). */
    private val trees = java.util.concurrent.ConcurrentHashMap<Int, FormTree>()

    /** A form version as a tree (null when the phone doesn't hold it). */
    fun tree(version: Int?): FormTree? = version?.let { v ->
        trees[v] ?: form(v)?.let { FormTree.parse(it) }?.also { trees[v] = it }
    }

    /** The forms and answers of an inspection, ready for the rules; null if a form is missing. */
    fun filled(bookingId: String, versions: Map<String, Int?>, answers: Map<String, Map<String, Any?>>,
               today: String, kept: Map<String, Any?> = emptyMap()): Filled? {
        val trees = PARTS.associateWith { p -> versions[p]?.let { tree(it) ?: return null } }
        if (trees["inspection"] == null) return null
        // off the list (taken away, closed): the copy the draft kept
        return Filled(trees, answers, bookingAnswers(bookingId).ifEmpty { kept }, today)
    }

    /** Every form this job needs is on the phone, so it can be done without signal. */
    fun readyOffline(job: Job): Boolean =
        job.versions["inspection"] != null && job.versions.values.filterNotNull().all { form(it) != null }

    private fun write(o: JsonObject) = writeAtomically(file, o.toString().toByteArray())
}

private fun JsonObject.obj(k: String): JsonObject = this[k] as? JsonObject ?: JsonObject(emptyMap())
