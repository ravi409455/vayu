package `in`.carcid.vayu.ui.ops

import `in`.carcid.vayu.core.ops.MediaLinks
import `in`.carcid.vayu.core.ops.MediaItem
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import `in`.carcid.vayu.core.ARRIVED


import androidx.compose.material.icons.outlined.Add
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.automirrored.outlined.List
import android.content.Intent
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Autorenew
import androidx.compose.material.icons.outlined.PlayCircle
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.BuildConfig
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.draft.transfer
import `in`.carcid.vayu.core.forms.Field
import `in`.carcid.vayu.core.forms.PARTS
import `in`.carcid.vayu.core.media.copyIn
import `in`.carcid.vayu.core.ops.a
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.s
import `in`.carcid.vayu.core.writeAtomically
import `in`.carcid.vayu.ui.expert.newFile
import `in`.carcid.vayu.ui.expert.sha256
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.File
import java.util.UUID

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
        val links = MediaLinks.from(env.data.api.get("media/$id/url")) ?: return@withContext null
        val url = links.previewUrl?.takeIf { preview && it.isNotBlank() } ?: links.url
        writeAtomically(if (url == links.url) full else f, env.data.api.download(url))
        if (url == links.url) full else f
    } catch (e: kotlin.coroutines.cancellation.CancellationException) { throw e } catch (e: Exception) { null }
}

/** [thumb] off the main thread (a 2000-px decode stutters the list on a low-end phone). */
private suspend fun decoded(f: File, size: Int): ImageBitmap? = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Default) { `in`.carcid.vayu.core.media.thumb(f.path, size) }

/**
 * Ops add a file to a submitted inspection, or replace one (the old one stays as history only
 * Admin opens; nobody deletes): start the upload saying what it replaces, send it, attach it.
 */
class OpsUploader(val pick: (part: String, f: Field, replaces: String?) -> Unit,
                  val canAdd: (part: String, f: Field, have: Int) -> Boolean, val canReplace: (Field) -> Boolean,
                  /** one pick of several files: file i takes the place of slots[i] (files that never arrived) */
                  val fill: (f: Field, slots: List<String>, done: () -> Unit) -> Unit = { _, _, _ -> })

@Composable
fun rememberOpsUploader(env: OpsEnv, id: String, data: Loaded3?, online: Boolean): OpsUploader {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var target by remember { mutableStateOf<Triple<String, Field, String?>?>(null) }
    // only once the expert has submitted, and never on a cancelled booking
    val may = env.can("media.manage") && online && data?.insp?.status == "submitted" && data.b.stage != "cancelled"
    suspend fun upload(f: Field, file: File, type: String, replaces: String?, quiet: Boolean = false): Boolean {
        var loose: String? = null
        try {
            val hash = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { sha256(file) }
            val init = env.data.api.mediaInitiate(id, UUID.randomUUID().toString(), f.key, f.type, type, file.length(), hash, "gallery", replaces)
            loose = init.s("id")
            if (!transfer(env.data.api, init, file, type)) { env.say("The file arrived damaged. Try again."); return false }
            env.data.act("POST", "media/$loose/attach", buildJsonObject { if (replaces != null) put("replaces", replaces) })
            loose = null
            if (!quiet) { env.say(if (replaces != null) "Replaced." else "Added."); env.refresh() }
            return true
        } catch (e: ApiError) { env.say(e.message); return false } finally {
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
    var filling by remember { mutableStateOf<Triple<Field, List<String>, () -> Unit>?>(null) }
    val many = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        val (f, slots, done) = filling ?: return@rememberLauncherForActivityResult
        filling = null
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        done()
        scope.launch {
            var sent = 0
            for ((uri, slot) in uris.zip(slots)) {          // in the order picked; extra ones not used
                val tmp = newFile(ctx.cacheDir, "up")
                val type = withContext(Dispatchers.IO) { copyIn(ctx, uri, tmp) } ?: continue
                if (upload(f, tmp, type, slot, quiet = true)) sent++ else break
            }
            val extra = uris.size - slots.size
            if (sent > 0) env.say("Uploaded. It is checked in the background." +
                if (extra > 0) " Only ${slots.size} ${if (slots.size == 1) "was" else "were"} missing; $extra not used." else "")
            env.refresh()
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
        canReplace = { f -> may && f.config["ops_upload"] != false },
        fill = { f, slots, done -> filling = Triple(f, slots, done); many.launch(types(f)) })
}

/** Photos and videos by section: view full screen, play, add, replace, delete, share a ZIP. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MediaScreen(env: OpsEnv, id: String, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val data = rememberBooking(env, id)
    val list = rememberLoad(env, "bookings/$id/media")
    val all = MediaItem.list(list.value?.data?.rows().orEmpty())
    val items = all.filter { it.status in ARRIVED }
    var open by remember { mutableStateOf<MediaItem?>(null) }
    val online = list.value?.offline == false
    val fields = PARTS.flatMap { p -> data?.trees?.get(p)?.pages.orEmpty().flatMap { pg -> pg.sections.flatMap { s -> s.fields.filter { it.isMedia }.map { Triple(p, s.title, it) } } } }
    val up = rememberOpsUploader(env, id, data, online)
    open?.let { m ->
        val f = fields.firstOrNull { it.third.key == m.fieldKey }
        val have = items.count { it.fieldKey == m.fieldKey }
        MediaViewer(env, m, fieldLabel = f?.third?.label ?: m.fieldKey, onClose = { open = null },
            onReplace = f?.takeIf { up.canReplace(it.third) }?.let { { open = null; up.pick(it.first, it.third, m.id) } },
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
            Text("${items.count { it.kind == "photo" }} photos · ${items.count { it.kind == "video" }} videos", color = Vayu.colors.muted)
            // files deleted after the storage time Admin set (Settings) are gone for good: say so
            val deleted = all.count { it.status == "purged" }
            if (deleted > 0) Text("$deleted ${if (deleted == 1) "file was" else "files were"} deleted after the storage time set in Settings.",
                color = Vayu.colors.muted, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp))
            val filled = data?.filled(env.today().toString())
            fields.groupBy { it.second }.forEach { (section, fs) ->
                val here = items.filter { m -> fs.any { it.third.key == m.fieldKey } }
                val addable = fs.filter { (p, _, f) -> filled?.visible(p, f.key) != false && up.canAdd(p, f, here.count { it.fieldKey == f.key }) }
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
internal fun MediaTile(env: OpsEnv, m: MediaItem, size: androidx.compose.ui.unit.Dp = 76.dp, onClick: () -> Unit) {
    val ctx = LocalContext.current
    val img by produceState<ImageBitmap?>(null, m.id) {
        if (m.kind in setOf("photo", "signature")) value = mediaBytes(env, ctx.cacheDir, m.id, preview = true)?.let { decoded(it, 160) }
    }
    Box(Modifier.size(size).clip(RoundedCornerShape(if (size < 76.dp) 10.dp else 12.dp)).background(Vayu.colors.illo).clickable(role = Role.Button, onClick = onClick)
        .semantics { contentDescription = "${m.kind} ${m.fieldKey}" }, contentAlignment = Alignment.Center) {
        img?.let { Image(it, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize()) }
        if (m.kind == "video") Icon(Icons.Outlined.PlayCircle, null, tint = Color.White, modifier = Modifier.size(30.dp))
        if (m.hiddenFromCustomer) Text("Hidden", fontSize = 10.sp, color = Vayu.colors.warn, maxLines = 1,
            modifier = Modifier.align(Alignment.BottomStart).padding(4.dp).clip(RoundedCornerShape(6.dp))
                .background(Vayu.colors.warnTint).padding(horizontal = 5.dp, vertical = 1.dp)
                .semantics { contentDescription = "Hidden from customer" })
    }
}

@Composable
internal fun MediaViewer(env: OpsEnv, m: MediaItem, fieldLabel: String, onClose: () -> Unit, onReplace: (() -> Unit)? = null, onAdd: (() -> Unit)? = null) {
    BackHandler(onBack = onClose)
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    // null while loading; false when it couldn't be loaded
    val img by produceState<Any?>(null, m.id) {
        if (m.kind in setOf("photo", "signature")) value = mediaBytes(env, ctx.cacheDir, m.id)?.let { decoded(it, 2000) } ?: false
    }
    var videoUrl by remember { mutableStateOf<String?>(null) }
    var scale by remember { mutableStateOf(1f) }
    var pan by remember { mutableStateOf(androidx.compose.ui.geometry.Offset.Zero) }
    Column(Modifier.fillMaxSize().background(Color.Black).safeDrawingPadding()) {
        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            `in`.carcid.vayu.ui.expert.CloseButton("Back", onClose, tint = Color.White)
            Column {
                Text(fieldLabel, color = Color.White, fontWeight = FontWeight.Bold)
                if (m.hiddenFromCustomer) Text("Hidden from customer: not in the report, its downloads or any ZIP",
                    color = Vayu.colors.warnTint, fontSize = 12.sp)
            }
        }
        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            when {
                // pinch to zoom, drag to look around
                img is ImageBitmap -> Image(img as ImageBitmap, fieldLabel, contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize()
                    .pointerInput(Unit) { detectTransformGestures { _, p, z, _ -> scale = (scale * z).coerceIn(1f, 5f); pan = if (scale == 1f) androidx.compose.ui.geometry.Offset.Zero else pan + p } }
                    .graphicsLayer(scaleX = scale, scaleY = scale, translationX = pan.x, translationY = pan.y))
                img == false -> Text("Couldn't load this photo. Check the signal and try again.", color = Color.White, modifier = Modifier.padding(24.dp))
                m.kind in setOf("photo", "signature") -> Text("Loading…", color = Color.White)
                videoUrl != null -> AndroidView(factory = { c -> android.widget.VideoView(c).apply {
                    setMediaController(android.widget.MediaController(c).also { it.setAnchorView(this) })
                    setVideoURI(android.net.Uri.parse(videoUrl)); setOnPreparedListener { start() }
                    setOnErrorListener { _, _, _ -> env.say("Couldn't play this video."); true }
                } }, onRelease = { it.stopPlayback() }, modifier = Modifier.fillMaxSize())
                else -> Column(horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.clickable(role = Role.Button) {
                        scope.launch {
                            try {
                                val url = MediaLinks.from(env.data.api.get("media/${m.id}/url"))?.url.orEmpty()
                                if (url.isBlank()) { env.say("Couldn't open this file. Try again."); return@launch }
                                // videos play here; other files open in an app that can show them
                                if (m.kind == "video") videoUrl = url
                                else try { ctx.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url))) }
                                    catch (e: android.content.ActivityNotFoundException) { env.say("No app on this phone can open this file.") }
                            } catch (e: ApiError) { env.say(e.message) }
                        }
                    }) {
                    Icon(Icons.Outlined.PlayCircle, null, tint = Color.White, modifier = Modifier.size(72.dp))
                    Text(if (m.kind == "video") "Play" else "Open", color = Color.White)
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
