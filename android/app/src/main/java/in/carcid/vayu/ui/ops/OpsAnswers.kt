package `in`.carcid.vayu.ui.ops

import `in`.carcid.vayu.core.ops.MediaItem
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import `in`.carcid.vayu.core.ARRIVED

import `in`.carcid.vayu.ui.expert.answered

import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.automirrored.outlined.List
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.foundation.selection.toggleable
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.border
import `in`.carcid.vayu.ui.expert.whenStamp
import `in`.carcid.vayu.ui.expert.time12
import `in`.carcid.vayu.ui.expert.dayLabel
import `in`.carcid.vayu.ui.components.VayuSheet
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.forms.Field
import `in`.carcid.vayu.core.forms.answerProblem
import `in`.carcid.vayu.core.forms.refusalText
import `in`.carcid.vayu.core.forms.PARTS
import `in`.carcid.vayu.core.ops.a
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.s
import `in`.carcid.vayu.core.rules.JsonLogic
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.expert.FieldEnv
import `in`.carcid.vayu.ui.expert.Question
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * The inspection's answers: Check-in · Inspection · Wrap-up, each part's pages in one scroll with a
 * jump list, "Only problems", photos inline. Tap an answer to change it (Ops).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AnswersScreen(env: OpsEnv, id: String, startPart: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val data = rememberBooking(env, id)
    var part by rememberSaveable { mutableStateOf(startPart) }
    var onlyProblems by rememberSaveable { mutableStateOf(false) }
    var jump by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<Pair<String, Field>?>(null) }
    var viewing by remember { mutableStateOf<MediaItem?>(null) }
    val list = androidx.compose.foundation.lazy.rememberLazyListState()
    val media = MediaItem.list(rememberLoad(env, "bookings/$id/media").value?.data?.rows().orEmpty()).filter { it.status in ARRIVED }
    val up = rememberOpsUploader(env, id, data, rememberLoad(env, "bookings/$id").value?.offline == false)
    viewing?.let { m ->
        val pf = PARTS.firstNotNullOfOrNull { p -> data?.trees?.get(p)?.fields?.firstOrNull { it.key == m.fieldKey }?.let { p to it } }
        val have = media.count { it.fieldKey == m.fieldKey }
        MediaViewer(env, m, fieldLabel = pf?.second?.label ?: m.fieldKey, onClose = { viewing = null },
            onReplace = pf?.takeIf { up.canReplace(it.second) }?.let { { viewing = null; up.pick(it.first, it.second, m.id) } },
            onAdd = pf?.takeIf { up.canAdd(it.first, it.second, have) }?.let { { viewing = null; up.pick(it.first, it.second, null) } })
        return
    }
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        Row(Modifier.fillMaxWidth().padding(start = 6.dp, end = 6.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back to the booking", tint = Vayu.colors.ink) }
            Text(data?.let { "${it.b.code} · ${it.b.customer}" }.orEmpty(), fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            IconButton(onClick = { jump = true }) { Icon(Icons.AutoMirrored.Outlined.List, contentDescription = "Jump to a page", tint = Vayu.colors.ink) }
        }
        val filled = data?.filled(env.today().toString())
        if (data?.insp == null || filled == null) {
            Text(if (data == null) "Loading…" else "No inspection yet.", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp)); return
        }
        val names = mapOf("start" to "Check-in", "inspection" to "Inspection", "end" to "Wrap-up")
        val parts = PARTS.filter { filled.visiblePages(it).isNotEmpty() }
        if (part !in parts) part = parts.firstOrNull() ?: return
        // part tabs with their counts
        Row(Modifier.padding(horizontal = 20.dp, vertical = 8.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Vayu.colors.soft).padding(4.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            parts.forEach { p ->
                val (n, bad) = partCounts(data, filled, p)
                val on = p == part
                Column(Modifier.weight(1f).heightIn(min = 44.dp).clip(RoundedCornerShape(9.dp)).background(if (on) Vayu.colors.bg else Color.Transparent)
                    .selectable(selected = on, role = Role.Tab) { part = p; scope.launch { list.scrollToItem(0) } },
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text(names[p] ?: p, fontSize = 14.sp, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        color = if (on) Vayu.colors.ink else Vayu.colors.muted)
                    Text("$n" + if (bad > 0) " · $bad problem${if (bad == 1) "" else "s"}" else "", fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        color = if (bad > 0) Vayu.colors.warn else Vayu.colors.muted)
                }
            }
        }
        val pages = filled.visiblePages(part)
        val answers = data.answers[part].orEmpty()
        // a check's own photos (photo_of) show on the check's row, not as a row of their own
        val photosOf = pages.flatMap { it.fields }.filter { it.isMedia && (it.config["photo_of"] as? String) != null }.groupBy({ it.config["photo_of"] as String }, { it.key })
        val rows = pages.map { pg -> pg to pg.fields.filter { f -> f.answerable && filled.visible(part, f.key) && (f.config["photo_of"] as? String) !in pg.fields.map { it.key }
            && (!onlyProblems || problemOf(f, answers[f.key]) != null) } }
        val problems = pages.sumOf { pg -> pg.fields.count { filled.visible(part, it.key) && problemOf(it, answers[it.key]) != null } }
        val pageOf = pages.flatMap { pg -> pg.fields.map { it.key to pg.title } }.toMap()
        if (problems > 0 || onlyProblems) Row(Modifier.padding(horizontal = 20.dp)) {
            Row(Modifier.heightIn(min = 40.dp).clip(RoundedCornerShape(20.dp)).background(if (onlyProblems) Vayu.colors.warnTint else Vayu.colors.bg)
                .border(1.dp, if (onlyProblems) Vayu.colors.warn else Vayu.colors.line2, RoundedCornerShape(20.dp))
                .toggleable(onlyProblems, role = Role.Switch) { onlyProblems = it }.padding(horizontal = 12.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Icon(Icons.Outlined.ErrorOutline, null, tint = if (onlyProblems) Vayu.colors.warn else Vayu.colors.ink, modifier = Modifier.size(16.dp))
                Text("Only problems · $problems", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = if (onlyProblems) Vayu.colors.warn else Vayu.colors.ink)
            }
        }
        OfflineNote(rememberLoad(env, "bookings/$id").value)
        // header index of each page, for the jump list
        val headerAt = mutableMapOf<Int, Int>()
        androidx.compose.foundation.lazy.LazyColumn(Modifier.weight(1f), state = list) {
            var i = 0
            rows.forEachIndexed { pi, (pg, fs) ->
                if (fs.isEmpty()) return@forEachIndexed
                headerAt[pi] = i
                item(key = "p${pg.id}") {
                    Row(Modifier.padding(top = 12.dp).fillMaxWidth().background(Vayu.colors.soft).padding(horizontal = 20.dp, vertical = 8.dp)) {
                        Text(pg.title, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink2, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text("page ${pi + 1} of ${pages.size}", fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1, softWrap = false)
                    }
                }
                i++
                items(fs, key = { "f${it.key}" }) { f ->
                    val v = answers[f.key]
                    val editable = env.can("submissions.edit") && !data.offline && !f.isMedia
                    val bad = problemOf(f, v)
                    Column(Modifier.padding(horizontal = 20.dp)) {
                        Row(Modifier.fillMaxWidth().heightIn(min = 60.dp).clickable(enabled = editable, role = Role.Button) { editing = part to f }.padding(vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Column(Modifier.weight(1f)) {
                                Text(f.label, fontSize = 12.sp, color = Vayu.colors.muted)
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    // a photo question counts what the server holds, even before the answer lists it
                                    val held = if (f.isMedia) media.count { it.fieldKey == f.key } else 0
                                    val shownText = if (f.isMedia && v == null && held > 0) "$held ${if (f.type == "file") "file" else f.type}${if (held == 1) "" else "s"}" else answerText(f, v, env)
                                    Text(shownText, color = Vayu.colors.ink, modifier = Modifier.weight(1f, fill = false))
                                    // the tag only when it adds something ("Minor" twice says nothing)
                                    if (bad != null && !bad.equals(shownText, ignoreCase = true)) Text(bad, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.warn,
                                        modifier = Modifier.clip(RoundedCornerShape(11.dp)).background(Vayu.colors.warnTint).padding(horizontal = 8.dp, vertical = 2.dp))
                                }
                            }
                            // photos of this answer, small, right here
                            val keys = setOf(f.key) + photosOf[f.key].orEmpty()
                            val mine = media.filter { it.fieldKey in keys }
                            mine.take(2).forEach { m -> MediaTile(env, m, size = 56.dp) { viewing = m } }
                        }
                        HorizontalDivider(color = Vayu.colors.line)
                    }
                }
                i += fs.size
            }
            if (rows.all { it.second.isEmpty() }) item {
                Text(if (onlyProblems) "No problems here." else "Nothing answered here.", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp))
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
        if (jump) VayuSheet({ jump = false }) {
            Text("Pages", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = Vayu.colors.ink, modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
            pages.forEachIndexed { pi, p ->
                val at = headerAt[pi]
                Text("${pi + 1}. ${p.title}", color = if (at == null) Vayu.colors.muted else Vayu.colors.ink,
                    modifier = Modifier.fillMaxWidth().clickable(enabled = at != null, role = Role.Button) { jump = false; scope.launch { list.scrollToItem(at ?: 0) } }
                        .padding(horizontal = 20.dp, vertical = 14.dp))
            }
            Spacer(Modifier.height(24.dp))
        }
        editing?.let { (p, f) ->
            var value by remember(f.key) { mutableStateOf(data.answers[p]?.get(f.key)) }
            var error by remember(f.key) { mutableStateOf<String?>(null) }
            VayuSheet({ editing = null }) {
                Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
                    Text(pageOf[f.key].orEmpty(), fontSize = 13.sp, color = Vayu.colors.muted)
                    Question(f, value, filled.required(p, f.key), false, error ?: answerProblem(f, value), false, opsFieldEnv(env)) { value = it; error = null }
                    Text("Was ${answerText(f, data.answers[p]?.get(f.key), env)}" +
                        (data.insp.expert?.let { ", answered by ${env.labels.person(it)}." } ?: "."), fontSize = 13.sp, color = Vayu.colors.muted)
                    Row(Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        SoftButton("Cancel", { editing = null }, Modifier.weight(1f))
                        PrimaryButton("Save", {
                            scope.launch {
                                try {
                                    env.data.act("PATCH", "inspections/${data.insp.id}", buildJsonObject {
                                        put("row_version", data.insp.rowVersion)
                                        put("answers", buildJsonObject { put(p, buildJsonObject { put(f.key, JsonLogic.toJson(value)) }) })
                                    })
                                    editing = null; env.say("Saved."); env.refresh()
                                } catch (e: ApiError) {
                                    error = when (e.code) {
                                        "STALE_INSPECTION" -> "Someone else saved this inspection meanwhile. Their version is loaded now; check and save again."
                                            .also { env.refresh() }
                                        "INVALID_ANSWERS" -> (e.extra["errors"] as? JsonObject)?.s(f.key)?.ifBlank { null }?.let { refusalText(it) } ?: e.message
                                        "FIELD_ACCESS" -> "You can't change this at this stage."
                                        else -> e.message
                                    }
                                }
                            }
                        }, Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

/** Field setup for Ops: lists, types and people from the labels; no camera here. */
fun opsFieldEnv(env: OpsEnv, lists: Map<String, List<Pair<String, String>>> = emptyMap()) = FieldEnv(
    locked = false,
    list = { k -> lists[k] ?: when (k) { "city" -> env.labels.cities.toList(); "car_make_model" -> env.labels.cars.toList(); else -> emptyList() } },
    types = env.labels.types.filter { it.third }.map { it.first to it.second },
    files = emptyMap(), now = { java.time.Instant.now() },
    onCamera = {}, onGallery = {}, onPickFile = {}, onSign = {}, onScan = {}, onOpenFile = { _, _ -> }, onLocate = { _, done -> done(null) },
    asset = { null },
    people = env.labels.people.map { Triple(it.s("id"), it.s("name").ifBlank { it.s("username") }, it.s("role")) })

private fun answerText(f: Field, v: Any?, env: OpsEnv): String = when (f.type) {
    "single_choice" -> f.options.firstOrNull { it.key == v }?.label ?: shown(v)
    "multi_choice" -> (v as? List<*>)?.joinToString(", ") { k -> f.options.firstOrNull { it.key == k }?.label ?: k.toString() } ?: "—"
    "master_list" -> (v as? String)?.let { if (f.config["list"] == "city") env.labels.city(it) else if (f.config["list"] == "car_make_model") env.labels.car(it) else it } ?: "—"
    "form_choice" -> (v as? String)?.let(env.labels::type) ?: "—"
    "user_picker" -> (v as? Number)?.let { env.labels.person(it.toInt()) } ?: "—"
    "number" -> if (v == null) "—" else shown(v) + ((f.config["unit"] as? String)?.let { " $it" } ?: "")
    "currency" -> if (v == null) "—" else "₹" + shown(v)
    "datetime" -> (v as? String)?.let { whenStamp(it, env.today()) } ?: "—"
    "date" -> (v as? String)?.let { dayLabel(it, env.today()).ifBlank { it } } ?: "—"
    "time" -> (v as? String)?.let { time12(it).ifBlank { it } } ?: "—"
    "photo", "video", "file" -> (v as? List<*>)?.size?.let { n -> "$n ${if (f.type == "file") "file" else f.type}${if (n == 1) "" else "s"}" } ?: "—"
    "signature" -> if (v == null) "—" else "Signed"
    else -> shown(v)
}
