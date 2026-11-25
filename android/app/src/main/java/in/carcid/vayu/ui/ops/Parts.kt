package `in`.carcid.vayu.ui.ops


import `in`.carcid.vayu.core.ops.Inspection
import `in`.carcid.vayu.ui.expert.answered

import androidx.compose.material.icons.automirrored.outlined.List
import androidx.compose.runtime.Composable
import `in`.carcid.vayu.core.forms.Field
import `in`.carcid.vayu.core.forms.Filled
import `in`.carcid.vayu.core.forms.FormTree
import `in`.carcid.vayu.core.forms.PARTS
import `in`.carcid.vayu.core.ops.a
import `in`.carcid.vayu.core.ops.o
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.s
import `in`.carcid.vayu.core.rules.JsonLogic
import kotlinx.serialization.json.JsonObject

/** A booking with its current inspection and that inspection's form trees. */
class Loaded3(val b: Bk, val insp: Inspection?, val trees: Map<String, FormTree?>, val raw: Map<String, JsonObject?>, val offline: Boolean,
              val insps: List<Inspection> = emptyList()) {
    @Suppress("UNCHECKED_CAST")
    val answers: Map<String, Map<String, Any?>> get() = PARTS.associateWith { p ->
        (insp?.answers?.get(p)?.let { JsonLogic.fromJson(it) } as? Map<String, Any?>).orEmpty() }
    fun filled(today: String) = trees["inspection"]?.let { Filled(trees, answers, JsonLogic.fromJson(b.answers) as Map<String, Any?>, today) }
}

/** The three forms an inspection was made with (check-in, inspection, wrap-up), raw and parsed. */
@Composable
fun rememberForms(env: OpsEnv, insp: Inspection?): Map<String, JsonObject?> {
    val versions = mapOf("inspection" to insp?.formVersion, "start" to insp?.startVersion, "end" to insp?.endVersion)
    return versions.mapValues { (_, v) -> rememberLoad(env, v?.let { "form-versions/$it" }).value?.data as? JsonObject }
}

@Composable
fun rememberBooking(env: OpsEnv, id: String): Loaded3? {
    val b = rememberLoad(env, "bookings/$id").value
    val insps = rememberLoad(env, "bookings/$id/inspections").value?.data?.rows()?.let(Inspection::list)
    val insp = insps?.let(::currentInspection)
    val raw = rememberForms(env, insp)
    if (b == null || insps == null) return null
    return Loaded3(Bk(b.data as JsonObject), insp, raw.mapValues { it.value?.let(FormTree::parse) }, raw, b.offline, insps)
}

/** An answer that is a problem: a defect option was chosen (its severity, else "Problem"). */
fun problemOf(f: Field, v: Any?): String? {
    val picked = when (v) { is String -> listOf(v); is List<*> -> v.filterIsInstance<String>(); else -> emptyList() }
    return f.options.firstOrNull { it.isDefect && it.key in picked }?.let { (it.severity ?: "problem").replaceFirstChar(Char::uppercase) }
}

/** How much of one part (start, inspection, end) is answered, and how many answers are problems. */
fun partCounts(data: Loaded3, filled: Filled, part: String): Pair<Int, Int> {
    val fs = filled.visiblePages(part).flatMap { it.fields }.filter { it.answerable && filled.visible(part, it.key) }
    val a = data.answers[part].orEmpty()
    return fs.count { answered(a[it.key]) } to fs.count { problemOf(it, a[it.key]) != null }
}
