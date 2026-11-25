package `in`.carcid.vayu.ui.ops



import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import `in`.carcid.vayu.ui.expert.whenStamp
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.ops.a
import `in`.carcid.vayu.core.ops.o
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.s
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** What happened to the booking, newest first. */
@Composable
fun HistoryScreen(env: OpsEnv, id: String, onBack: () -> Unit) {
    val rows = rememberLoad(env, "bookings/$id/activity").value?.data?.rows().orEmpty()
    val kcs = rememberBooking(env, id)?.raw?.get("inspection")?.a("key_checks").orEmpty().map { it as JsonObject }
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader("History", null, onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            rows.forEach { r ->
                Column(Modifier.fillMaxWidth().heightIn(min = 56.dp).padding(vertical = 8.dp)) {
                    Text(activityText(r, env) { k -> kcs.firstOrNull { it.s("key") == k }?.s("label") ?: k }, color = Vayu.colors.ink)
                    Text(whenStamp(r.s("at"), env.today()), fontSize = 13.sp, color = Vayu.colors.muted)
                }
                HorizontalDivider(color = Vayu.colors.line)
            }
            if (rows.isEmpty()) Text("Nothing yet.", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 20.dp))
        }
    }
}

/** One history row in words (web: activityText). */
fun activityText(r: JsonObject, env: OpsEnv, kcLabel: (String) -> String = { it }): String {
    val by = r.o("by").s("name").ifBlank { "The system" }
    val c = r.o("changes")
    fun new(k: String) = (c[k] as? kotlinx.serialization.json.JsonArray)?.getOrNull(1)?.let { (it as? JsonPrimitive)?.content }
    fun old(k: String) = (c[k] as? kotlinx.serialization.json.JsonArray)?.getOrNull(0)?.let { (it as? JsonPrimitive)?.content }
    return when {
        r.s("kind") == "created" -> "Created by $by"
        r.s("kind") == "report_downloaded" -> "$by downloaded the report"
        r.s("kind") == "report_shared" -> if (new("how") == "check_link" || c.s("how") == "check_link") "$by copied the report's check link" else "$by shared the report PDF"
        r.s("kind") == "inspection_edited" -> "$by changed ${r.a("keys").size} answer${if (r.a("keys").size == 1) "" else "s"}"
        r.s("kind") == "ratings_changed" -> "$by changed the ratings"
        r.s("kind") == "key_checks_changed" -> c.entries.map { (k, ab) ->
            val label = kcLabel(k.removePrefix("check."))
            fun at(i: Int) = ((ab as? kotlinx.serialization.json.JsonArray)?.getOrNull(i) as? JsonPrimitive)?.let { if (it is kotlinx.serialization.json.JsonNull) null else it.content }?.ifBlank { null } ?: "empty"
            "$label: ${at(0)} → ${at(1)}"
        }.let { if (it.isEmpty()) "$by changed Key Checks" else "$by changed ${it.joinToString("; ")}" }
        r.s("kind") == "media_replaced" || r.s("kind") == "media_added" -> {
            val where = r.a("keys").mapNotNull { (it as? JsonPrimitive)?.content }
                .joinToString(", ") { it.substringAfter('.').replace('_', ' ').replaceFirstChar { ch -> ch.uppercase() } }.ifBlank { "the inspection" }
            if (r.s("kind") == "media_replaced") "$by replaced a file in $where" else "$by added a file to $where"
        }
        r.s("kind") == "finished_without_files" -> {
            val n = c.s("missing").toIntOrNull() ?: 0
            val which = r.a("keys").mapNotNull { (it as? JsonPrimitive)?.content }.filter { it != "stage" }
                .map { it.substringAfter('.').replace('_', ' ').replaceFirstChar { ch -> ch.uppercase() } }
            "Finished by $by without $n file${if (n == 1) "" else "s"}" + (if (which.isEmpty()) "" else ": " + which.joinToString(", "))
        }
        r.s("kind") == "late_reviewed" -> "Late start reviewed by $by"
        r.s("kind") == "quick_reviewed" -> "Quick finish reviewed by $by"
        new("stage") == "completed" -> "Completed: every file uploaded"
        new("stage") == "submitted" -> "Submitted by $by"
        new("stage") == "in_progress" -> "Started by $by"
        new("stage") == "cancelled" -> "Cancelled by $by" + (new("cancel_reason")?.takeIf { it != "null" && it.isNotBlank() }
            ?.let { " · " + it.replace('_', ' ').replaceFirstChar { c -> c.uppercase() } } ?: "")
        new("stage") == "assigned" && old("stage") == "in_progress" -> "Force-released by $by"
        c["assigned_expert"] != null -> "${if (old("assigned_expert") != null && old("assigned_expert") != "null") "Reassigned" else "Assigned"} to ${env.labels.person(new("assigned_expert")?.toIntOrNull())} by $by"
        c["inspection_date"] != null || c["inspection_time"] != null -> "Rescheduled by $by"
        c["inspection_type"] != null -> "Type changed to ${env.labels.type(new("inspection_type").orEmpty())} by $by"
        c["conflict"] != null -> "Conflict resolved by $by"
        else -> "$by changed ${r.a("keys").joinToString(", ") { (it as JsonPrimitive).content.replace('_', ' ') }.ifBlank { "the booking" }}"
    }
}
