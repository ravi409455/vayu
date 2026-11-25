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
