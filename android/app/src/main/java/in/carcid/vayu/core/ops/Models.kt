package `in`.carcid.vayu.core.ops

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/**
 * Typed Ops replies (R-11), decoded once here instead of read field by field in the screens.
 * Unknown fields are ignored and a null where a value is expected takes the default, so a newer
 * server never breaks an older app.
 */
internal val opsJson = Json { ignoreUnknownKeys = true; coerceInputValues = true; explicitNulls = false }

/** Whether Regenerate can be pressed now, and why not (GET bookings/{id}/report). */
@Serializable
data class Regenerate(val allowed: Boolean = false, val reason: String? = null)

/** A booking's report (GET bookings/{id}/report). */
@Serializable
data class Report(
    val revision: Int? = null,
    /** "ready", "pending" or "failed". */
    val status: String = "",
    /** Being made right now. */
    val updating: Boolean = false,
    /** Something it shows changed since: Ops press Regenerate. */
    @SerialName("out_of_date") val outOfDate: Boolean = false,
    val regenerate: Regenerate = Regenerate(),
    @SerialName("generated_at") val generatedAt: String? = null,
    val error: String = "",
    /** The PDF through the server (logged); null until ready. */
    val url: String? = null,
) {
    companion object {
        /** The reply as a Report; null when it isn't one. */
        fun from(e: JsonElement?): Report? = (e as? JsonObject)?.let { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}

/** A note the server keeps on a booking (TYPE_CHANGE_REJECTED, LATE_WORK, …). */
@Serializable
data class Alert(val code: String = "", val detail: String = "", val at: String = "")

/** Started late / too quick (Admin and Ops only); names and times of who marked them reviewed. */
@Serializable
data class Timing(
    val late: Boolean = false, val quick: Boolean = false,
    @SerialName("late_minutes") val lateMinutes: Int? = null,
    @SerialName("duration_minutes") val durationMinutes: Int? = null,
    @SerialName("min_minutes") val minMinutes: Int? = null,
    @SerialName("grace_minutes") val graceMinutes: Int? = null,
    @SerialName("late_reviewed_by") val lateReviewedBy: String? = null,
    @SerialName("late_reviewed_at") val lateReviewedAt: String? = null,
    @SerialName("quick_reviewed_by") val quickReviewedBy: String? = null,
    @SerialName("quick_reviewed_at") val quickReviewedAt: String? = null,
)

/** A booking (GET bookings, GET bookings/{id}); [answers] is the booking form, whose fields the Admin defines. */
@Serializable
data class Booking(
    val id: String = "",
    @SerialName("booking_id") val bookingId: String = "",
    val stage: String = "",
    @SerialName("inspection_type") val inspectionType: String = "",
    @SerialName("assigned_expert") val assignedExpert: Int? = null,
    val answers: JsonObject = JsonObject(emptyMap()),
    @SerialName("row_version") val rowVersion: Int = 0,
    val conflict: String = "",
    @SerialName("cancel_reason") val cancelReason: String = "",
    @SerialName("unverified_time") val unverifiedTime: Boolean = false,
    val alerts: List<Alert> = emptyList(),
    val timing: Timing? = null,
) {
    companion object {
        fun from(e: JsonElement?): Booking? = (e as? JsonObject)?.let { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}

/**
 * One expert's inspection of a booking (GET bookings/{id}/inspections). [answers] (per part), [scores]
 * and [overrides] follow the form the Admin built, so they stay JSON objects.
 */
@Serializable
data class Inspection(
    val id: String = "",
    val expert: Int? = null,
    /** "draft" or "submitted". */
    val status: String = "",
    @SerialName("submitted_at") val submittedAt: String = "",
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("row_version") val rowVersion: Int = 0,
    @SerialName("form_version") val formVersion: Int? = null,
    @SerialName("start_version") val startVersion: Int? = null,
    @SerialName("end_version") val endVersion: Int? = null,
    val answers: JsonObject = JsonObject(emptyMap()),
    val scores: JsonObject = JsonObject(emptyMap()),
    val overrides: JsonObject = JsonObject(emptyMap()),
    @SerialName("unverified_time") val unverifiedTime: Boolean = false,
) {
    companion object {
        fun from(e: JsonElement?): Inspection? = (e as? JsonObject)?.let { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
        /** A list reply as inspections (rows that aren't one are left out). */
        fun list(rows: List<JsonObject>): List<Inspection> = rows.mapNotNull(::from)
    }
}

/** A photo, video, file or signature on a booking (GET bookings/{id}/media). */
@Serializable
data class MediaItem(
    val id: String = "",
    @SerialName("field_key") val fieldKey: String = "",
    /** "photo", "video", "file" or "signature". */
    val kind: String = "",
    /** "pending", "uploaded", "verified", "failed" or "purged". */
    val status: String = "",
    /** its field is marked "Hide from customer": never in the report, its downloads or a ZIP */
    @SerialName("hidden_from_customer") val hiddenFromCustomer: Boolean = false,
) {
    companion object {
        fun list(rows: List<JsonObject>): List<MediaItem> = rows.mapNotNull { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}

/** A person (GET users): Ops see names, roles and phones to assign and call. */
@Serializable
data class Person(
    val id: Int? = null,
    val username: String = "",
    val name: String = "",
    val role: String = "",
    @SerialName("is_active") val isActive: Boolean = true,
    val phone: String = "",
) {
    /** The name to show: the full name, else the username. */
    val shown: String get() = name.ifBlank { username }

    companion object {
        fun list(rows: List<JsonObject>): List<Person> = rows.mapNotNull { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}

/** One entry of a master list (GET master-lists/{key}/items) or of the inspection types (GET inspection-types). */
@Serializable
data class ListItem(val key: String = "", val label: String = "", val archived: Boolean = false, val available: Boolean = true) {
    companion object {
        fun list(rows: List<JsonObject>): List<ListItem> = rows.mapNotNull { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}

/** A file the server has waited on too long (GET problems/stuck-uploads); [expert] is who sent it. */
@Serializable
data class StuckUpload(
    val id: String = "",
    val booking: String = "",
    @SerialName("booking_id") val bookingId: String = "",
    @SerialName("field_key") val fieldKey: String = "",
    val expert: String = "",
    /** When the upload began (Needs you shows the time). */
    @SerialName("created_at") val createdAt: String = "",
) {
    companion object {
        fun list(rows: List<JsonObject>): List<StuckUpload> = rows.mapNotNull { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}

/** A report that needs Ops (GET problems/reports): [problem] is "failed", "stuck" or "out_of_date". */
@Serializable
data class ReportProblem(
    val booking: String = "",
    @SerialName("booking_id") val bookingId: String = "",
    val error: String = "",
    val problem: String = "",
    @SerialName("out_of_date_since") val outOfDateSince: String? = null,
    /** When it became a problem: failed, render started, went out of date, or sent (missing). */
    val at: String? = null,
) {
    companion object {
        fun list(rows: List<JsonObject>): List<ReportProblem> = rows.mapNotNull { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}

/** Numbers for one period or one expert (GET dashboards/summary); the timing ones only for those who may see them. */
@Serializable
data class DashStats(
    val expert: Int? = null,
    val bookings: Int? = null, val completed: Int? = null, val cancelled: Int? = null,
    val late: Int? = null, val quick: Int? = null,
    @SerialName("completion_rate") val completionRate: Double? = null,
    @SerialName("avg_minutes") val avgMinutes: Int? = null,
    @SerialName("on_time") val onTime: Int? = null,
)

/** GET dashboards/summary: this period, the one before, and per expert. */
@Serializable
data class DashSummary(val period: DashStats = DashStats(), val previous: DashStats = DashStats(),
                       @SerialName("by_expert") val byExpert: List<DashStats> = emptyList()) {
    companion object {
        fun from(e: JsonElement?): DashSummary? = (e as? JsonObject)?.let { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}

/** One count of GET dashboards/volume: [key] (a type, city, expert or stage) in [period]. */
@Serializable
data class VolumeRow(val period: String = "", val key: String = "", val count: Int = 0) {
    companion object {
        fun list(rows: List<JsonObject>): List<VolumeRow> = rows.mapNotNull { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}

/** Signed links to a stored file (GET media/{id}/url); [previewUrl] is the small copy when the server has one. */
@Serializable
data class MediaLinks(val url: String = "", @SerialName("preview_url") val previewUrl: String? = null) {
    companion object {
        fun from(e: JsonElement?): MediaLinks? = (e as? JsonObject)?.let { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}
