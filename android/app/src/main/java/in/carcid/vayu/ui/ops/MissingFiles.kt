package `in`.carcid.vayu.ui.ops

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.FileUpload
import androidx.compose.material.icons.outlined.RadioButtonUnchecked
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.forms.Option
import `in`.carcid.vayu.core.s
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.VayuSheet
import `in`.carcid.vayu.ui.expert.SingleChoice
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Duration
import java.time.OffsetDateTime

/** One field the booking still waits for (from bookings/{id}/missing-files). */
data class MissingRow(val part: String, val key: String, val label: String, val count: Int, val required: Boolean,
                      val ids: List<String>, val of: Int, val page: String, val section: String) {
    val id get() = "$part.$key"

    companion object {
        fun parse(o: JsonObject) = MissingRow(o.s("part"), o.s("key"), o.s("label"), o.int("count") ?: 1,
            (o["required"] as? JsonPrimitive)?.booleanOrNull == true,
            (o["ids"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.content },
            o.int("of") ?: 1, o.s("page"), o.s("section"))
    }
}

val FINISH_REASONS = listOf("customer_waiting" to "Customer is waiting", "phone_lost" to "Phone lost or broken", "other" to "Other")

private fun plural(n: Int, w: String) = "$n $w${if (n == 1) "" else "s"}"

private fun ago(d: Duration): String {
    val min = d.toMinutes().coerceAtLeast(0)
    return when { min < 60 -> plural(min.toInt(), "min"); min < 48 * 60 -> "${min / 60} h"; else -> plural((min / 1440).toInt(), "day") }
}

/** What Ops read about the expert's phone: still sending (wait), or likely lost (upload here). */
fun phoneLine(expert: String, phone: JsonObject?, now: OffsetDateTime = OffsetDateTime.now()): String {
    val who = expert.ifBlank { "The expert" }
    val them = expert.ifBlank { "them" }
    val seen = phone?.s("last_seen_at")?.takeIf { it.isNotBlank() }?.let { runCatching { OffsetDateTime.parse(it) }.getOrNull() }
        ?: return "$who's phone is signed out or never checked in. Get the files from $them and upload them here."
    val files = phone.int("files") ?: 0
    val holds = if (files > 0) ", still holds ${plural(files, "file")}" else ""
    val gap = Duration.between(seen, now)
    return if (gap > Duration.ofHours(2)) "$who's phone: not seen for ${ago(gap)}$holds. It may be lost. Get the files from $them and upload them here."
    else "$who's phone: seen ${ago(gap)} ago$holds. Usually wait. If stuck, ask $them to open Vayu on Wi-Fi."
}

/** A booking waiting for the expert's files: one row per field with an Upload in place of the
 *  missing ones; Finish works at any time, required files missing too, with a reason. */
@Composable
fun MissingFilesCard(env: OpsEnv, id: String, data: Loaded3, expert: String, online: Boolean, onFinish: (Int, Int) -> Unit) {
    val load = rememberLoad(env, "bookings/$id/missing-files").value?.data as? JsonObject ?: return
    val rows = (load["missing"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonObject)?.let(MissingRow::parse) }
    // rows Ops uploaded here: "checking" until the server has verified them, then done with the time
    val mine = remember { mutableStateMapOf<String, Pair<String, MissingRow>>() }
    val up = rememberOpsUploader(env, id, data, online)
    LaunchedEffect(mine.size, rows.size) {           // our uploads are being checked: look again soon
        if (mine.isNotEmpty() && rows.any { it.id in mine }) { delay(5000); env.refresh() }
    }
    val done = mine.values.filter { (_, r) -> rows.none { it.id == r.id } }
    if (rows.isEmpty() && done.isEmpty()) return
    val total = rows.sumOf { it.count }
    val need = rows.filter { it.required }.sumOf { it.count }
    Column(Modifier.padding(top = 14.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Vayu.colors.warnTint)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(if (total > 0) "Waiting for ${plural(total, "file")}" + (if (need > 0) " · $need required" else "") else "Checking your uploads",
                fontWeight = FontWeight.Bold, color = Vayu.colors.warn)
            if (total > 0) Text(phoneLine(expert, load["phone"] as? JsonObject), color = Vayu.colors.warn, fontSize = 13.sp)
        }
        rows.sortedByDescending { it.required }.forEach { r ->
            HorizontalDivider(color = Vayu.colors.line)
            val f = data.trees[r.part]?.field(r.key)
            val checking = r.id in mine
            val noun = if (f?.type == "video") "video" else if (f?.type == "file") "file" else "photo"
            Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Icon(Icons.Outlined.RadioButtonUnchecked, null, Modifier.size(18.dp), tint = if (r.required) Vayu.colors.bad else Vayu.colors.muted)
                Column(Modifier.weight(1f)) {
                    Text(r.label, color = Vayu.colors.ink, fontWeight = FontWeight.SemiBold)
                    Text("${r.page} › ${r.section} · " + (if (checking) "checking your upload…" else "${r.count} of ${plural(r.of, noun)} not arrived") +
                        if (r.required) " · required" else "", color = Vayu.colors.muted, fontSize = 13.sp)
                }
                if (f != null && up.canReplace(f) && !checking) IconButton(onClick = {
                    up.fill(f, r.ids) { mine[r.id] = java.time.LocalTime.now().toString().take(5) to r }
                }) { Icon(Icons.Outlined.FileUpload, "Upload ${r.label}", tint = Vayu.colors.ink) }
            }
        }
        done.forEach { (at, r) ->
            HorizontalDivider(color = Vayu.colors.line)
            Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Icon(Icons.Outlined.CheckCircle, null, Modifier.size(18.dp), tint = Vayu.colors.ok)
                Column(Modifier.weight(1f)) {
                    Text(r.label, color = Vayu.colors.muted)
                    Text("Uploaded by you, $at", color = Vayu.colors.muted, fontSize = 13.sp)
                }
            }
        }
        if (total > 0) {
            HorizontalDivider(color = Vayu.colors.line)
            SoftButton("Finish without the missing files", { if (online) onFinish(total, need) }, Modifier.fillMaxWidth().padding(10.dp))
        }
    }
}

/** Finish now: the report is made with the usual stand-in image for what is missing. */
@Composable
fun FinishSheet(total: Int, need: Int, onClose: () -> Unit, onFinish: (JsonObject) -> Unit) {
    var reason by remember { mutableStateOf<String?>("customer_waiting") }
    var note by remember { mutableStateOf("") }
    VayuSheet(onClose) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Finish without ${plural(total, "file")}?", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink)
            Text((if (need > 0) "$need ${if (need == 1) "is" else "are"} required. " else "") +
                "The report is made now with the usual stand-in image in their place. If the files arrive later, the report goes out of date and you can regenerate it.",
                color = Vayu.colors.muted, fontSize = 14.sp)
            SingleChoice("Reason", FINISH_REASONS.map { Option(it.first, it.second, false, null) }, reason, false, { reason = it as String? }, forceList = true)
            SoftField(note, { note = it.take(300) }, "Add a note (optional)")
            PrimaryButton("Finish", {
                onFinish(buildJsonObject { put("reason", reason ?: "other"); if (note.isNotBlank()) put("note", note.trim()) })
            })
        }
    }
}
