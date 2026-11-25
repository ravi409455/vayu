package `in`.carcid.vayu.ui.ops

import androidx.compose.material.icons.outlined.Add
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.automirrored.outlined.List
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.foundation.selection.toggleable
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.border
import `in`.carcid.vayu.ui.expert.whenStamp
import `in`.carcid.vayu.ui.expert.time12
import `in`.carcid.vayu.ui.expert.dayLabel
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.layout.positionInParent
import androidx.compose.ui.layout.onGloballyPositioned
import `in`.carcid.vayu.ui.components.VayuSheet
import android.content.Intent
import android.graphics.BitmapFactory
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Autorenew
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.PlayCircle
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import `in`.carcid.vayu.BuildConfig
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.draft.transfer
import `in`.carcid.vayu.core.forms.Field
import `in`.carcid.vayu.core.forms.answerProblem
import `in`.carcid.vayu.core.forms.refusalText
import `in`.carcid.vayu.core.forms.Filled
import `in`.carcid.vayu.core.forms.FormTree
import `in`.carcid.vayu.core.forms.PARTS
import `in`.carcid.vayu.core.media.copyIn
import `in`.carcid.vayu.core.ops.a
import `in`.carcid.vayu.core.ops.o
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.ops.s
import `in`.carcid.vayu.core.rules.JsonLogic
import `in`.carcid.vayu.core.writeAtomically
import `in`.carcid.vayu.ui.components.Banner
import `in`.carcid.vayu.ui.components.ChoiceRow
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.Tone
import `in`.carcid.vayu.ui.expert.FieldEnv
import `in`.carcid.vayu.ui.expert.Question
import `in`.carcid.vayu.ui.expert.SingleChoice
import `in`.carcid.vayu.ui.expert.newFile
import `in`.carcid.vayu.ui.expert.sha256
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.File
import java.util.UUID

/** A booking with its current inspection and that inspection's form trees. */
class Loaded3(val b: Bk, val insp: JsonObject?, val trees: Map<String, FormTree?>, val raw: Map<String, JsonObject?>, val offline: Boolean,
              val insps: List<JsonObject> = emptyList()) {
    @Suppress("UNCHECKED_CAST")
    val answers: Map<String, Map<String, Any?>> get() = PARTS.associateWith { p ->
        (insp?.o("answers")?.get(p)?.let { JsonLogic.fromJson(it) } as? Map<String, Any?>).orEmpty() }
    fun filled(today: String) = trees["inspection"]?.let { Filled(trees, answers, JsonLogic.fromJson(b.answers) as Map<String, Any?>, today) }
}

/** The three forms an inspection was made with (check-in, inspection, wrap-up), raw and parsed. */
@Composable
fun rememberForms(env: OpsEnv, insp: JsonObject?): Map<String, JsonObject?> {
    val versions = mapOf("inspection" to insp?.int("form_version"), "start" to insp?.int("start_version"), "end" to insp?.int("end_version"))
    return versions.mapValues { (_, v) -> rememberLoad(env, v?.let { "form-versions/$it" }).value?.data as? JsonObject }
}

@Composable
fun rememberBooking(env: OpsEnv, id: String): Loaded3? {
    val b = rememberLoad(env, "bookings/$id").value
    val insps = rememberLoad(env, "bookings/$id/inspections").value?.data?.rows()
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

fun answered(v: Any?) = v != null && v != "" && !(v is List<*> && v.isEmpty())

/** How much of one part (start, inspection, end) is answered, and how many answers are problems. */
fun partCounts(data: Loaded3, filled: Filled, part: String): Pair<Int, Int> {
    val fs = filled.visiblePages(part).flatMap { it.fields }.filter { it.answerable && filled.visible(part, it.key) }
    val a = data.answers[part].orEmpty()
    return fs.count { answered(a[it.key]) } to fs.count { problemOf(it, a[it.key]) != null }
}

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
    var viewing by remember { mutableStateOf<JsonObject?>(null) }
    val list = androidx.compose.foundation.lazy.rememberLazyListState()
    val media = rememberLoad(env, "bookings/$id/media").value?.data?.rows().orEmpty().filter { it.s("status") in setOf("uploaded", "verified") }
    val up = rememberOpsUploader(env, id, data, rememberLoad(env, "bookings/$id").value?.offline == false)
    viewing?.let { m ->
        val pf = PARTS.firstNotNullOfOrNull { p -> data?.trees?.get(p)?.fields?.firstOrNull { it.key == m.s("field_key") }?.let { p to it } }
        val have = media.count { it.s("field_key") == m.s("field_key") }
        MediaViewer(env, m, fieldLabel = pf?.second?.label ?: m.s("field_key"), onClose = { viewing = null },
            onReplace = pf?.takeIf { up.canReplace(it.second) }?.let { { viewing = null; up.pick(it.first, it.second, m.s("id")) } },
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
                                    val held = if (f.isMedia) media.count { it.s("field_key") == f.key } else 0
                                    val shownText = if (f.isMedia && v == null && held > 0) "$held ${if (f.type == "file") "file" else f.type}${if (held == 1) "" else "s"}" else answerText(f, v, env)
                                    Text(shownText, color = Vayu.colors.ink, modifier = Modifier.weight(1f, fill = false))
                                    // the tag only when it adds something ("Minor" twice says nothing)
                                    if (bad != null && !bad.equals(shownText, ignoreCase = true)) Text(bad, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.warn,
                                        modifier = Modifier.clip(RoundedCornerShape(11.dp)).background(Vayu.colors.warnTint).padding(horizontal = 8.dp, vertical = 2.dp))
                                }
                            }
                            // photos of this answer, small, right here
                            val keys = setOf(f.key) + photosOf[f.key].orEmpty()
                            val mine = media.filter { it.s("field_key") in keys }
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
                        (data.insp.int("expert")?.let { ", answered by ${env.labels.person(it)}." } ?: "."), fontSize = 13.sp, color = Vayu.colors.muted)
                    Row(Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        SoftButton("Cancel", { editing = null }, Modifier.weight(1f))
                        PrimaryButton("Save", {
                            scope.launch {
                                try {
                                    env.data.act("PATCH", "inspections/${data.insp.s("id")}", buildJsonObject {
                                        put("row_version", data.insp.int("row_version") ?: 0)
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

/**
 * A file fetched through its signed link and kept in the cache folder. [preview]: the server's small
 * preview when it has one (tiles; a phone photo is ~0.5 MB, its preview a few KB), else the file.
 */
suspend fun mediaBytes(env: OpsEnv, dir: File, id: String, preview: Boolean = false): File? = withContext(Dispatchers.IO) {
    // the file name comes from the server's ID: only a real ID, never a path
    if (runCatching { java.util.UUID.fromString(id) }.isFailure) return@withContext null
    val full = File(dir, "media-$id")
    if (full.exists()) return@withContext full                  // the whole file serves as its own preview
    val f = if (preview) File(dir, "media-$id-p") else full
    if (f.exists()) return@withContext f
    try {
        val links = env.data.api.get("media/$id/url") as JsonObject
        val url = links.s("preview_url").takeIf { preview && it.isNotBlank() } ?: links.s("url")
        writeAtomically(if (url == links.s("url")) full else f, env.data.api.download(url))
        if (url == links.s("url")) full else f
    } catch (e: kotlin.coroutines.cancellation.CancellationException) { throw e } catch (e: Exception) { null }
}

/** [thumb] off the main thread (a 2000-px decode stutters the list on a low-end phone). */
private suspend fun decoded(f: File, size: Int): ImageBitmap? = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Default) { thumb(f, size) }

private fun thumb(f: File, size: Int): ImageBitmap? = runCatching {
    val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(f.path, o)
    var s = 1
    while (o.outWidth / (s * 2) >= size && o.outHeight / (s * 2) >= size) s *= 2
    BitmapFactory.decodeFile(f.path, BitmapFactory.Options().apply { inSampleSize = s })?.asImageBitmap()
}.getOrNull()

/**
 * Ops add a file to a submitted inspection, or replace one (the old one stays as history only
 * Admin opens; nobody deletes): start the upload saying what it replaces, send it, attach it.
 */
class OpsUploader(val pick: (part: String, f: Field, replaces: String?) -> Unit,
                  val canAdd: (part: String, f: Field, have: Int) -> Boolean, val canReplace: (Field) -> Boolean)

@Composable
fun rememberOpsUploader(env: OpsEnv, id: String, data: Loaded3?, online: Boolean): OpsUploader {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var target by remember { mutableStateOf<Triple<String, Field, String?>?>(null) }
    // only once the expert has submitted, and never on a cancelled booking
    val may = env.can("media.manage") && online && data?.insp?.s("status") == "submitted" && data.b.stage != "cancelled"
    suspend fun upload(f: Field, file: File, type: String, replaces: String?) {
        var loose: String? = null
        try {
            val hash = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { sha256(file) }
            val init = env.data.api.mediaInitiate(id, UUID.randomUUID().toString(), f.key, f.type, type, file.length(), hash, "gallery", replaces)
            loose = init.s("id")
            if (!transfer(env.data.api, init, file, type)) { env.say("The file arrived damaged. Try again."); return }
            env.data.act("POST", "media/$loose/attach", buildJsonObject { if (replaces != null) put("replaces", replaces) })
            loose = null
            env.say(if (replaces != null) "Replaced." else "Added."); env.refresh()
        } catch (e: ApiError) { env.say(e.message) } finally {
            file.delete()
            // an upload that never got attached is taken back, so it can't pile up
            loose?.let { l -> try { env.data.act("DELETE", "media/$l") } catch (e: ApiError) { } }
        }
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        val (_, f, replaces) = target ?: return@rememberLauncherForActivityResult
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val tmp = newFile(ctx.cacheDir, "up")
            val type = withContext(Dispatchers.IO) { copyIn(ctx, uri, tmp) } ?: return@launch
            upload(f, tmp, type, replaces)
        }
    }
    fun types(f: Field): Array<String> = when (f.type) {
        "video" -> arrayOf("video/*")
        "file" -> ((f.config["allowed"] as? List<*>)?.map { it.toString() } ?: listOf("image", "pdf")).map { if (it == "pdf") "application/pdf" else "image/*" }.toTypedArray()
        else -> arrayOf("image/*")
    }
    return OpsUploader(
        pick = { p, f, r -> target = Triple(p, f, r); picker.launch(types(f)) },
        canAdd = { _, f, have -> may && f.config["ops_upload"] != false && have < f.maxCount },
        canReplace = { f -> may && f.config["ops_upload"] != false })
}

/** Photos and videos by section: view full screen, play, add, replace, delete, share a ZIP. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MediaScreen(env: OpsEnv, id: String, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val data = rememberBooking(env, id)
    val list = rememberLoad(env, "bookings/$id/media")
    val items = list.value?.data?.rows().orEmpty().filter { it.s("status") in setOf("uploaded", "verified") }
    var open by remember { mutableStateOf<JsonObject?>(null) }
    val online = list.value?.offline == false
    val fields = PARTS.flatMap { p -> data?.trees?.get(p)?.pages.orEmpty().flatMap { pg -> pg.sections.flatMap { s -> s.fields.filter { it.isMedia }.map { Triple(p, s.title, it) } } } }
    val up = rememberOpsUploader(env, id, data, online)
    open?.let { m ->
        val f = fields.firstOrNull { it.third.key == m.s("field_key") }
        val have = items.count { it.s("field_key") == m.s("field_key") }
        MediaViewer(env, m, fieldLabel = f?.third?.label ?: m.s("field_key"), onClose = { open = null },
            onReplace = f?.takeIf { up.canReplace(it.third) }?.let { { open = null; up.pick(it.first, it.third, m.s("id")) } },
            onAdd = f?.takeIf { up.canAdd(it.first, it.third, have) }?.let { { open = null; up.pick(it.first, it.third, null) } })
        return
    }
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader("Photos and videos", data?.let { "${it.b.code} · ${it.b.customer}" }, onBack) {
            if (env.can("media.download")) IconButton(onClick = {
                scope.launch {
                    try {
                        val r = env.data.act("POST", "bookings/$id/media-zip", buildJsonObject { put("kind", "image") }) as JsonObject
                        val link = BuildConfig.API_URL.removeSuffix("api/v1/") + "zip/" + r.s("url").substringAfter("/zips/")
                        ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
                            .putExtra(Intent.EXTRA_TEXT, "Photos for ${data?.b?.code}: $link"), "Share the photos"))
                    } catch (e: ApiError) { env.say(e.message) }
                }
            }, enabled = online) { Icon(Icons.Outlined.Share, contentDescription = "Share all photos as a ZIP", tint = if (online) Vayu.colors.ink else Vayu.colors.muted) }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            OfflineNote(list.value)
            Text("${items.count { it.s("kind") == "photo" }} photos · ${items.count { it.s("kind") == "video" }} videos", color = Vayu.colors.muted)
            // files deleted after the storage time Admin set (Settings) are gone for good: say so
            val deleted = list.value?.data?.rows().orEmpty().count { it.s("status") == "purged" }
            if (deleted > 0) Text("$deleted ${if (deleted == 1) "file was" else "files were"} deleted after the storage time set in Settings.",
                color = Vayu.colors.muted, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp))
            val filled = data?.filled(env.today().toString())
            fields.groupBy { it.second }.forEach { (section, fs) ->
                val here = items.filter { m -> fs.any { it.third.key == m.s("field_key") } }
                val addable = fs.filter { (p, _, f) -> filled?.visible(p, f.key) != false && up.canAdd(p, f, here.count { it.s("field_key") == f.key }) }
                val canAdd = addable.isNotEmpty()
                // a section with nothing to show or add is left out
                if (here.isEmpty() && !canAdd) return@forEach
                Section(section)
                // as many ~76 dp columns as fit, stretched to share the whole width (a wide phone gets more, no empty strip)
                androidx.compose.foundation.layout.BoxWithConstraints(Modifier.fillMaxWidth()) {
                val cols = ((maxWidth + 8.dp) / 84.dp).toInt().coerceAtLeast(3)
                // whole pixels: a tile a fraction too wide would push the last one to the next row
                val tile = with(androidx.compose.ui.platform.LocalDensity.current) { ((constraints.maxWidth - 8.dp.roundToPx() * (cols - 1)) / cols).toDp() }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), maxItemsInEachRow = cols) {
                    here.forEach { m -> MediaTile(env, m, size = tile) { open = m } }
                    // an add tile only where Ops may add, the field shows in this inspection, and it has room
                    addable.forEach { (p, _, f) ->
                        Box(Modifier.size(tile).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.soft)
                            .clickable(role = Role.Button) { up.pick(p, f, null) }
                            .semantics { contentDescription = "Add to ${f.label}" }, contentAlignment = Alignment.Center) {
                            Text("+ ${f.label}", fontSize = 11.sp, color = Vayu.colors.ink2, modifier = Modifier.padding(4.dp), maxLines = 3)
                        }
                    }
                }
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun MediaTile(env: OpsEnv, m: JsonObject, size: androidx.compose.ui.unit.Dp = 76.dp, onClick: () -> Unit) {
    val ctx = LocalContext.current
    val img by produceState<ImageBitmap?>(null, m.s("id")) {
        if (m.s("kind") in setOf("photo", "signature")) value = mediaBytes(env, ctx.cacheDir, m.s("id"), preview = true)?.let { decoded(it, 160) }
    }
    Box(Modifier.size(size).clip(RoundedCornerShape(if (size < 76.dp) 10.dp else 12.dp)).background(Vayu.colors.illo).clickable(role = Role.Button, onClick = onClick)
        .semantics { contentDescription = "${m.s("kind")} ${m.s("field_key")}" }, contentAlignment = Alignment.Center) {
        img?.let { Image(it, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize()) }
        if (m.s("kind") == "video") Icon(Icons.Outlined.PlayCircle, null, tint = Color.White, modifier = Modifier.size(30.dp))
    }
}

@Composable
private fun MediaViewer(env: OpsEnv, m: JsonObject, fieldLabel: String, onClose: () -> Unit, onReplace: (() -> Unit)? = null, onAdd: (() -> Unit)? = null) {
    BackHandler(onBack = onClose)
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    // null while loading; false when it couldn't be loaded
    val img by produceState<Any?>(null, m.s("id")) {
        if (m.s("kind") in setOf("photo", "signature")) value = mediaBytes(env, ctx.cacheDir, m.s("id"))?.let { decoded(it, 2000) } ?: false
    }
    var videoUrl by remember { mutableStateOf<String?>(null) }
    var scale by remember { mutableStateOf(1f) }
    var pan by remember { mutableStateOf(androidx.compose.ui.geometry.Offset.Zero) }
    Column(Modifier.fillMaxSize().background(Color.Black).safeDrawingPadding()) {
        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            `in`.carcid.vayu.ui.expert.CloseButton("Back", onClose, tint = Color.White)
            Text(fieldLabel, color = Color.White, fontWeight = FontWeight.Bold)
        }
        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            when {
                // pinch to zoom, drag to look around
                img is ImageBitmap -> Image(img as ImageBitmap, fieldLabel, contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize()
                    .pointerInput(Unit) { detectTransformGestures { _, p, z, _ -> scale = (scale * z).coerceIn(1f, 5f); pan = if (scale == 1f) androidx.compose.ui.geometry.Offset.Zero else pan + p } }
                    .graphicsLayer(scaleX = scale, scaleY = scale, translationX = pan.x, translationY = pan.y))
                img == false -> Text("Couldn't load this photo. Check the signal and try again.", color = Color.White, modifier = Modifier.padding(24.dp))
                m.s("kind") in setOf("photo", "signature") -> Text("Loading…", color = Color.White)
                videoUrl != null -> AndroidView(factory = { c -> android.widget.VideoView(c).apply {
                    setMediaController(android.widget.MediaController(c).also { it.setAnchorView(this) })
                    setVideoURI(android.net.Uri.parse(videoUrl)); setOnPreparedListener { start() }
                    setOnErrorListener { _, _, _ -> env.say("Couldn't play this video."); true }
                } }, onRelease = { it.stopPlayback() }, modifier = Modifier.fillMaxSize())
                else -> Column(horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.clickable(role = Role.Button) {
                        scope.launch {
                            try {
                                val url = (env.data.api.get("media/${m.s("id")}/url") as JsonObject).s("url")
                                // videos play here; other files open in an app that can show them
                                if (m.s("kind") == "video") videoUrl = url
                                else try { ctx.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url))) }
                                    catch (e: android.content.ActivityNotFoundException) { env.say("No app on this phone can open this file.") }
                            } catch (e: ApiError) { env.say(e.message) }
                        }
                    }) {
                    Icon(Icons.Outlined.PlayCircle, null, tint = Color.White, modifier = Modifier.size(72.dp))
                    Text(if (m.s("kind") == "video") "Play" else "Open", color = Color.White)
                }
            }
        }
        // nobody deletes a submitted file: replace it (the old one stays as history) or add another
        if (onReplace != null || onAdd != null) Row(Modifier.fillMaxWidth().padding(20.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
            onReplace?.let { r ->
                Column(Modifier.clickable(role = Role.Button, onClick = r).padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Outlined.Autorenew, null, tint = Color.White); Text("Replace", color = Color.White)
                }
            }
            onAdd?.let { a ->
                Column(Modifier.clickable(role = Role.Button, onClick = a).padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Outlined.Add, null, tint = Color.White); Text("Add", color = Color.White)
                }
            }
        }
    }
}

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
    var pending by remember(data?.insp?.int("row_version")) { mutableStateOf(mapOf<String, Any?>()) }
    var saving by remember { mutableStateOf(false) }
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader("Review", data?.let { "${it.b.code} · ${it.b.customer}" }, onBack)
        val insp = data?.insp
        if (insp == null) { Text(if (data == null) "Loading…" else "Key Checks and ratings are worked out once the expert submits.", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp)); return }
        val s = insp.o("scores")
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
                            put("row_version", insp.int("row_version") ?: 0)
                        }
                        try { env.data.act("PATCH", "inspections/${insp.s("id")}/overrides", body); env.say("Saved."); env.refresh() }
                        catch (e: ApiError) { env.say(if (e.code == "STALE_INSPECTION") "Someone else changed it meanwhile; loaded their version." else e.message); env.refresh() }
                        finally { saving = false }
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

/** Payment as Ops read it: "₹1,499 · UPI" / "Taken at wrap-up" (mode names from the wrap-up form). */
fun paymentText(data: Loaded3): Pair<String, String> {
    val end = data.answers["end"].orEmpty()
    val mode = end["payment_mode"]?.let { k -> data.trees["end"]?.fields?.firstOrNull { it.key == "payment_mode" }?.options?.firstOrNull { it.key == k }?.label ?: k.toString() }
    return when (end["taking_payment"]) {
        true -> listOfNotNull((end["payment_amount"] as? Number)?.let { "₹" + shown(it.toDouble()) }, mode).joinToString(" · ").ifBlank { "Taken" } to "Taken at wrap-up"
        false -> "Pay later" to "No payment taken"
        else -> "Not answered yet" to ""
    }
}

/**
 * The PDF report on the booking screen. It updates by itself after any change (the card says
 * "Updating…" and checks again until it's done); Open · Share · Check link. Opening downloads it
 * through the server (logged); sharing the PDF or the check link is logged too.
 */
@Composable
fun ReportCard(env: OpsEnv, id: String, b: Bk) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val r = rememberLoad(env, "bookings/$id/report")
    var rep by remember(r.value) { mutableStateOf(r.value?.data as? JsonObject) }
    val online = r.value?.offline != true
    val updating = rep?.s("updating") == "true"
    // while a new revision is being made, look again every few seconds until it's done
    LaunchedEffect(updating, id) {
        while (rep?.s("updating") == "true") {
            kotlinx.coroutines.delay(4000)
            val now = try { env.data.api.get("bookings/$id/report") as? JsonObject } catch (e: ApiError) { null } ?: continue
            rep = now
            if (now.s("updating") != "true") env.refresh()
        }
    }
    // one download per revision: kept on the phone until a newer one is made
    suspend fun file(): File? {
        if (rep?.s("url").isNullOrBlank()) return null
        val code = b.code.filter { it.isLetterOrDigit() || it == '-' }
        val dir = File(ctx.cacheDir, "reports").apply { mkdirs() }
        // kept only under a real revision number and its time; without them, always a fresh download
        val rev = rep?.s("revision")?.takeIf { it.isNotBlank() && it.all(Char::isDigit) }
        val made = rep?.s("generated_at").orEmpty().filter { it.isDigit() }
        // our own name, never the server's (no path tricks in the cache folder)
        val f = File(dir, if (rev != null && made.isNotEmpty()) "report-$code-$rev-$made.pdf" else "report-$code-latest.pdf")
        if (rev != null && made.isNotEmpty() && f.exists()) return f
        return withContext(Dispatchers.IO) {
            try {
                dir.listFiles { x -> x.name.startsWith("report-$code-") }?.forEach { it.delete() }
                writeAtomically(f, env.data.api.reportPdf(id)); f
            } catch (e: ApiError) { null }
        }
    }
    fun uriOf(f: File) = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
    // who passed it on, and how, goes on the booking's history first; no record, no share
    suspend fun logShared(how: String): Boolean = try {
        env.data.act("POST", "bookings/$id/report/shared", buildJsonObject { put("how", how) }); true
    } catch (e: ApiError) { env.say("Couldn't record the share. Check the signal and try again."); false }
    Column(Modifier.padding(top = 8.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Vayu.colors.soft).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val failed = rep?.s("status") == "failed"
        Text(when {
            b.conflict.isNotEmpty() -> "Waits for your choice above"
            rep == null -> if (b.stage == "completed") "Being made" else "Made when the booking is completed"
            updating -> "Updating…"
            failed -> "Couldn't be made · tried again by itself"
            rep!!.s("status") == "ready" -> "Ready" + (rep!!.s("generated_at").takeIf { it.isNotBlank() }?.let { " · made ${whenStamp(it, env.today()).replaceFirstChar { c -> c.lowercase() }}" } ?: "")
            else -> "Being made"
        }, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
        if (failed && rep?.s("error")?.isNotBlank() == true) Note(rep!!.s("error"), Vayu.colors.badTint)
        if (rep?.s("url")?.isNotBlank() == true) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CardButton("Open", Modifier.weight(1f), online) { scope.launch { file()?.let { ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uriOf(it), "application/pdf").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)) } ?: env.say("Couldn't download the report.") } }
            CardButton("Share", Modifier.weight(1f), online) { scope.launch {
                file()?.let {
                    if (!logShared("pdf")) return@launch
                    ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("application/pdf")
                        .putExtra(Intent.EXTRA_STREAM, uriOf(it)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Share the report"))
                } ?: env.say("Couldn't download the report.")
            } }
            if (rep!!.s("verify_url").isNotBlank()) CardButton("Check link", Modifier.weight(1f), online) { scope.launch {
                if (!logShared("check_link")) return@launch
                ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, rep!!.s("verify_url")), "Share the check link"))
            } }
        }
    }
}

/** A button on a grey card: white with a border, one line. */
@Composable
private fun CardButton(text: String, modifier: Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    Box(modifier.heightIn(min = 48.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.bg)
        .border(1.dp, Vayu.colors.line2, RoundedCornerShape(12.dp)).clickable(enabled = enabled, role = Role.Button, onClick = onClick)
        .padding(horizontal = 6.dp), contentAlignment = Alignment.Center) {
        Text(text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
            color = if (enabled) Vayu.colors.ink else Vayu.colors.muted)
    }
}

@Composable
private fun Note(text: String, bg: Color) = Text(text, fontSize = 13.sp, color = Vayu.colors.ink2,
    modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(bg).padding(12.dp))

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

/** New booking or edit: the booking form as the Admin built it. */
@Composable
fun BookingFormScreen(env: OpsEnv, id: String?, onBack: () -> Unit, onSaved: (String, Boolean) -> Unit) {
    val scope = rememberCoroutineScope()
    val forms = rememberLoad(env, "forms").value?.data?.rows().orEmpty()
    val version = forms.firstOrNull { it.s("type") == "booking" && it.s("is_active") != "false" }?.o("published_version")?.int("id")
    val tree = rememberLoad(env, version?.let { "form-versions/$it" }).value?.data?.let { FormTree.parse(it as JsonObject) }
    val existing = id?.let { rememberLoad(env, "bookings/$it").value?.data?.let { d -> Bk(d as JsonObject) } }
    val listKeys = tree?.fields?.filter { it.type == "master_list" }?.mapNotNull { it.config["list"] as? String }?.distinct().orEmpty()
    val lists = listKeys.associateWith { k -> rememberLoad(env, "master-lists/$k/items").value?.data?.rows().orEmpty().filter { it.s("archived") != "true" }.map { it.s("key") to it.s("label") } }
    @Suppress("UNCHECKED_CAST")
    var values by remember(existing?.rowVersion) { mutableStateOf((existing?.answers?.let { JsonLogic.fromJson(it) } as? Map<String, Any?>).orEmpty()) }
    var changed by remember(existing?.rowVersion) { mutableStateOf(setOf<String>()) }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var busy by remember { mutableStateOf(false) }
    val scroll = rememberScrollState()
    val where = remember { mutableMapOf<String, Int>() }
    var refused by remember { mutableStateOf(0) }
    BackHandler(onBack = onBack)
    fun save(assign: Boolean) = scope.launch {
        busy = true
        try {
            val body = if (id == null) buildJsonObject { put("answers", JsonLogic.toJson(values)) }
                else buildJsonObject { put("row_version", existing!!.rowVersion); put("answers", JsonLogic.toJson(values.filterKeys { it in changed })) }
            val r = env.data.act(if (id == null) "POST" else "PATCH", if (id == null) "bookings" else "bookings/$id", body) as JsonObject
            env.say("Saved."); env.refresh(); onSaved(r.s("id"), assign)
        } catch (e: ApiError) {
            errors = (e.extra["errors"] as? JsonObject)?.mapValues { (it.value as? JsonPrimitive)?.content ?: "Check this." } ?: emptyMap()
            if (e.code == "DUPLICATE_BOOKING_ID") errors = errors + ("booking_id" to e.message)
            refused++
            if (e.code.startsWith("STALE")) { env.refresh(); env.say("Someone else saved this booking meanwhile; their version is loaded.") }
            else if (errors.isEmpty()) env.say(e.message)
        } finally { busy = false }
    }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader(if (id == null) "New booking" else "Edit booking", existing?.code, onBack)
        if (tree == null) { Text("Loading the booking form…", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp)); return }
        // the booking form's own answers are "booking" in its rules
        val filled = Filled(mapOf("booking" to tree), emptyMap(), values, env.today().toString())
        // after a refused save: say so and bring the first marked question into view
        LaunchedEffect(refused) {
            if (refused == 0 || errors.isEmpty()) return@LaunchedEffect
            env.say(if (errors.size == 1) "Fix the question marked in red." else "Fix the ${errors.size} questions marked in red.")
            errors.keys.mapNotNull { where[it] }.minOrNull()?.let { scroll.animateScrollTo(it) }
        }
        Column(Modifier.weight(1f).verticalScroll(scroll).padding(horizontal = 20.dp)) {
            val fe = opsFieldEnv(env, lists)
            val shown = tree.pages.flatMap { it.sections }.map { s ->
                s to s.fields.filter { it.answerable && filled.visible("booking", it.key) && it.key != "assigned_expert" && !(id != null && it.key == "inspection_type") }
            }.filter { it.second.isNotEmpty() }
            shown.forEach { (s, fs) ->
                // a lone section needs no heading ("Section 1")
                if (shown.size > 1) Section(s.title)
                fs.forEach { f ->
                    Box(Modifier.onGloballyPositioned { where[f.key] = it.positionInParent().y.toInt() }) {
                        Question(f, values[f.key], filled.required("booking", f.key), false,
                            errors[f.key]?.let { refusalText(it) } ?: answerProblem(f, values[f.key]) ?: filled.checkMessage("booking", f.key), false, fe) { v ->
                            values = values + (f.key to v); changed = changed + f.key; errors = errors - f.key
                        }
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
        }
        Row(Modifier.padding(horizontal = 20.dp, vertical = 14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            when {
                id != null -> PrimaryButton(if (busy) "Saving…" else "Save changes", { save(false) }, Modifier.weight(1f), enabled = !busy && changed.isNotEmpty())
                env.can("bookings.assign") -> {
                    SoftButton("Save", { save(false) }, Modifier.weight(1f))
                    PrimaryButton(if (busy) "Saving…" else "Save and assign", { save(true) }, Modifier.weight(1f), enabled = !busy)
                }
                else -> PrimaryButton(if (busy) "Saving…" else "Save", { save(false) }, Modifier.weight(1f), enabled = !busy)
            }
        }
    }
}
