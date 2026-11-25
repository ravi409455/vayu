package `in`.carcid.vayu.ui.ops

import `in`.carcid.vayu.core.forms.Kind
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
import androidx.compose.runtime.LaunchedEffect
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
import `in`.carcid.vayu.core.forms.Filled
import `in`.carcid.vayu.core.forms.Page
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

/** One page in the page list: its part, its place in that part's scroll, its number across all three parts. */
data class NavPage(val part: String, val indexInPart: Int, val number: Int, val title: String, val isFilled: Boolean)

/** Every page of Check-in, Inspection and Wrap-up in order, numbered 1..N across all three. */
fun navPages(data: Loaded3, filled: Filled): List<NavPage> {
    var number = 0
    return PARTS.flatMap { part ->
        val answers = data.answers[part].orEmpty()
        filled.visiblePages(part).mapIndexed { i, pg ->
            NavPage(part, i, ++number, pg.title, pg.fields.any { it.answerable && filled.visible(part, it.key) && answered(answers[it.key]) })
        }
    }
}

/** One part's pages with the answers each shows (a check's own photo rides on the check's row); with onlyProblems, the problems alone. */
private fun partRows(data: Loaded3, filled: Filled, part: String, onlyProblems: Boolean): List<Pair<Page, List<Field>>> {
    val answers = data.answers[part].orEmpty()
    return filled.visiblePages(part).map { pg -> pg to pg.fields.filter { f -> f.answerable && filled.visible(part, f.key)
        && (f.config["photo_of"] as? String) !in pg.fields.map { it.key } && (!onlyProblems || problemOf(f, answers[f.key]) != null) } }
}

/** Where a page's header sits in the scroll (each shown page is one header and its rows); null when the page shows nothing. */
private fun headerIndex(rows: List<Pair<Page, List<Field>>>, page: Int): Int? =
    if (rows.getOrNull(page)?.second.isNullOrEmpty()) null else rows.take(page).filter { it.second.isNotEmpty() }.sumOf { 1 + it.second.size }

/**
 * The inspection's answers: Check-in · Inspection · Wrap-up tabs, each part's pages in one scroll.
 * The page list names every page of all three parts (numbered across them) and opens the page's
 * tab; "Only problems" counts and filters the whole inspection. Photos inline. Tap an answer to
 * change it (Ops).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AnswersScreen(env: OpsEnv, id: String, startPart: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val data = rememberBooking(env, id)
    var part by rememberSaveable { mutableStateOf(startPart) }
    var onlyProblems by rememberSaveable { mutableStateOf(false) }
    var jump by remember { mutableStateOf(false) }
    // a page picked in the page list: scrolled to once its tab is on screen
    var scrollTo by remember { mutableStateOf<Int?>(null) }
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
        val rows = partRows(data, filled, part, onlyProblems)
        val nav = navPages(data, filled)
        val before = nav.first { it.part == part }.number - 1     // pages in the tabs before this one
        val problems = parts.sumOf { partCounts(data, filled, it).second }
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
        LaunchedEffect(scrollTo, part) { scrollTo?.let { list.scrollToItem(it); scrollTo = null } }
        androidx.compose.foundation.lazy.LazyColumn(Modifier.weight(1f), state = list) {
            rows.forEachIndexed { pi, (pg, fs) ->
                if (fs.isEmpty()) return@forEachIndexed
                item(key = "p${pg.id}") {
                    Row(Modifier.padding(top = 12.dp).fillMaxWidth().background(Vayu.colors.soft).padding(horizontal = 20.dp, vertical = 8.dp)) {
                        Text(pg.title, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink2, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text("page ${before + pi + 1} of ${nav.size}", fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1, softWrap = false)
                    }
                }
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
            }
            if (rows.all { it.second.isEmpty() }) item {
                Text(if (onlyProblems) "No problems here." else "Nothing answered here.", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp))
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
        if (jump) VayuSheet({ jump = false }) {
            Text("Pages", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = Vayu.colors.ink, modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
            parts.forEach { p ->
                Text(names[p] ?: p, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.muted,
                    modifier = Modifier.padding(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 2.dp))
                val shown = if (p == part) rows else partRows(data, filled, p, onlyProblems)
                nav.filter { it.part == p }.forEach { pg ->
                    val at = headerIndex(shown, pg.indexInPart)
                    Row(Modifier.fillMaxWidth().clickable(enabled = at != null, role = Role.Button) { jump = false; part = p; scrollTo = at }
                        .padding(horizontal = 20.dp, vertical = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("${pg.number}. ${pg.title}", color = if (at == null) Vayu.colors.muted else Vayu.colors.ink, modifier = Modifier.weight(1f))
                        if (!pg.isFilled) Text("Not filled yet", fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1)
                    }
                }
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
                            env.actions.send("PATCH", "inspections/${data.insp.id}", buildJsonObject {
                                put("row_version", data.insp.rowVersion)
                                put("answers", buildJsonObject { put(p, buildJsonObject { put(f.key, JsonLogic.toJson(value)) }) })
                            }, "Saved.", refused = { e ->
                                error = when (e.code) {
                                    "STALE_INSPECTION" -> "Someone else saved this inspection meanwhile. Their version is loaded now; check and save again."
                                        .also { env.refresh() }
                                    "INVALID_ANSWERS" -> (e.extra["errors"] as? JsonObject)?.s(f.key)?.ifBlank { null }?.let { refusalText(it) } ?: e.message
                                    "FIELD_ACCESS" -> "You can't change this at this stage."
                                    else -> e.message
                                }
                            }) { editing = null }
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
    people = env.labels.people.map { Triple(it.id?.toString().orEmpty(), it.shown, it.role) })

private fun answerText(f: Field, v: Any?, env: OpsEnv): String = when (f.fieldType.kind) {
    Kind.CHOICE -> f.options.firstOrNull { it.key == v }?.label ?: shown(v)
    Kind.MULTI -> (v as? List<*>)?.joinToString(", ") { k -> f.options.firstOrNull { it.key == k }?.label ?: k.toString() } ?: "—"
    Kind.LIST -> (v as? String)?.let { if (f.config["list"] == "city") env.labels.city(it) else if (f.config["list"] == "car_make_model") env.labels.car(it) else it } ?: "—"
    Kind.FORM_CHOICE -> (v as? String)?.let(env.labels::type) ?: "—"
    Kind.USER -> (v as? Number)?.let { env.labels.person(it.toInt()) } ?: "—"
    Kind.NUMBER -> if (v == null) "—" else if (f.type == "currency") "₹" + shown(v) else shown(v) + ((f.config["unit"] as? String)?.let { " $it" } ?: "")
    Kind.WHEN -> (v as? String)?.let { when (f.type) {
        "date" -> dayLabel(it, env.today()).ifBlank { it }; "time" -> time12(it).ifBlank { it }; else -> whenStamp(it, env.today()) } } ?: "—"
    Kind.MEDIA -> (v as? List<*>)?.size?.let { n -> "$n ${if (f.type == "file") "file" else f.type}${if (n == 1) "" else "s"}" } ?: "—"
    Kind.SIGNATURE -> if (v == null) "—" else "Signed"
    Kind.TEXT, Kind.YES_NO, Kind.GPS, Kind.IMAGE, Kind.SYSTEM -> shown(v)
}
