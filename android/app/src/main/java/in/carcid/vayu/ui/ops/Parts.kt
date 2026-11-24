package `in`.carcid.vayu.ui.ops

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
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.File
import java.util.UUID

/** A booking with its current inspection and that inspection's form trees. */
class Loaded3(val b: Bk, val insp: JsonObject?, val trees: Map<String, FormTree?>, val raw: Map<String, JsonObject?>, val offline: Boolean) {
    @Suppress("UNCHECKED_CAST")
    val answers: Map<String, Map<String, Any?>> get() = PARTS.associateWith { p ->
        (insp?.o("answers")?.get(p)?.let { JsonLogic.fromJson(it) } as? Map<String, Any?>).orEmpty() }
    fun filled(today: String) = trees["inspection"]?.let { Filled(trees, answers, JsonLogic.fromJson(b.answers) as Map<String, Any?>, today) }
}

@Composable
fun rememberBooking(env: OpsEnv, id: String): Loaded3? {
    val b = rememberLoad(env, "bookings/$id").value
    val insps = rememberLoad(env, "bookings/$id/inspections").value?.data?.rows()
    val insp = insps?.let(::currentInspection)
    val versions = mapOf("inspection" to insp?.int("form_version"), "start" to insp?.int("start_version"), "end" to insp?.int("end_version"))
    val raw = versions.mapValues { (_, v) -> rememberLoad(env, v?.let { "form-versions/$it" }).value?.data as? JsonObject }
    if (b == null || insps == null) return null
    return Loaded3(Bk(b.data as JsonObject), insp, raw.mapValues { it.value?.let(FormTree::parse) }, raw, b.offline)
}

/** Every answer of the inspection, page by page; tap one to change it (Ops). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AnswersScreen(env: OpsEnv, id: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val data = rememberBooking(env, id)
    var page by remember { mutableStateOf(0) }
    var pages by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<Pair<String, Field>?>(null) }
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader("Answers", data?.let { "${it.b.code} · ${it.b.customer}" }, onBack)
        val filled = data?.filled(env.today().toString())
        if (data?.insp == null || filled == null) {
            Text(if (data == null) "Loading…" else "No inspection yet.", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp)); return
        }
        val steps = PARTS.flatMap { p -> filled.visiblePages(p).map { p to it } }
        val (part, pg) = steps[page.coerceIn(0, steps.lastIndex)]
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            OfflineNote(rememberLoad(env, "bookings/$id").value)
            Row(Modifier.padding(top = 10.dp).fillMaxWidth().heightIn(min = 48.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.soft)
                .clickable(role = Role.Button) { pages = true }.padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("${pg.title} · page ${page + 1} of ${steps.size}", fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, modifier = Modifier.weight(1f))
                Icon(Icons.Outlined.ExpandMore, null, tint = Vayu.colors.ink)
            }
            pg.fields.filter { it.answerable && filled.visible(part, it.key) }.forEach { f ->
                val v = data.answers[part]?.get(f.key)
                val editable = env.can("submissions.edit") && !data.offline && !f.isMedia
                Column(Modifier.fillMaxWidth().heightIn(min = 58.dp).clickable(enabled = editable, role = Role.Button) { editing = part to f }
                    .padding(vertical = 8.dp), verticalArrangement = Arrangement.Center) {
                    Text(f.label, fontSize = 13.sp, color = Vayu.colors.muted)
                    Text(answerText(f, v, env), color = Vayu.colors.ink)
                }
                HorizontalDivider(color = Vayu.colors.line)
            }
            Text("Tap an answer to change it. Ratings and Key Checks update when you save.", color = Vayu.colors.muted, fontSize = 13.sp,
                modifier = Modifier.padding(vertical = 16.dp))
        }
        if (pages) ModalBottomSheet(onDismissRequest = { pages = false }, containerColor = Vayu.colors.bg) {
            steps.forEachIndexed { i, (_, p) ->
                Text("${i + 1}. ${p.title}", color = Vayu.colors.ink, fontWeight = if (i == page) FontWeight.Bold else FontWeight.Normal,
                    modifier = Modifier.fillMaxWidth().clickable(role = Role.Button) { page = i; pages = false }.padding(horizontal = 20.dp, vertical = 14.dp))
            }
            Spacer(Modifier.height(24.dp))
        }
        editing?.let { (p, f) ->
            var value by remember(f.key) { mutableStateOf(data.answers[p]?.get(f.key)) }
            var error by remember(f.key) { mutableStateOf<String?>(null) }
            ModalBottomSheet(onDismissRequest = { editing = null }, containerColor = Vayu.colors.bg) {
                Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
                    Text(pg.title, fontSize = 13.sp, color = Vayu.colors.muted)
                    Question(f, value, filled.required(p, f.key), false, error, false, opsFieldEnv(env)) { value = it }
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
                                        "INVALID_ANSWERS" -> (e.extra["errors"] as? JsonObject)?.s(f.key)?.ifBlank { null } ?: e.message
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
    "number" -> shown(v) + ((f.config["unit"] as? String)?.let { " $it" } ?: "")
    "currency" -> if (v == null) "—" else "₹" + shown(v)
    else -> shown(v)
}

/** A signed file URL, fetched and kept in the cache folder (thumbnails, full view). */
suspend fun mediaBytes(env: OpsEnv, dir: File, id: String): File? = withContext(Dispatchers.IO) {
    val f = File(dir, "media-$id")
    if (f.exists()) return@withContext f
    runCatching {
        val url = (env.data.api.get("media/$id/url") as JsonObject).s("url")
        writeAtomically(f, env.data.api.download(url)); f
    }.getOrNull()
}

private fun thumb(f: File, size: Int): ImageBitmap? = runCatching {
    val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(f.path, o)
    var s = 1
    while (o.outWidth / (s * 2) >= size && o.outHeight / (s * 2) >= size) s *= 2
    BitmapFactory.decodeFile(f.path, BitmapFactory.Options().apply { inSampleSize = s })?.asImageBitmap()
}.getOrNull()

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
    var adding by remember { mutableStateOf<Pair<String, Field>?>(null) }
    val online = list.value?.offline == false
    val fields = PARTS.flatMap { p -> data?.trees?.get(p)?.pages.orEmpty().flatMap { pg -> pg.sections.flatMap { s -> s.fields.filter { it.isMedia }.map { Triple(p, s.title, it) } } } }
    suspend fun upload(part: String, f: Field, file: File, type: String) {
        val insp = data?.insp ?: return
        try {
            val init = env.data.api.mediaInitiate(id, UUID.randomUUID().toString(), f.key, f.type, type, file.length(), sha256(file), "gallery")
            if (!transfer(env.data.api, init, file, type)) { env.say("The file arrived damaged. Try again."); return }
            val cur = data.answers[part]?.get(f.key)
            val value: Any? = if (f.type == "signature") init.s("id") else ((cur as? List<*>).orEmpty() + init.s("id"))
            env.data.act("PATCH", "inspections/${insp.s("id")}", buildJsonObject {
                put("row_version", insp.int("row_version") ?: 0)
                put("answers", buildJsonObject { put(part, buildJsonObject { put(f.key, JsonLogic.toJson(value)) }) })
            })
            env.say("Added."); env.refresh()
        } catch (e: ApiError) { env.say(e.message) } finally { file.delete() }
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        val (part, f) = adding ?: return@rememberLauncherForActivityResult
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val tmp = newFile(ctx.cacheDir, "up")
            val type = withContext(Dispatchers.IO) { copyIn(ctx, uri, tmp) } ?: return@launch
            upload(part, f, tmp, type)
        }
    }
    open?.let { m -> MediaViewer(env, m, fieldLabel = fields.firstOrNull { it.third.key == m.s("field_key") }?.third?.label ?: m.s("field_key"),
        canManage = env.can("media.manage") && online, onClose = { open = null },
        onDelete = {
            scope.launch {
                try { env.data.act("DELETE", "media/${m.s("id")}"); open = null; env.say("Deleted."); env.refresh() } catch (e: ApiError) { env.say(e.message) }
            }
        }, onReplace = {
            val f = fields.firstOrNull { it.third.key == m.s("field_key") }
            if (f != null) scope.launch {
                try { env.data.act("DELETE", "media/${m.s("id")}") } catch (e: ApiError) { env.say(e.message); return@launch }
                open = null; adding = f.first to f.third; picker.launch(arrayOf(if (f.third.type == "video") "video/*" else "image/*"))
            }
        }); return }
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
            fields.groupBy { it.second }.forEach { (section, fs) ->
                val here = items.filter { m -> fs.any { it.third.key == m.s("field_key") } }
                Section(section)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    here.forEach { m -> MediaTile(env, m) { open = m } }
                    if (env.can("media.manage") && online && data?.insp != null) fs.forEach { (p, _, f) ->
                        Box(Modifier.size(76.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.soft)
                            .clickable(role = Role.Button) { adding = p to f; picker.launch(arrayOf(if (f.type == "video") "video/*" else "image/*", "application/pdf")) }
                            .semantics { contentDescription = "Add to ${f.label}" }, contentAlignment = Alignment.Center) {
                            Text("+ ${f.label}", fontSize = 11.sp, color = Vayu.colors.ink2, modifier = Modifier.padding(4.dp), maxLines = 3)
                        }
                    }
                }
            }
            Text("Tap one to see it full screen, replace it or delete it.", color = Vayu.colors.muted, fontSize = 13.sp, modifier = Modifier.padding(vertical = 16.dp))
        }
    }
}

@Composable
private fun MediaTile(env: OpsEnv, m: JsonObject, onClick: () -> Unit) {
    val ctx = LocalContext.current
    val img by produceState<ImageBitmap?>(null, m.s("id")) {
        if (m.s("kind") == "photo") value = mediaBytes(env, ctx.cacheDir, m.s("id"))?.let { thumb(it, 160) }
    }
    Box(Modifier.size(76.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.illo).clickable(role = Role.Button, onClick = onClick)
        .semantics { contentDescription = "${m.s("kind")} ${m.s("field_key")}" }, contentAlignment = Alignment.Center) {
        img?.let { Image(it, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize()) }
        if (m.s("kind") == "video") Icon(Icons.Outlined.PlayCircle, null, tint = Color.White, modifier = Modifier.size(30.dp))
    }
}

@Composable
private fun MediaViewer(env: OpsEnv, m: JsonObject, fieldLabel: String, canManage: Boolean, onClose: () -> Unit, onDelete: () -> Unit, onReplace: () -> Unit) {
    BackHandler(onBack = onClose)
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val img by produceState<ImageBitmap?>(null, m.s("id")) {
        if (m.s("kind") == "photo") value = mediaBytes(env, ctx.cacheDir, m.s("id"))?.let { thumb(it, 1400) }
    }
    Column(Modifier.fillMaxSize().background(Color.Black).safeDrawingPadding()) {
        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            `in`.carcid.vayu.ui.expert.CloseButton("Back", onClose, tint = Color.White)
            Text(fieldLabel, color = Color.White, fontWeight = FontWeight.Bold)
        }
        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            img?.let { Image(it, fieldLabel, contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize()) }
            if (m.s("kind") != "photo") Column(horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.clickable(role = Role.Button) {
                    scope.launch {
                        try {
                            val url = (env.data.api.get("media/${m.s("id")}/url") as JsonObject).s("url")
                            ctx.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url)))
                        } catch (e: ApiError) { env.say(e.message) }
                    }
                }) {
                Icon(Icons.Outlined.PlayCircle, null, tint = Color.White, modifier = Modifier.size(72.dp))
                Text(if (m.s("kind") == "video") "Play" else "Open", color = Color.White)
            }
        }
        if (canManage) Row(Modifier.fillMaxWidth().padding(20.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
            Column(Modifier.clickable(role = Role.Button, onClick = onDelete).padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Outlined.Delete, null, tint = Color.White); Text("Delete", color = Color.White)
            }
            Column(Modifier.clickable(role = Role.Button, onClick = onReplace).padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Outlined.Autorenew, null, tint = Color.White); Text("Replace", color = Color.White)
            }
        }
    }
}

/** Ratings (override), Key Checks (override), the overall word, and the payment as answered. */
@Composable
fun RatingsScreen(env: OpsEnv, id: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val data = rememberBooking(env, id)
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader("Ratings and payment", data?.let { "${it.b.code} · ${it.b.customer}" }, onBack)
        val insp = data?.insp
        if (insp == null) { Text(if (data == null) "Loading…" else "Ratings are calculated once the expert submits.", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp)); return }
        val s = insp.o("scores")
        val edit = env.can("ratings.override") && !data.offline
        fun send(body: JsonObject) = scope.launch {
            try {
                env.data.act("PATCH", "inspections/${insp.s("id")}/overrides", JsonObject(body + ("row_version" to JsonPrimitive(insp.int("row_version") ?: 0))))
                env.say("Saved."); env.refresh()
            } catch (e: ApiError) { env.say(if (e.code == "STALE_INSPECTION") "Someone else changed it meanwhile; loaded their version." else e.message); env.refresh() }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            if (data.offline) OfflineNote(rememberLoad(env, "bookings/$id").value)
            val overall = s.o("overall")
            Section("Overall · ${overall.s("word").ifBlank { "—" }}" + if (overall.s("overridden") == "true") " (set by you)" else "")
            ChoiceRow(listOf("Excellent", "Good", "Average", "Bad").map { it to false },
                overall.s("word").takeIf { overall.s("overridden") == "true" }?.replaceFirstChar { it.uppercase() }) { w ->
                if (edit) send(buildJsonObject { put("overall", w.lowercase()) })
            }
            Text("Suggested: ${overall.s("suggested_word").ifBlank { "—" }}", color = Vayu.colors.muted, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp))
            val cats = data.raw["inspection"]?.o("rating_config")?.a("categories").orEmpty().map { it as JsonObject }
            if (cats.isNotEmpty()) Section("Ratings")
            cats.forEach { c ->
                val r = s.o("ratings").o(c.s("key"))
                Text(c.s("label") + if (r.s("overridden") == "true") " · set by you" else "  (suggested ${r.s("suggested").ifBlank { "—" }})",
                    fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, modifier = Modifier.padding(top = 10.dp, bottom = 6.dp))
                ChoiceRow((1..5).map { "$it" to false }, r.s("value").takeIf { it.isNotBlank() }?.substringBefore(".")) { n ->
                    if (edit) send(buildJsonObject { put("ratings", buildJsonObject { put(c.s("key"), n.toInt()) }) })
                }
            }
            val checks = data.trees["inspection"]?.fields.orEmpty().filter { it.type == "derived" }
            if (checks.isNotEmpty()) Section("Key Checks")
            checks.forEach { f ->
                val yes = f.config["true_label"] as? String ?: "Yes"; val no = f.config["false_label"] as? String ?: "No"
                val now = s.o("derived").s(f.key) == "true"
                Text("${f.label} · now ${if (now) yes else no}", fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, modifier = Modifier.padding(top = 10.dp, bottom = 6.dp))
                ChoiceRow(listOf(yes to false, no to false), insp.o("overrides").o("derived").s(f.key).takeIf { it.isNotBlank() }?.let { if (it == "true") yes else no }) { v ->
                    if (edit) send(buildJsonObject { put("derived", buildJsonObject { put(f.key, v == yes) }) })
                }
            }
            Section("Payment")
            val end = data.answers["end"].orEmpty()
            val paid = end["taking_payment"]
            Text(when (paid) {
                true -> listOfNotNull(end["payment_mode"]?.toString()?.replaceFirstChar { it.uppercase() },
                    (end["payment_amount"] as? Number)?.let { "₹" + shown(it.toDouble()) }).joinToString(" · ").ifBlank { "Taken" }
                false -> "No payment taken (pay later)"
                else -> "Not answered yet"
            }, color = Vayu.colors.ink)
            Text("Verifying or recording a payment isn't on the server yet; change the wrap-up answers to correct it.",
                color = Vayu.colors.muted, fontSize = 13.sp, modifier = Modifier.padding(vertical = 12.dp))
        }
    }
}

/** The PDF report: status, open, share, remake. */
@Composable
fun ReportScreen(env: OpsEnv, id: String, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val b = rememberLoad(env, "bookings/$id").value?.data?.let { Bk(it as JsonObject) }
    val r = rememberLoad(env, "bookings/$id/report")
    val rep = r.value?.data as? JsonObject
    BackHandler(onBack = onBack)
    suspend fun file(): File? {
        val url = rep?.s("url")?.ifBlank { null } ?: return null
        return withContext(Dispatchers.IO) {
            runCatching {
                val f = File(File(ctx.cacheDir, "reports").apply { mkdirs() }, rep.s("filename").ifBlank { "report.pdf" }.replace("/", "_"))
                writeAtomically(f, env.data.api.download(url)); f
            }.getOrNull()
        }
    }
    fun uriOf(f: File) = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader("Report", b?.let { "${it.code} · ${it.customer}" }, onBack)
        Column(Modifier.padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            OfflineNote(r.value)
            when {
                rep == null -> Text(if (b?.stage == "completed") "The report is being made." else "It's made automatically when the booking is Completed.",
                    color = Vayu.colors.muted)
                else -> {
                    Text(when (rep.s("status")) { "ready" -> "Ready" + (rep.s("generated_at").takeIf { it.isNotBlank() }?.let { " · made ${shortStamp(it)}" } ?: "")
                        else -> rep.s("status").replaceFirstChar { it.uppercase() } }, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink)
                    if (rep.s("stale") == "true") Banner("Out of date: answers changed after this PDF was made. Make it again to include them.", Tone.WARN, {})
                    if (rep.s("error").isNotBlank()) Banner("Problem: ${rep.s("error")}", Tone.BAD, {})
                    if (rep.s("url").isNotBlank()) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        SoftButton("Open", { scope.launch { file()?.let { ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uriOf(it), "application/pdf").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)) } ?: env.say("Couldn't download the report.") } }, Modifier.weight(1f))
                        PrimaryButton("Share", { scope.launch { file()?.let { ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("application/pdf")
                            .putExtra(Intent.EXTRA_STREAM, uriOf(it)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Share the report")) } ?: env.say("Couldn't download the report.") } }, Modifier.weight(1f))
                    }
                    if (rep.s("verify_url").isNotBlank()) SoftButton("Share the check link", {
                        ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, rep.s("verify_url")), "Share the check link"))
                    }, Modifier.fillMaxWidth())
                }
            }
            if (env.can("reports.regenerate") && b?.stage == "completed") SoftButton("Make it again", {
                scope.launch {
                    try { env.data.act("POST", "bookings/$id/report/regenerate", JsonObject(emptyMap())); env.say("Making the report. This takes a few seconds."); kotlinx.coroutines.delay(4000); env.refresh() }
                    catch (e: ApiError) { env.say(e.message) }
                }
            }, Modifier.fillMaxWidth())
        }
    }
}

/** What happened to the booking, newest first. */
@Composable
fun HistoryScreen(env: OpsEnv, id: String, onBack: () -> Unit) {
    val rows = rememberLoad(env, "bookings/$id/activity").value?.data?.rows().orEmpty()
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader("History", null, onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            rows.forEach { r ->
                Column(Modifier.fillMaxWidth().heightIn(min = 56.dp).padding(vertical = 8.dp)) {
                    Text(activityText(r, env), color = Vayu.colors.ink)
                    Text(r.s("at").take(16).replace('T', ' '), fontSize = 13.sp, color = Vayu.colors.muted)
                }
                HorizontalDivider(color = Vayu.colors.line)
            }
            if (rows.isEmpty()) Text("Nothing yet.", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 20.dp))
        }
    }
}

/** One history row in words (web: activityText). */
fun activityText(r: JsonObject, env: OpsEnv): String {
    val by = r.o("by").s("name").ifBlank { "The system" }
    val c = r.o("changes")
    fun new(k: String) = (c[k] as? kotlinx.serialization.json.JsonArray)?.getOrNull(1)?.let { (it as? JsonPrimitive)?.content }
    fun old(k: String) = (c[k] as? kotlinx.serialization.json.JsonArray)?.getOrNull(0)?.let { (it as? JsonPrimitive)?.content }
    return when {
        r.s("kind") == "created" -> "Created by $by"
        r.s("kind") == "inspection_edited" -> "$by changed ${r.a("keys").size} answer${if (r.a("keys").size == 1) "" else "s"}"
        r.s("kind") == "ratings_changed" -> "$by changed the ratings"
        new("stage") == "completed" -> "Completed: every file uploaded"
        new("stage") == "submitted" -> "Submitted by $by"
        new("stage") == "in_progress" -> "Started by $by"
        new("stage") == "cancelled" -> "Cancelled by $by"
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
            if (e.code.startsWith("STALE")) { env.refresh(); env.say("Someone else saved this booking meanwhile; their version is loaded.") }
            else if (errors.isEmpty()) env.say(e.message)
        } finally { busy = false }
    }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader(if (id == null) "New booking" else "Edit booking", existing?.code, onBack)
        if (tree == null) { Text("Loading the booking form…", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp)); return }
        // the booking form's own answers are "booking" in its rules
        val filled = Filled(mapOf("booking" to tree), emptyMap(), values, env.today().toString())
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            val fe = opsFieldEnv(env, lists)
            tree.pages.forEach { p -> p.sections.forEach { s ->
                val fs = s.fields.filter { it.answerable && filled.visible("booking", it.key) && it.key != "assigned_expert" && !(id != null && it.key == "inspection_type") }
                if (fs.isNotEmpty()) Section(s.title)
                fs.forEach { f ->
                    Question(f, values[f.key], filled.required("booking", f.key), false, errors[f.key], false, fe) { v ->
                        values = values + (f.key to v); changed = changed + f.key; errors = errors - f.key
                    }
                }
            } }
            Spacer(Modifier.height(16.dp))
        }
        Row(Modifier.padding(horizontal = 20.dp, vertical = 14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SoftButton("Save", { save(false) }, Modifier.weight(1f))
            if (id == null && env.can("bookings.assign")) PrimaryButton(if (busy) "Saving…" else "Save and assign", { save(true) }, Modifier.weight(1f), enabled = !busy)
            else if (id != null) PrimaryButton(if (busy) "Saving…" else "Save changes", { save(false) }, Modifier.weight(1f), enabled = !busy && changed.isNotEmpty())
        }
    }
}
