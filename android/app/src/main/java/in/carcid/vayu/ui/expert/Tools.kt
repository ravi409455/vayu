package `in`.carcid.vayu.ui.expert

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Paint
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.FlashOff
import androidx.compose.material.icons.outlined.FlashOn
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material.icons.outlined.Videocam
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import `in`.carcid.vayu.core.draft.LocalFile
import `in`.carcid.vayu.core.forms.Field
import `in`.carcid.vayu.core.media.Locator
import `in`.carcid.vayu.core.media.stampPhoto
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private val STAMP_TIME = DateTimeFormatter.ofPattern("d MMM yyyy HH:mm", Locale.ENGLISH)

/** The two stamp lines: "DEMO-8 · Ravi Expert · 24 Nov 2026 15:41" and the place. */
fun stampLines(code: String, expert: String, at: Instant, verified: Boolean, place: android.location.Location?): List<String> =
    listOf("$code · $expert · ${at.atZone(ZoneId.systemDefault()).format(STAMP_TIME)}" + if (verified) "" else " (phone time)",
        Locator.stampLine(place))

/** Ask for [permissions] once when the screen opens; [granted] says whether the first one was given. */
@Composable
fun rememberPermissions(vararg permissions: String, onResult: (Boolean) -> Unit = {}): Boolean {
    val ctx = LocalContext.current
    var ok by remember { mutableStateOf(ContextCompat.checkSelfPermission(ctx, permissions[0]) == PackageManager.PERMISSION_GRANTED) }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        ok = it[permissions[0]] == true; onResult(ok)
    }
    LaunchedEffect(Unit) { if (!ok || permissions.drop(1).any { p -> ContextCompat.checkSelfPermission(ctx, p) != PackageManager.PERMISSION_GRANTED }) ask.launch(arrayOf(*permissions)) }
    return ok
}

/**
 * The in-app camera (approved prototype): live preview with the stamp, one shutter, several shots
 * in a row up to the field's limit. Photos are stamped and shrunk; videos are 720p, at most 60 s.
 */
@SuppressLint("MissingPermission")
@Composable
fun CameraScreen(field: Field, have: Int, code: String, expert: String, now: () -> Instant, verified: Boolean,
                 dir: File, onTaken: (File, String) -> Unit, onDone: () -> Unit) {
    BackHandler(onBack = onDone)
    val video = field.type == "video"
    val ctx = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val camOk = if (video) rememberPermissions(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO,
        Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
        else rememberPermissions(Manifest.permission.CAMERA, Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
    var taken by remember { mutableStateOf(have) }
    var last by remember { mutableStateOf<File?>(null) }
    var busy by remember { mutableStateOf(false) }
    var recording by remember { mutableStateOf<Recording?>(null) }
    var seconds by remember { mutableStateOf(0) }
    var place by remember { mutableStateOf(Locator.last) }
    var clock by remember { mutableStateOf(now()) }
    LaunchedEffect(Unit) { place = Locator.fix(ctx) ?: place }
    LaunchedEffect(Unit) { while (true) { clock = now(); kotlinx.coroutines.delay(1000) } }
    val capture = remember { ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build() }
    val recorder = remember { Recorder.Builder().setQualitySelector(QualitySelector.from(Quality.HD)).build() }
    val videoCapture = remember { VideoCapture.withOutput(recorder) }
    val full = taken >= field.maxCount

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        if (camOk) AndroidView(factory = { c ->
            PreviewView(c).also { view ->
                val future = ProcessCameraProvider.getInstance(c)
                future.addListener({
                    val provider = future.get()
                    val preview = Preview.Builder().build().also { it.surfaceProvider = view.surfaceProvider }
                    provider.unbindAll()
                    provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, if (video) videoCapture else capture)
                }, ContextCompat.getMainExecutor(c))
            }
        }, modifier = Modifier.fillMaxSize())
        else Text("Allow the camera to take photos here.", color = Color.White, modifier = Modifier.align(Alignment.Center).padding(24.dp))

        Column(Modifier.fillMaxSize().safeDrawingPadding()) {
            Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                CloseButton("Close the camera", onDone, tint = Color.White)
                Column(Modifier.weight(1f)) {
                    Text(field.label, color = Color.White, fontWeight = FontWeight.Bold)
                    Text("$taken of ${field.maxCount} ${if (video) "recorded" else "taken"}", color = Color.White.copy(alpha = .8f), fontSize = 13.sp)
                }
                if (recording != null) Text("● %d:%02d / 1:00".format(seconds / 60, seconds % 60), color = Color(0xFFFF5A5A),
                    fontWeight = FontWeight.Bold, modifier = Modifier.padding(end = 12.dp))
            }
            Spacer(Modifier.weight(1f))
            Text(stampLines(code, expert, clock, verified, place).joinToString("\n"), color = Color.White, fontFamily = FontFamily.Monospace,
                fontSize = 12.sp, modifier = Modifier.padding(12.dp).background(Color.Black.copy(alpha = .45f)).padding(8.dp))
            Row(Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 20.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(56.dp).clip(RoundedCornerShape(12.dp)).background(Color.DarkGray)) {
                    last?.takeIf { !video }?.let { f -> rememberThumb(f.path)?.let { Image(it, "Last photo", contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize()) } }
                }
                Spacer(Modifier.weight(1f))
                Box(Modifier.size(76.dp).clip(CircleShape).border(4.dp, Color.White, CircleShape).padding(8.dp).clip(CircleShape)
                    .background(when { full && recording == null -> Color.Gray; video -> Color(0xFFE5484D); else -> Color.White })
                    .clickable(enabled = camOk && !busy && (!full || recording != null), role = Role.Button) {
                        if (video) {
                            val r = recording
                            if (r != null) { r.stop(); recording = null; return@clickable }
                            val out = newFile(dir, "mp4")
                            val opts = FileOutputOptions.Builder(out).setDurationLimitMillis(60_000).build()
                            seconds = 0
                            recording = videoCapture.output.prepareRecording(ctx, opts).let {
                                if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) it.withAudioEnabled() else it
                            }.start(ContextCompat.getMainExecutor(ctx)) { e ->
                                when (e) {
                                    is VideoRecordEvent.Status -> seconds = (e.recordingStats.recordedDurationNanos / 1_000_000_000).toInt()
                                    is VideoRecordEvent.Finalize -> {
                                        recording = null
                                        if (out.exists() && out.length() > 0) { onTaken(out, "video/mp4"); taken++ }
                                    }
                                }
                            }
                        } else {
                            busy = true
                            val raw = newFile(dir, "raw.jpg")
                            capture.takePicture(ImageCapture.OutputFileOptions.Builder(raw).build(), ContextCompat.getMainExecutor(ctx),
                                object : ImageCapture.OnImageSavedCallback {
                                    override fun onImageSaved(r: ImageCapture.OutputFileResults) {
                                        scope.launch {
                                            val out = newFile(dir, "jpg")
                                            withContext(Dispatchers.Default) {
                                                stampPhoto(raw, out, stampLines(code, expert, now(), verified, place)); raw.delete()
                                            }
                                            onTaken(out, "image/jpeg"); last = out; taken++; busy = false
                                        }
                                    }
                                    override fun onError(e: ImageCaptureException) { raw.delete(); busy = false }
                                })
                        }
                    }.semantics { contentDescription = if (video) (if (recording != null) "Stop recording" else "Record") else "Take photo" })
                Spacer(Modifier.weight(1f))
                Text("Done", color = Color.White, fontWeight = FontWeight.Bold, modifier = Modifier.clickable(role = Role.Button) {
                    recording?.stop(); onDone()
                }.padding(12.dp))
            }
        }
    }
}

/** Full-screen signature pad; saved as a PNG on white. */
@Composable
fun SignatureScreen(field: Field, dir: File, onSigned: (File) -> Unit, onClose: () -> Unit) {
    BackHandler(onBack = onClose)
    val strokes = remember { mutableStateListOf<List<Offset>>() }
    var current by remember { mutableStateOf<List<Offset>>(emptyList()) }
    var size by remember { mutableStateOf(IntSize(1, 1)) }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            CloseButton("Close", onClose)
            Text(field.label, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink, modifier = Modifier.weight(1f))
        }
        Text("Sign with your finger inside the box.", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 8.dp))
        Canvas(Modifier.fillMaxWidth().weight(1f).clip(RoundedCornerShape(14.dp)).background(Color.White)
            .border(1.dp, Vayu.colors.line2, RoundedCornerShape(14.dp)).onSizeChanged { size = it }
            .semantics { contentDescription = "Signature pad" }
            .pointerInput(Unit) {
                detectDragGestures(onDragStart = { current = listOf(it) },
                    onDragEnd = { strokes.add(current); current = emptyList() }) { change, _ -> current = current + change.position }
            }) {
            (strokes + listOf(current)).filter { it.size > 1 }.forEach { pts ->
                drawPath(Path().apply { moveTo(pts[0].x, pts[0].y); pts.drop(1).forEach { lineTo(it.x, it.y) } },
                    Color(0xFF1C2330), style = Stroke(6f, cap = StrokeCap.Round, join = StrokeJoin.Round))
            }
        }
        Row(Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SoftButton("Clear", { strokes.clear() }, Modifier.weight(1f))
            PrimaryButton("Use this signature", {
                val bmp = Bitmap.createBitmap(size.width, size.height, Bitmap.Config.ARGB_8888)
                val c = android.graphics.Canvas(bmp).apply { drawColor(android.graphics.Color.WHITE) }
                val p = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                    color = android.graphics.Color.rgb(28, 35, 48); strokeWidth = 6f; style = Paint.Style.STROKE
                    strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
                }
                strokes.filter { it.size > 1 }.forEach { pts ->
                    c.drawPath(android.graphics.Path().apply { moveTo(pts[0].x, pts[0].y); pts.drop(1).forEach { lineTo(it.x, it.y) } }, p)
                }
                val out = newFile(dir, "png")
                FileOutputStream(out).use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
                bmp.recycle()
                onSigned(out)
            }, Modifier.weight(1f), enabled = strokes.isNotEmpty())
        }
    }
}

/** What a scan found: runs of letters and digits (a chassis number is 17), longest first, at most 5. */
fun scanCandidates(lines: List<String>): List<String> = lines
    // a label before a colon ("VIN: ...") is not part of the number; spaces inside it are dropped
    .map { it.uppercase().substringAfterLast(':') }
    .flatMap { l -> listOf(l.replace(Regex("[^A-Z0-9]"), "")) + Regex("[A-Z0-9]{5,}").findAll(l).map { it.value } }
    .filter { it.length >= 5 }.distinct().sortedByDescending { it.length }.take(5)

/**
 * Scan a short text with the camera, on the phone (no signal needed). It reads only when the
 * expert taps Read, and only the text inside the box; they pick the right result and can still
 * type over it. Tap the picture to focus; the torch helps under a bonnet.
 */
@SuppressLint("UnsafeOptInUsageError", "ClickableViewAccessibility")
@Composable
fun ScanScreen(field: Field, current: String?, onUse: (String) -> Unit, onClose: () -> Unit) {
    BackHandler(onBack = onClose)
    val owner = LocalLifecycleOwner.current
    val ok = rememberPermissions(Manifest.permission.CAMERA)
    var text by remember { mutableStateOf(current ?: "") }
    var found by remember { mutableStateOf<List<String>?>(null) }
    var reading by remember { mutableStateOf(false) }
    var torch by remember { mutableStateOf(false) }
    var camera by remember { mutableStateOf<androidx.camera.core.Camera?>(null) }
    val armed = remember { java.util.concurrent.atomic.AtomicBoolean(false) }
    val recognizer = remember { TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS) }
    DisposableEffect(Unit) { onDispose { recognizer.close() } }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            CloseButton("Close", onClose)
            Text("Scan ${field.label.lowercase()}", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink, modifier = Modifier.weight(1f))
            androidx.compose.material3.IconButton(onClick = { torch = !torch; camera?.cameraControl?.enableTorch(torch) }) {
                Icon(if (torch) androidx.compose.material.icons.Icons.Outlined.FlashOn else androidx.compose.material.icons.Icons.Outlined.FlashOff,
                    contentDescription = if (torch) "Turn the torch off" else "Turn the torch on", tint = Vayu.colors.ink)
            }
        }
        Box(Modifier.fillMaxWidth().height(300.dp).padding(horizontal = 16.dp).clip(RoundedCornerShape(16.dp)).background(Color.Black)) {
            if (ok) AndroidView(factory = { c ->
                PreviewView(c).also { view ->
                    val future = ProcessCameraProvider.getInstance(c)
                    future.addListener({
                        val provider = future.get()
                        val preview = Preview.Builder().build().also { it.surfaceProvider = view.surfaceProvider }
                        val analysis = ImageAnalysis.Builder().setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
                        analysis.setAnalyzer(ContextCompat.getMainExecutor(c)) { proxy ->
                            val media = proxy.image
                            // nothing is read until the expert taps Read: no racing text
                            if (media == null || !armed.getAndSet(false)) { proxy.close(); return@setAnalyzer }
                            val turned = proxy.imageInfo.rotationDegrees % 180 != 0
                            val w = if (turned) proxy.height else proxy.width
                            val h = if (turned) proxy.width else proxy.height
                            recognizer.process(InputImage.fromMediaImage(media, proxy.imageInfo.rotationDegrees))
                                .addOnSuccessListener { r ->
                                    // only lines whose middle is inside the box (the middle third of the picture)
                                    val inBox = r.textBlocks.flatMap { it.lines }.filter { l ->
                                        val b = l.boundingBox ?: return@filter false
                                        b.centerY() in (h / 3)..(h * 2 / 3) && b.centerX() in (w / 10)..(w * 9 / 10)
                                    }.map { it.text }
                                    found = scanCandidates(inBox)
                                    found?.firstOrNull()?.let { if (text.isBlank()) text = it }
                                }
                                .addOnCompleteListener { reading = false; proxy.close() }
                        }
                        provider.unbindAll()
                        camera = provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                    }, ContextCompat.getMainExecutor(c))
                    // tap to focus on the number
                    view.setOnTouchListener { v, e ->
                        if (e.action == android.view.MotionEvent.ACTION_UP) camera?.cameraControl?.startFocusAndMetering(
                            androidx.camera.core.FocusMeteringAction.Builder(view.meteringPointFactory.createPoint(e.x, e.y)).build())
                        v.performClick(); true
                    }
                }
            }, modifier = Modifier.fillMaxSize())
            // the box: put the number inside it
            Box(Modifier.align(Alignment.Center).fillMaxWidth(0.84f).height(86.dp).border(2.dp, Color.White, RoundedCornerShape(10.dp)))
            Text(if (reading) "Reading…" else "Put the number inside the box, tap to focus, then Read", color = Color.White,
                fontSize = 13.sp, modifier = Modifier.align(Alignment.BottomCenter).padding(10.dp))
        }
        Column(Modifier.verticalScroll(androidx.compose.foundation.rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PrimaryButton(if (reading) "Reading…" else if (found == null) "Read" else "Read again", {
                if (!reading) { reading = true; armed.set(true) }
            }, enabled = ok && !reading)
            when {
                found == null -> {}
                found!!.isEmpty() -> Text("Nothing readable in the box. Move closer, tap to focus, and read again.", color = Vayu.colors.warn, fontSize = 14.sp)
                else -> {
                    Text("Tap the right one", color = Vayu.colors.muted, fontSize = 13.sp)
                    found!!.forEach { c ->
                        Text(c, fontFamily = FontFamily.Monospace, fontSize = 17.sp, color = if (c == text) Vayu.colors.onPrimary else Vayu.colors.ink,
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp))
                                .background(if (c == text) Vayu.colors.primary else Vayu.colors.soft)
                                .clickable(role = Role.RadioButton) { text = c }.padding(horizontal = 14.dp, vertical = 12.dp))
                    }
                }
            }
            Text("Check it against the car; you can type over it", color = Vayu.colors.muted, fontSize = 13.sp)
            SoftField(text, { text = it.uppercase() }, field.label)
            PrimaryButton("Use this", { onUse(text.trim()) }, enabled = text.isNotBlank())
        }
    }
}

/** One taken file, large, with Delete and Retake. */
@Composable
fun FileReview(field: Field, file: LocalFile, index: Int, count: Int, locked: Boolean, onDelete: () -> Unit, onRetake: () -> Unit, onClose: () -> Unit) {
    BackHandler(onBack = onClose)
    val status = when { file.sent -> "Sent"; file.error != null -> file.error; file.progress > 0f -> "Uploading ${(file.progress * 100).toInt()}%"; else -> "Waiting to send" }
    Column(Modifier.fillMaxSize().background(Color.Black).safeDrawingPadding()) {
        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            CloseButton("Back", onClose, tint = Color.White)
            Column {
                Text("${field.label} · $index of $count", color = Color.White, fontWeight = FontWeight.Bold)
                Text(status, color = Color.White.copy(alpha = .8f), fontSize = 13.sp)
            }
        }
        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            val img = if (file.contentType.startsWith("image/")) rememberThumb(file.path, 1400) else null
            if (img != null) Image(img, file.label, contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize())
            else Icon(if (file.kind == "video") Icons.Outlined.Videocam else Icons.Outlined.PhotoCamera, null, tint = Color.White, modifier = Modifier.size(64.dp))
        }
        if (!locked) Row(Modifier.fillMaxWidth().padding(20.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
            Column(Modifier.clickable(role = Role.Button, onClick = onDelete).padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Outlined.Delete, null, tint = Color.White); Text("Delete", color = Color.White)
            }
            if (field.type != "file") Column(Modifier.clickable(role = Role.Button, onClick = onRetake).padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Outlined.PhotoCamera, null, tint = Color.White); Text("Retake", color = Color.White)
            }
        }
    }
}
