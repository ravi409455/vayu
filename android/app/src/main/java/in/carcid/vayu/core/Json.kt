package `in`.carcid.vayu.core

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/** A text field of a server reply, "" when missing or not text (the one getter the app uses). */
fun JsonObject.s(k: String): String = (this[k] as? JsonPrimitive)?.contentOrNull ?: ""

/** Media statuses that mean the file reached storage (uploaded, then checked). */
val ARRIVED = setOf("uploaded", "verified")
