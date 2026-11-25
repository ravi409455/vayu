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
    @SerialName("verify_url") val verifyUrl: String = "",
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
data class Alert(val code: String = "", val detail: String = "")

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
) {
    companion object {
        fun list(rows: List<JsonObject>): List<MediaItem> = rows.mapNotNull { runCatching { opsJson.decodeFromJsonElement(serializer(), it) }.getOrNull() }
    }
}
