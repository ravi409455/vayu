package `in`.carcid.vayu.ui.expert

import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.draft.Draft
import `in`.carcid.vayu.core.draft.DraftStore
import `in`.carcid.vayu.core.draft.LocalFile
import `in`.carcid.vayu.core.forms.Field
import `in`.carcid.vayu.core.forms.Filled
import `in`.carcid.vayu.core.forms.refusalText
import `in`.carcid.vayu.core.media.Locator
import `in`.carcid.vayu.core.media.copyIn
import `in`.carcid.vayu.core.media.stampPhoto
import `in`.carcid.vayu.ui.components.Banner
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.Tone
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.time.Instant

/** Which full-screen tool is open over the wizard. */
private sealed interface Tool {
    data class Camera(val part: String, val field: Field) : Tool
    data class Sign(val part: String, val field: Field) : Tool
    data class Scan(val part: String, val field: Field) : Tool
    data class Review(val part: String, val field: Field, val file: LocalFile) : Tool
}

/** What the inspection screens need from the app around them. */
class InspectionEnv(
    val model: InspectionModel,
    val drafts: DraftStore,
    val expertName: String,
    val verified: Boolean,
    val now: () -> Instant,
    val list: (String) -> List<Pair<String, String>>,
    val types: List<Pair<String, String>>,
    val asset: suspend (String) -> ImageBitmap?,
    /** Ops changed something on this job since the expert last looked ("old -> new"). */
    val opsChanges: List<String> = emptyList(),
)

@Composable
fun InspectionScreen(env: InspectionEnv, onClose: () -> Unit) {
    val tick by env.drafts.changes.collectAsState()
    val draft = remember(tick) { env.model.draft }
    val filled = remember(tick) { env.model.filled(draft) }
    LaunchedEffect(Unit) { env.model.open() }
    if (filled == null) {
        Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding().padding(20.dp)) {
            CloseButton("Close", onClose)
            Text("This job's form isn't on the phone yet. Connect to the internet once and tap Refresh.", color = Vayu.colors.ink)
        }
        return
    }
    if (draft.locked) { SubmittedScreen(draft, onClose); return }
    Wizard(env, draft, filled, onClose)
}

@OptIn(ExperimentalMaterial3Api::class, androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun Wizard(env: InspectionEnv, draft: Draft, filled: Filled, onClose: () -> Unit) {
    val model = env.model
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val steps = model.steps(filled)
    val index = draft.step.coerceIn(0, steps.lastIndex)
    val step = steps[index]
    var tool by remember { mutableStateOf<Tool?>(null) }
    var pages by remember { mutableStateOf(false) }
    var blocked by remember { mutableStateOf<List<String>>(emptyList()) }
    var confirm by remember { mutableStateOf<String?>(null) }
    var dismissed by rememberSaveable { mutableStateOf(false) }
    val files = draft.files.associateBy { it.id }
    val dir = env.drafts.filesDir

    LaunchedEffect(step.id) { if (step.id !in draft.visited) model.go(index, step) }

    val missingOn = { s: Step -> if (s.isReview) 0 else filled.pageGaps(s.part!!, s.page!!).size }
    // a page the Admin marked "finish before moving on" holds everything after it
    val gate = steps.indexOfFirst { !it.isReview && it.page!!.gate && missingOn(it) > 0 }
    val lockedFrom = if (gate == -1) steps.size else gate + 1
    fun go(i: Int) {
        blocked = emptyList()
        if (i >= lockedFrom) { blocked = listOf("Finish ${steps[gate].title} first."); return }
        model.go(i.coerceIn(0, steps.lastIndex), steps[i.coerceIn(0, steps.lastIndex)])
    }

    // pickers for the gallery and files (the system's own, no permission needed)
    var picking by remember { mutableStateOf<Pair<String, Field>?>(null) }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        val (part, f) = picking ?: return@rememberLauncherForActivityResult
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val raw = newFile(dir, "pick")
            val type = withContext(Dispatchers.IO) { copyIn(ctx, uri, raw) } ?: return@launch
            if (f.type == "photo" && type.startsWith("image/")) {
                val out = newFile(dir, "jpg")
                withContext(Dispatchers.Default) {
                    stampPhoto(raw, out, stampLines(draft.code, env.expertName, env.now(), env.verified, Locator.last).let { listOf(it[0] + " · gallery", it[1]) })
                    raw.delete()
                }
                model.addFile(part, f.key, "photo", out, "image/jpeg", "gallery", label(f, draft, part), single = false)
            } else model.addFile(part, f.key, f.type, raw, type, "gallery", label(f, draft, part), single = false)
        }
    }
    val document = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        val (part, f) = picking ?: return@rememberLauncherForActivityResult
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val raw = newFile(dir, "file")
            val type = withContext(Dispatchers.IO) { copyIn(ctx, uri, raw) } ?: return@launch
            model.addFile(part, f.key, "file", raw, type, "gallery", label(f, draft, part), single = false)
        }
    }

    when (val t = tool) {
        is Tool.Camera -> {
            CameraScreen(t.field, (draft.answer(t.part, t.field.key) as? List<*>)?.size ?: 0, draft.code, env.expertName, env.now,
                env.verified, dir, onTaken = { file, type ->
                    model.addFile(t.part, t.field.key, t.field.type, file, type, "camera", label(t.field, model.draft, t.part), single = false)
                }, onDone = { tool = null })
            return
        }
        is Tool.Sign -> {
            SignatureScreen(t.field, dir, onSigned = { file ->
                model.addFile(t.part, t.field.key, "signature", file, "image/png", "camera", t.field.label, single = true); tool = null
            }, onClose = { tool = null })
            return
        }
        is Tool.Scan -> {
            ScanScreen(t.field, draft.answer(t.part, t.field.key) as? String, onUse = { model.set(t.part, t.field.key, it); tool = null },
                onClose = { tool = null })
            return
        }
        is Tool.Review -> {
            val ids = (draft.answer(t.part, t.field.key) as? List<*>)?.filterIsInstance<String>() ?: listOfNotNull(draft.answer(t.part, t.field.key) as? String)
            val live = files[t.file.id] ?: run { tool = null; return }
            FileReview(t.field, live, ids.indexOf(live.id) + 1, ids.size, draft.locked,
                onDelete = { model.removeFile(t.part, t.field.key, live.id); tool = null },
                onRetake = { model.removeFile(t.part, t.field.key, live.id); tool = Tool.Camera(t.part, t.field) },
                onClose = { tool = null })
            return
        }
        null -> {}
    }

    BackHandler(onBack = onClose)
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        // header: close (the draft stays), page title, "3 / 14" opens the page list
        Row(Modifier.fillMaxWidth().padding(start = 6.dp, end = 8.dp, top = 8.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            CloseButton("Close and keep the draft", onClose)
            Column(Modifier.weight(1f)) {
                Text(if (step.part == "start" && steps.count { it.part == "start" } == 1) "Check-in" else step.title,
                    fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink, maxLines = 1)
                Text("${draft.code} · ${draft.customer}", fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1)
            }
            Row(Modifier.heightIn(min = 40.dp).clip(RoundedCornerShape(20.dp)).background(Vayu.colors.soft)
                .clickable(role = Role.Button) { pages = true }.padding(horizontal = 12.dp)
                .semantics { contentDescription = "Page ${index + 1} of ${steps.size}, open the page list" },
                verticalAlignment = Alignment.CenterVertically) {
                Text("${index + 1} / ${steps.size}", fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = Vayu.colors.ink)
                Icon(Icons.Outlined.ExpandMore, null, tint = Vayu.colors.ink, modifier = Modifier.size(18.dp))
            }
        }
        Box(Modifier.padding(horizontal = 20.dp).fillMaxWidth().height(3.dp).clip(RoundedCornerShape(2.dp)).background(Vayu.colors.line)) {
            Box(Modifier.fillMaxWidth(index.toFloat() / steps.lastIndex.coerceAtLeast(1)).height(3.dp).background(Vayu.colors.ink))
        }
        if (step.isReview) ReviewPage(draft, filled, steps, missingOn, { go(it) }, Modifier.weight(1f), onSubmit = {
            val notOpened = steps.filter { !it.isReview && it.id !in draft.visited }
            if (notOpened.isNotEmpty()) confirm = "submit" else model.submit()
        }) else {
            val scroll = rememberScrollState()
            val requesters = remember(step.id) { HashMap<String, BringIntoViewRequester>() }
            val part = step.part!!
            val gaps = filled.pageGaps(part, step.page!!)
            Column(Modifier.weight(1f).verticalScroll(scroll).padding(horizontal = 20.dp)) {
                if (draft.problem != null && !dismissed) {
                    Spacer(Modifier.height(12.dp))
                    Banner(problemText(draft), Tone.BAD, { dismissed = true })
                }
                env.opsChanges.forEach { Spacer(Modifier.height(12.dp)); Banner(it, Tone.WARN, {}) }
                step.page.sections.forEach { s ->
                    val shown = s.fields.filter { filled.visible(part, it.key) && it.type !in Field.SYSTEM_MADE }
                    if (shown.isEmpty()) return@forEach
                    val countable = shown.filter { it.answerable }
                    Row(Modifier.fillMaxWidth().padding(top = 22.dp, bottom = 2.dp)) {
                        Text(s.title.uppercase(), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.7.sp,
                            color = Vayu.colors.muted, modifier = Modifier.weight(1f))
                        if (countable.isNotEmpty()) Text("${countable.count { answered(draft.answer(part, it.key)) }} of ${countable.size}",
                            fontSize = 12.sp, color = Vayu.colors.muted)
                    }
                    shown.forEach { f ->
                        val r = requesters.getOrPut(f.key) { BringIntoViewRequester() }
                        Box(Modifier.bringIntoViewRequester(r)) {
                            val v = draft.answer(part, f.key)
                            Question(f, v, filled.required(part, f.key),
                                missing = blocked.isNotEmpty() && gaps.any { it.key == f.key },
                                // what the server refused, or what its rules would refuse, right under the answer
                                error = draft.fieldErrors[f.key]?.let(::refusalText) ?: `in`.carcid.vayu.core.forms.answerProblem(f, v),
                                nested = f.showIf != null, env = FieldEnv(
                                    locked = draft.locked, list = env.list, types = env.types, files = files, now = env.now,
                                    onCamera = { tool = Tool.Camera(part, it) },
                                    onGallery = { picking = part to it; gallery.launch(PickVisualMediaRequest(
                                        if (it.type == "video") ActivityResultContracts.PickVisualMedia.VideoOnly else ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                                    onPickFile = { picking = part to it; document.launch(arrayOf("image/jpeg", "image/png", "application/pdf")) },
                                    onSign = { tool = Tool.Sign(part, it) }, onScan = { tool = Tool.Scan(part, it) },
                                    onOpenFile = { fld, file -> tool = Tool.Review(part, fld, file) },
                                    onLocate = { _, done -> scope.launch { done(Locator.fix(ctx)?.let(Locator::answer)) } },
                                    asset = env.asset)) { v ->
                                model.set(part, f.key, v)
                                // a tap answer moves the eye to the next question still open on this page
                                if (f.type in setOf("single_choice", "yes_no") && v != null) {
                                    val after = shown.dropWhile { it.key != f.key }.drop(1)
                                    after.firstOrNull { it.answerable && !answered(model.draft.answer(part, it.key)) }
                                        ?.let { next -> scope.launch { requesters[next.key]?.bringIntoView() } }
                                }
                            }
                        }
                    }
                }
                if (blocked.isNotEmpty()) Text(blocked.first(), color = Vayu.colors.bad, modifier = Modifier.padding(vertical = 12.dp))
                Spacer(Modifier.height(24.dp))
            }
            // footer: what is still needed here, back, next
            Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (gaps.isNotEmpty()) Text("${gaps.size} still needed on this page · Show me", color = Vayu.colors.bad, fontWeight = FontWeight.SemiBold,
                    fontSize = 14.sp, modifier = Modifier.fillMaxWidth().clickable(role = Role.Button) {
                        blocked = listOf("Fill in the questions marked in red.")
                        scope.launch { requesters[gaps.first().key]?.bringIntoView() }
                    }.padding(vertical = 6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(54.dp).clip(RoundedCornerShape(14.dp)).background(Vayu.colors.soft)
                        .clickable(enabled = index > 0, role = Role.Button) { go(index - 1) }.semantics { contentDescription = "Previous page" },
                        contentAlignment = Alignment.Center) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, null, tint = Vayu.colors.ink) }
                    PrimaryButton("Next · ${steps[index + 1].title}", {
                        if (step.page.gate && gaps.isNotEmpty()) {
                            blocked = listOf("Finish this page first: " + gaps.joinToString(", ") { it.label })
                            scope.launch { requesters[gaps.first().key]?.bringIntoView() }
                        } else go(index + 1)
                    }, Modifier.weight(1f))
                }
            }
        }
    }

    if (pages) ModalBottomSheet(onDismissRequest = { pages = false }, containerColor = Vayu.colors.bg) {
        val needed = filled.allGaps().size
        Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 6.dp)) {
            Text("Pages", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = Vayu.colors.ink, modifier = Modifier.weight(1f))
            if (needed > 0) Text("$needed still needed", color = Vayu.colors.bad, fontSize = 14.sp)
        }
        LazyColumn(Modifier.heightIn(max = 560.dp)) {
            itemsIndexed(steps) { i, s ->
                val miss = missingOn(s)
                val seen = s.id in draft.visited
                val done = seen && miss == 0 && !s.isReview
                Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clickable(enabled = i < lockedFrom, role = Role.Button) { pages = false; go(i) }
                    .background(if (i == index) Vayu.colors.soft else Vayu.colors.bg).padding(horizontal = 20.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Box(Modifier.size(28.dp).clip(CircleShape).background(if (done) Vayu.colors.ok else Vayu.colors.soft), contentAlignment = Alignment.Center) {
                        Text(if (done) "✓" else "${i + 1}", fontSize = 13.sp, fontWeight = FontWeight.Bold,
                            color = if (done) androidx.compose.ui.graphics.Color.White else Vayu.colors.ink2)
                    }
                    Text(if (s.isReview) "Review and submit" else s.title, modifier = Modifier.weight(1f),
                        color = if (i < lockedFrom) Vayu.colors.ink else Vayu.colors.muted, fontWeight = if (i == index) FontWeight.SemiBold else FontWeight.Normal)
                    when {
                        seen && miss > 0 -> Text("$miss needed", color = Vayu.colors.bad, fontSize = 13.sp)
                        !seen && !s.isReview && i < lockedFrom -> Box(Modifier.size(8.dp).clip(CircleShape).background(Vayu.colors.info)
                            .semantics { contentDescription = "not opened yet" })
                    }
                }
            }
            item {
                if (gate != -1) Text("Finish ${steps[gate].title} to open the other pages.", color = Vayu.colors.muted, fontSize = 13.sp,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
                Text("Discard draft…", color = Vayu.colors.bad, fontWeight = FontWeight.SemiBold, modifier = Modifier
                    .clickable(role = Role.Button) { pages = false; confirm = "discard" }.padding(horizontal = 20.dp, vertical = 16.dp))
                Spacer(Modifier.height(16.dp))
            }
        }
    }

    when (confirm) {
        "discard" -> AlertDialog(onDismissRequest = { confirm = null },
            title = { Text("Start this inspection again?") },
            text = { Text("Every answer and photo saved on this phone for ${draft.code} is cleared, including photos not sent yet. This cannot be undone.") },
            confirmButton = { TextButton({ confirm = null; model.discard(); onClose() }) { Text("Discard draft", color = Vayu.colors.bad) } },
            dismissButton = { TextButton({ confirm = null }) { Text("Keep it") } })
        "submit" -> {
            val notOpened = steps.filter { !it.isReview && it.id !in draft.visited }
            AlertDialog(onDismissRequest = { confirm = null },
                title = { Text("Submit with ${notOpened.size} page${if (notOpened.size == 1) "" else "s"} not opened?") },
                text = { Text("You have not opened: ${notOpened.joinToString { it.title }}. Their questions are sent unanswered.") },
                confirmButton = { TextButton({ confirm = null; model.submit() }) { Text("Submit anyway") } },
                dismissButton = { TextButton({ confirm = null }) { Text("Go back") } })
        }
    }
}

private fun problemText(d: Draft) = when (d.problemCode) {
    "NOT_ASSIGNED" -> "This job was given to another expert. You can still submit what you did, or discard it."
    "INVALID_STAGE" -> "This job was cancelled. Your draft is still sent to Ops if you submit."
    "APP_TOO_OLD" -> "Update the app to start new jobs."
    else -> d.problem ?: ""
}

/** "Door photo 2": how the Uploads tab names a file. */
private fun label(f: Field, d: Draft, part: String): String {
    val n = ((d.answer(part, f.key) as? List<*>)?.size ?: 0) + 1
    return if (f.maxCount > 1) "${f.label} $n" else f.label
}

@Composable
private fun ReviewPage(draft: Draft, filled: Filled, steps: List<Step>, missingOn: (Step) -> Int, go: (Int) -> Unit,
                       modifier: Modifier, onSubmit: () -> Unit) {
    val refused = draft.fieldErrors.keys
    val gaps = filled.allGaps().let { g -> g + steps.mapNotNull { it.page }.flatMap { p -> p.fields }.filter { it.key in refused && g.none { x -> x.key == it.key } }
        .map { f -> `in`.carcid.vayu.core.forms.Gap("", f.key, f.label, steps.first { s -> s.page?.fields?.any { it.key == f.key } == true }.page!!.id,
            steps.first { s -> s.page?.fields?.any { it.key == f.key } == true }.title) } }
    val notOpened = steps.filter { !it.isReview && it.id !in draft.visited }
    val sent = draft.files.count { it.sent }
    Column(modifier.fillMaxWidth()) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            Spacer(Modifier.height(16.dp))
            if (gaps.isEmpty()) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Outlined.CheckCircle, null, tint = Vayu.colors.ok)
                Text("Everything needed is filled in.", color = Vayu.colors.ok, fontWeight = FontWeight.SemiBold)
            } else Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("${gaps.size}", fontSize = 34.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.bad)
                Text("answer${if (gaps.size == 1) "" else "s"} still needed", color = Vayu.colors.ink, modifier = Modifier.padding(bottom = 6.dp))
            }
            if (gaps.isNotEmpty()) {
                Text("STILL NEEDED", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.muted, modifier = Modifier.padding(top = 20.dp, bottom = 4.dp))
                gaps.forEach { g ->
                    val i = steps.indexOfFirst { (g.part.isEmpty() || it.part == g.part) && it.page?.id == g.pageId }
                    ReviewRow(g.label, g.pageTitle) { if (i >= 0) go(i) }
                }
            }
            if (notOpened.isNotEmpty()) {
                Text("NOT OPENED YET", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.muted, modifier = Modifier.padding(top = 20.dp, bottom = 4.dp))
                notOpened.forEach { s -> ReviewRow(s.title, null) { go(steps.indexOf(s)) } }
            }
            Text((if (draft.files.isNotEmpty()) "$sent of ${draft.files.size} files sent; the rest keep sending after you submit. " else "") +
                "Once submitted, only Ops can change answers.", color = Vayu.colors.muted, fontSize = 13.sp, modifier = Modifier.padding(top = 20.dp))
        }
        Box(Modifier.padding(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 16.dp)) {
            PrimaryButton("Submit inspection", onSubmit, enabled = gaps.isEmpty())
        }
    }
}

@Composable
private fun ReviewRow(title: String, sub: String?, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button, onClick = onClick), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(if (sub != null) Vayu.colors.bad else Vayu.colors.info))
        Column(Modifier.weight(1f)) {
            Text(title, color = Vayu.colors.ink, fontWeight = FontWeight.SemiBold)
            if (sub != null) Text(sub, fontSize = 13.sp, color = Vayu.colors.muted)
        }
        Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, tint = Vayu.colors.muted, modifier = Modifier.size(18.dp))
    }
    HorizontalDivider(color = Vayu.colors.line)
}

/** After Submit: answers are locked; files keep sending in the background. */
@Composable
fun SubmittedScreen(draft: Draft, onClose: () -> Unit) {
    BackHandler(onBack = onClose)
    val sent = draft.files.count { it.sent }
    val total = draft.files.size
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        IconButtonBack(onClose)
        Column(Modifier.padding(horizontal = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Spacer(Modifier.height(24.dp))
            Box(Modifier.size(72.dp).clip(CircleShape).background(Vayu.colors.okTint), contentAlignment = Alignment.Center) {
                Icon(Icons.Outlined.CheckCircle, null, tint = Vayu.colors.ok, modifier = Modifier.size(40.dp))
            }
            Text("Submitted", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink, modifier = Modifier.padding(top = 16.dp))
            Text("${draft.customer} · ${draft.code} · ${draft.submittedAt?.let(::shortTime) ?: ""}", color = Vayu.colors.muted,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            if (total > 0) {
                Row(Modifier.fillMaxWidth().padding(top = 28.dp)) {
                    Text(if (sent == total) "All files sent" else "Sending files", fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, modifier = Modifier.weight(1f))
                    Text("$sent of $total", color = Vayu.colors.muted)
                }
                Box(Modifier.padding(top = 8.dp).fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)).background(Vayu.colors.line)) {
                    Box(Modifier.fillMaxWidth(sent.toFloat() / total).height(6.dp).background(Vayu.colors.ok))
                }
                Text("They keep sending in the background, even with the app closed.", color = Vayu.colors.muted, fontSize = 13.sp,
                    modifier = Modifier.padding(top = 8.dp).fillMaxWidth())
            }
            Column(Modifier.fillMaxWidth().padding(top = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                StepLine(1, if (draft.submitSent) "Answers sent and locked" else "Answers locked; sending when there is signal", draft.submitSent)
                if (total > 0) StepLine(2, if (sent == total) "Files arrived" else "Files arriving · ${total - sent} left", sent == total)
                StepLine(if (total > 0) 3 else 2, "Completed, report made for Ops", false)
            }
            if (draft.problem != null) Text(problemText(draft), color = Vayu.colors.bad, modifier = Modifier.padding(top = 16.dp))
        }
    }
}

@Composable
private fun StepLine(n: Int, text: String, done: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(26.dp).clip(CircleShape).background(if (done) Vayu.colors.ok else Vayu.colors.soft), contentAlignment = Alignment.Center) {
            Text(if (done) "✓" else "$n", fontSize = 13.sp, fontWeight = FontWeight.Bold,
                color = if (done) androidx.compose.ui.graphics.Color.White else Vayu.colors.ink2)
        }
        Text(text, color = Vayu.colors.ink)
    }
}

@Composable
private fun IconButtonBack(onClick: () -> Unit) =
    androidx.compose.material3.IconButton(onClick = onClick, modifier = Modifier.padding(6.dp)) {
        Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back to My jobs", tint = Vayu.colors.ink)
    }

/** A form picture, fetched once and kept on the phone. */
suspend fun loadAsset(dir: File, id: String, fetch: suspend (String) -> ByteArray): ImageBitmap? = withContext(Dispatchers.IO) {
    if (!id.matches(Regex("[A-Za-z0-9-]{1,64}"))) return@withContext null
    val f = File(dir, "asset-$id")
    if (!f.exists()) runCatching { `in`.carcid.vayu.core.writeAtomically(f, fetch(id)) }
    runCatching { android.graphics.BitmapFactory.decodeFile(f.path)?.asImageBitmap() }.getOrNull()
}

