package `in`.carcid.vayu.ui.ops


import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import `in`.carcid.vayu.ui.expert.answered

import androidx.compose.material.icons.automirrored.outlined.List
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.border
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.ops.a
import `in`.carcid.vayu.core.ops.o
import `in`.carcid.vayu.core.s
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Review (web: ReviewTab): Key Checks, the overall word and ratings. Key Checks are plain text Ops
 * type over (editable once the expert submits); a dot marks what the answers suggest. Changes wait
 * for Save (Undo drops them), so a stray tap changes nothing. "Back to suggested" / "Reset to
 * automatic" drop an override.
 */
@Composable
fun ReviewScreen(env: OpsEnv, id: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val data = rememberBooking(env, id)
    // unsaved choices: "overall" -> word, "r:<key>" -> 1..5, "k:<key>" -> text; null means back to suggested / automatic
    var pending by remember(data?.insp?.rowVersion) { mutableStateOf(mapOf<String, Any?>()) }
    var saving by remember { mutableStateOf(false) }
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader("Review", data?.let { "${it.b.code} · ${it.b.customer}" }, onBack)
        val insp = data?.insp
        if (insp == null) { Text(if (data == null) "Loading…" else "Key Checks and ratings are worked out once the expert submits.", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp)); return }
        val s = insp.scores
        val edit = env.can("ratings.override") && !data.offline && !saving
        fun pick(k: String, v: Any?) { if (edit) pending = pending + (k to v) }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            if (data.offline) OfflineNote(rememberLoad(env, "bookings/$id").value)
            val kcs = data.raw["inspection"]?.a("key_checks").orEmpty().map { it as JsonObject }
            val kcEdit = edit && data.b.stage in setOf("submitted", "completed")
            if (kcs.isNotEmpty()) Section("Key Checks")
            if (kcs.isNotEmpty() && data.b.stage !in setOf("submitted", "completed"))
                Text("Editable once the expert submits.", fontSize = 13.sp, color = Vayu.colors.muted)
            kcs.forEach { kc ->
                val k = "k:" + kc.s("key")
                val v = s.o("key_checks").o(kc.s("key"))
                val reset = k in pending && pending[k] == null
                val text = if (k in pending) (pending[k] as String?) ?: v.s("auto") else v.s("value")
                Row(Modifier.padding(top = 12.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(kc.s("label"), fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, modifier = Modifier.weight(1f))
                    if (v.s("edited") == "true" && !reset) Text("Edited", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.warn)
                }
                SoftField(text, { t -> if (kcEdit) pending = if (t == v.s("value")) pending - k else pending + (k to t.take(500)) },
                    kc.s("label"), enabled = kcEdit)
                if (v.s("edited") == "true" && k !in pending) Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Automatic: ${v.s("auto").ifBlank { "empty" }}" + if (kcEdit) " · " else "", fontSize = 13.sp, color = Vayu.colors.muted,
                        maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    if (kcEdit) BackLink("Reset to automatic") { pick(k, null) }
                }
            }
            val overall = s.o("overall")
            Section("Overall")
            val sugWord = overall.s("suggested_word")
            val nowWord = if ("overall" in pending) (pending["overall"] as String?) ?: sugWord else overall.s("word")
            val mineOverall = if ("overall" in pending) pending["overall"] != null else overall.s("overridden") == "true"
            Picks(listOf("excellent", "good", "average", "bad"), nowWord, sugWord, columns = 2, label = { it.replaceFirstChar(Char::uppercase) }) { pick("overall", it) }
            if (mineOverall) BackLink("Back to suggested (${sugWord.replaceFirstChar(Char::uppercase)})") { pick("overall", null) }
            val cats = data.raw["inspection"]?.o("rating_config")?.a("categories").orEmpty().map { it as JsonObject }
            if (cats.isNotEmpty()) Section("Ratings")
            cats.forEach { c ->
                val k = "r:" + c.s("key")
                val r = s.o("ratings").o(c.s("key"))
                val sug = r.s("suggested").substringBefore(".")
                val now = if (k in pending) (pending[k] as Int?)?.toString() ?: sug else r.s("value").substringBefore(".")
                val mine = if (k in pending) pending[k] != null else r.s("overridden") == "true"
                Row(Modifier.padding(top = 12.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(c.s("label"), fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, modifier = Modifier.weight(1f))
                    if (mine) BackLink("Back to suggested ($sug)") { pick(k, null) } else Text("suggested $sug", fontSize = 13.sp, color = Vayu.colors.muted)
                }
                Picks((1..5).map { "$it" }, now, sug, columns = 5) { pick(k, it.toInt()) }
            }
            Spacer(Modifier.height(24.dp))
        }
        if (pending.isNotEmpty()) {
            HorizontalDivider(color = Vayu.colors.line)
            Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("${pending.size} change${if (pending.size == 1) "" else "s"} not saved", color = Vayu.colors.warn, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, modifier = Modifier.weight(1f))
                SoftButton("Undo", { pending = emptyMap() })
                PrimaryButton(if (saving) "Saving…" else "Save", {
                    scope.launch {
                        saving = true
                        val body = buildJsonObject {
                            if ("overall" in pending) put("overall", (pending["overall"] as String?)?.let { JsonPrimitive(it) } ?: JsonNull)
                            val rs = pending.filterKeys { it.startsWith("r:") }; val ks = pending.filterKeys { it.startsWith("k:") }
                            if (rs.isNotEmpty()) put("ratings", buildJsonObject { rs.forEach { (k, v) -> put(k.drop(2), (v as Int?)?.let { JsonPrimitive(it) } ?: JsonNull) } })
                            if (ks.isNotEmpty()) put("key_checks", buildJsonObject { ks.forEach { (k, v) -> put(k.drop(2), (v as String?)?.let { JsonPrimitive(it) } ?: JsonNull) } })
                            put("row_version", insp.rowVersion)
                        }
                        env.actions.send("PATCH", "inspections/${insp.id}/overrides", body, "Saved.", refused = { e ->
                            env.say(if (e.code == "STALE_INSPECTION") "Someone else changed it meanwhile; loaded their version." else e.message); env.refresh(); saving = false
                        }) { saving = false }
                    }
                }, enabled = !saving)
            }
        }
    }
}

/** Choices in equal columns; the chosen one filled, a small dot on the one the answers suggest. */
@Composable
private fun Picks(options: List<String>, chosen: String?, suggested: String?, columns: Int, label: (String) -> String = { it }, onPick: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        options.chunked(columns).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(if (columns > 2) 6.dp else 8.dp)) {
                row.forEach { o ->
                    val on = o == chosen
                    Box(Modifier.weight(1f).heightIn(min = 46.dp).clip(RoundedCornerShape(12.dp))
                        .background(if (on) Vayu.colors.primary else Vayu.colors.bg)
                        .border(1.dp, if (on) Vayu.colors.primary else Vayu.colors.line2, RoundedCornerShape(12.dp))
                        .selectable(selected = on, role = Role.RadioButton) { onPick(o) }
                        .semantics { if (o == suggested) contentDescription = "${label(o)}, suggested" }, contentAlignment = Alignment.Center) {
                        // a long choice wraps to two lines (then "…"), never a hard cut
                        Text(label(o), fontSize = 14.sp, fontWeight = FontWeight.Medium, maxLines = 2, overflow = TextOverflow.Ellipsis,
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp),
                            color = if (on) Vayu.colors.onPrimary else Vayu.colors.ink2)
                        if (o == suggested) Box(Modifier.align(Alignment.TopEnd).padding(6.dp).size(6.dp).clip(CircleShape).background(Vayu.colors.info))
                    }
                }
                repeat(columns - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}

@Composable
private fun BackLink(text: String, onClick: () -> Unit) = Text(text, color = Vayu.colors.info, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1,
    overflow = TextOverflow.Ellipsis, modifier = Modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClick = onClick).padding(vertical = 6.dp, horizontal = 2.dp))
