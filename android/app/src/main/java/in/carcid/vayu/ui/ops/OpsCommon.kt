package `in`.carcid.vayu.ui.ops

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.ops.Loaded
import `in`.carcid.vayu.core.ops.OpsData
import `in`.carcid.vayu.core.ops.o
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.ops.s
import `in`.carcid.vayu.ui.components.OfflineStrip
import `in`.carcid.vayu.ui.components.StatusDot
import `in`.carcid.vayu.ui.components.Tone
import `in`.carcid.vayu.ui.expert.dayLabel
import `in`.carcid.vayu.ui.expert.time12
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/** A booking as the Ops screens read it (BookingSerializer). */
class Bk(val o: JsonObject) {
    val id = o.s("id")
    val code = o.s("booking_id")
    val stage = o.s("stage")
    val type = o.s("inspection_type")
    val expert: Int? = (o["assigned_expert"] as? JsonPrimitive)?.intOrNull
    val answers = o.o("answers")
    val rowVersion: Int = (o["row_version"] as? JsonPrimitive)?.intOrNull ?: 0
    val conflict = o.s("conflict")
    fun a(k: String) = answers.s(k)
    val customer get() = a("customer_name")
    val phone get() = a("customer_phone")
    val date get() = a("inspection_date").take(10)
    val time get() = a("inspection_time").take(5)
    val typeRejected: String? get() = (o["alerts"] as? kotlinx.serialization.json.JsonArray)?.map { it as JsonObject }
        ?.firstOrNull { it.s("code") == "TYPE_CHANGE_REJECTED" }?.s("detail")
    val live get() = stage !in setOf("completed", "cancelled")
}

fun opsStatus(b: Bk): Pair<String, Tone> = when {
    b.conflict.isNotEmpty() -> "Conflict" to Tone.BAD
    b.stage == "draft" -> "Unassigned" to Tone.WARN
    b.stage == "assigned" -> "To start" to Tone.NEUTRAL
    b.stage == "in_progress" -> "On site" to Tone.INFO
    b.stage == "submitted" -> "Uploading" to Tone.WARN
    b.stage == "completed" -> "Done" to Tone.OK
    else -> "Cancelled" to Tone.BAD
}

/** Names for keys: cities, car models, types, people. Loaded once, kept for offline. */
class Labels(val cities: Map<String, String> = emptyMap(), val cars: Map<String, String> = emptyMap(),
             val types: List<Triple<String, String, Boolean>> = emptyList(), val people: List<JsonObject> = emptyList()) {
    fun city(k: String) = cities[k] ?: k
    fun car(k: String) = cars[k] ?: k
    // a type that's no longer offered still reads as words ("ev" -> "EV", "used_car" -> "Used car")
    fun type(k: String) = types.firstOrNull { it.first == k }?.second
        ?: if (k.length <= 3) k.uppercase() else k.replace('_', ' ').replaceFirstChar { it.uppercase() }
    fun person(id: Int?) = people.firstOrNull { (it["id"] as? JsonPrimitive)?.intOrNull == id }?.let { it.s("name").ifBlank { it.s("username") } } ?: if (id == null) "" else "#$id"
    val experts get() = people.filter { it.s("role") == "expert" && it.s("is_active") != "false" }
    fun byUsername(u: String) = people.firstOrNull { it.s("username") == u }?.s("name")?.ifBlank { null } ?: u

    /** The server's "Type change to pdi rejected: expert started ev" in words, with type names. */
    fun typeRejected(detail: String): String {
        val m = Regex("Type change to (\\S+) rejected: expert started (\\S+)").find(detail) ?: return detail
        return "The expert had already started a ${type(m.groupValues[2])} inspection, so your change to ${type(m.groupValues[1])} wasn't applied."
    }

    companion object {
        suspend fun load(data: OpsData): Labels {
            // failures count as empty; cancellation is never swallowed (ApiError only)
            suspend fun <T> soft(empty: T, f: suspend () -> T): T = try { f() } catch (e: ApiError) { empty }
            suspend fun list(k: String) = soft(emptyMap()) { data.load("master-lists/$k/items").data.rows().associate { it.s("key") to it.s("label") } }
            val types = soft(emptyList()) { data.load("inspection-types").data.rows().map { Triple(it.s("key"), it.s("label"), it.s("available") != "false") } }
            val people = soft(emptyList()) { data.load("users").data.rows() }
            return Labels(list("city"), list("car_make_model"), types, people)
        }
    }
}

/** Everything an Ops screen needs from around it. */
data class OpsEnv(val me: Me, val data: OpsData, val labels: Labels, val today: () -> LocalDate,
             /** Bump to reload every screen (Refresh, after a change). */
             val tick: Int, val refresh: () -> Unit, val say: (String) -> Unit) {
    fun can(p: String) = me.can(p)
}

/** Load [path] (again whenever [tick] changes); null while the first load runs. */
@Composable
fun rememberLoad(env: OpsEnv, path: String?): State<Loaded?, String?> {
    var error by androidx.compose.runtime.remember(path) { mutableStateOf<String?>(null) }
    // the saved copy shows at once while the fresh one loads; "offline" only once loading fails
    val loaded by produceState<Loaded?>(path?.let { env.data.saved(it)?.copy(offline = false) }, path, env.tick) {
        if (path == null) return@produceState
        try { value = env.data.load(path); error = null } catch (e: ApiError) { error = e.message }
    }
    return State(loaded, error)
}

data class State<A, B>(val value: A, val error: B)

fun asOf(ms: Long): String = Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).toLocalTime().let { "%d:%02d".format(it.hour, it.minute) }

/** The always-visible offline strip of an Ops screen. */
@Composable
fun OfflineNote(l: Loaded?) {
    if (l?.offline == true) Box(Modifier.padding(top = 10.dp)) { OfflineStrip("Offline · as of ${asOf(l.savedAt)}. Changes need signal.") }
}

@Composable
fun SubHeader(title: String, sub: String? = null, onBack: () -> Unit, actions: @Composable () -> Unit = {}) {
    Row(Modifier.fillMaxWidth().padding(start = 6.dp, end = 6.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = Vayu.colors.ink) }
        Column(Modifier.weight(1f)) {
            if (sub != null) Text(sub, fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        actions()
    }
    Text(title, fontSize = 26.sp, lineHeight = 32.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink,
        modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp))
}

@Composable
fun Section(text: String) = Text(text.uppercase(), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.7.sp,
    color = Vayu.colors.muted, modifier = Modifier.padding(top = 22.dp, bottom = 4.dp))

/** One booking row: time (or day), customer, a sub line, status or an action. */
@Composable
fun BookingRow(b: Bk, detail: String, today: LocalDate, onOpen: () -> Unit, trailing: (@Composable () -> Unit)? = null) {
    val lead = if (b.date.isEmpty() || b.date == today.toString()) b.time else runCatching { LocalDate.parse(b.date).let { "${it.dayOfMonth} ${it.month.name.take(3).lowercase().replaceFirstChar(Char::uppercase)}" } }.getOrDefault("")
    Column(Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onOpen)) {
        Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(lead, modifier = Modifier.width(48.dp).padding(top = 1.dp), fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Vayu.colors.ink2, maxLines = 1, softWrap = false)
            Column(Modifier.weight(1f)) {
                // line 1: the name ("…" if long) and the status; line 2: the booking ID, never cut; line 3: type · who or where
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(b.customer.ifBlank { b.code }, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, maxLines = 1,
                        overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    trailing?.invoke() ?: opsStatus(b).let { StatusDot(it.first, it.second) }
                }
                Text(b.code, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Vayu.colors.ink2)
                if (detail.isNotBlank()) Text(detail, fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        HorizontalDivider(color = Vayu.colors.line)
    }
}

/** A small pill button; locked (with a padlock) when offline or not allowed. */
@Composable
fun PillButton(text: String, enabled: Boolean, onClick: () -> Unit) {
    Row(Modifier.heightIn(min = 36.dp).clip(RoundedCornerShape(18.dp)).background(if (enabled) Vayu.colors.primary else Vayu.colors.soft)
        .clickable(enabled = enabled, role = Role.Button, onClick = onClick).padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        if (!enabled) Icon(Icons.Outlined.Lock, contentDescription = null, tint = Vayu.colors.muted, modifier = Modifier.size(14.dp))
        Text(text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = if (enabled) Vayu.colors.onPrimary else Vayu.colors.muted)
    }
}

/** "Today, 3:30 pm". */
fun slot(b: Bk, today: LocalDate) = listOf(dayLabel(b.date, today), time12(b.time)).filter { it.isNotEmpty() }.joinToString(", ")

/** A readable answer value for lists and rows. */
fun shown(v: Any?): String = when (v) {
    null -> "—"
    is Boolean -> if (v) "Yes" else "No"
    // ponytail: no comma under 10,000, so a year reads 2022 (47,000 km still gets one)
    is Double -> if (v % 1.0 != 0.0) v.toString() else if (kotlin.math.abs(v) < 10_000) v.toLong().toString() else "%,d".format(v.toLong())
    is List<*> -> if (v.all { it is String && it.length == 36 }) "${v.size} file${if (v.size == 1) "" else "s"}" else v.joinToString(", ")
    is Map<*, *> -> if (v["lat"] != null) "%.4f, %.4f".format((v["lat"] as Number).toDouble(), (v["lng"] as Number).toDouble()) else v.toString()
    else -> v.toString()
}

fun JsonObject.int(k: String): Int? = (this[k] as? JsonPrimitive)?.contentOrNull?.toIntOrNull()
