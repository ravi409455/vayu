package `in`.carcid.vayu.ui.expert

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.graphics.BitmapFactory
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccessTime
import androidx.compose.material.icons.outlined.AttachFile
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Draw
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Image
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material.icons.outlined.PhotoLibrary
import androidx.compose.material.icons.outlined.PictureAsPdf
import androidx.compose.material.icons.outlined.QrCodeScanner
import androidx.compose.material.icons.outlined.Videocam
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.draft.LocalFile
import `in`.carcid.vayu.core.forms.Field
import `in`.carcid.vayu.core.forms.Option
import `in`.carcid.vayu.core.rules.FormRules
import `in`.carcid.vayu.ui.components.ChoiceRow
import `in`.carcid.vayu.ui.components.StackedOption
import `in`.carcid.vayu.ui.components.ToggleChip
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.time.LocalDate
import java.time.LocalTime

/** How a choice question is laid out (approved rule, docs/android-requirements.md). */
enum class ChoiceLayout { ROW, STACK, LIST }

fun choiceLayout(labels: List<String>): ChoiceLayout = when {
    labels.size <= 4 && labels.all { it.length <= 12 } -> ChoiceLayout.ROW
    labels.size <= 8 -> ChoiceLayout.STACK
    else -> ChoiceLayout.LIST
}

/** What a question needs from around it: lists, files, and the actions that open other screens. */
class FieldEnv(
    val locked: Boolean,
    val list: (String) -> List<Pair<String, String>>,
    val types: List<Pair<String, String>>,
    val files: Map<String, LocalFile>,
    val now: () -> java.time.Instant,
    val onCamera: (Field) -> Unit,
    val onGallery: (Field) -> Unit,
    val onPickFile: (Field) -> Unit,
    val onSign: (Field) -> Unit,
    val onScan: (Field) -> Unit,
    val onOpenFile: (Field, LocalFile) -> Unit,
    val onLocate: (Field, (Map<String, Any?>?) -> Unit) -> Unit,
    val asset: suspend (String) -> ImageBitmap?,
    /** People for "pick a user" fields (Ops): id, name, role. Empty on the expert's phone. */
    val people: List<Triple<String, String, String>> = emptyList(),
)

/** One question: label (with * when needed), its input, help or what is missing. */
@Composable
fun Question(f: Field, value: Any?, required: Boolean, missing: Boolean, error: String?, nested: Boolean,
             env: FieldEnv, onChange: (Any?) -> Unit) {
    val readOnly = env.locked || !f.editable
    val bar = Vayu.colors.warn
    Column(Modifier.fillMaxWidth().padding(vertical = 14.dp)) {
        // a follow-up question (shown because of the one above) hangs off it with an amber rule
        Column(Modifier.let { m -> if (!nested) m else m.drawBehind {
                drawRect(bar, size = androidx.compose.ui.geometry.Size(3.dp.toPx(), size.height)) }.padding(start = 16.dp) },
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (f.type != "image") Row {
                Text(f.label, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = Vayu.colors.ink)
                if (required) Text(" *", fontWeight = FontWeight.SemiBold, color = Vayu.colors.bad,
                    modifier = Modifier.semantics { contentDescription = "required" })
                if (f.isMedia && f.type != "signature") {
                    val n = (value as? List<*>)?.size ?: 0
                    Text("  $n of ${f.maxCount}", color = Vayu.colors.muted, fontSize = 13.sp)
                }
            }
            Input(f, value, missing, readOnly, env, onChange)
            when {
                error != null && error != "required" -> Note(errorText(error), Vayu.colors.bad)
                missing -> Note("Needed" + (if (f.help.isNotBlank()) ": ${f.help}" else ""), Vayu.colors.bad)
                f.help.isNotBlank() -> Note(f.help, Vayu.colors.muted)
            }
        }
    }
    HorizontalDivider(color = Vayu.colors.line)
}

private fun errorText(code: String) = when (code) {
    "check_failed" -> "This doesn't fit with another answer."
    "UNKNOWN_MEDIA" -> "A file didn't arrive; take it again."
    else -> code.replace('_', ' ').lowercase().replaceFirstChar { it.uppercase() }
}

@Composable
private fun Note(text: String, color: androidx.compose.ui.graphics.Color) =
    Text(text, fontSize = 13.sp, color = color, fontWeight = if (color == Vayu.colors.bad) FontWeight.Medium else FontWeight.Normal)

@Composable
private fun Input(f: Field, value: Any?, missing: Boolean, readOnly: Boolean, env: FieldEnv, onChange: (Any?) -> Unit) {
    when (f.type) {
        "short_text", "phone", "long_text" -> TextInput(f, value as? String ?: "", missing, readOnly, env,
            keyboard = if (f.type == "phone") KeyboardType.Phone else KeyboardType.Text) { onChange(it.ifEmpty { null }) }
        "number", "currency" -> TextInput(f, (value as? Double)?.let { if (it % 1.0 == 0.0) it.toLong().toString() else it.toString() } ?: (value as? String ?: ""),
            missing, readOnly, env, keyboard = KeyboardType.Decimal) { t -> onChange(t.toDoubleOrNull() ?: if (t.isEmpty()) null else t) }
        "date", "time", "datetime" -> DateInput(f, value as? String, readOnly, env, onChange)
        "yes_no" -> {
            val sel = when (value) { true -> "Yes"; false -> "No"; else -> null }
            ChoiceRow(listOf("Yes" to false, "No" to false), sel) { if (!readOnly) onChange(if (it == sel) null else it == "Yes") }
        }
        "single_choice" -> SingleChoice(f.label, f.options, value as? String, readOnly, onChange)
        "multi_choice" -> MultiChoice(f.options, (value as? List<*>)?.filterIsInstance<String>().orEmpty(), readOnly, onChange)
        "master_list" -> SingleChoice(f.label, env.list(f.config["list"] as? String ?: "").map { Option(it.first, it.second, false, null) },
            value as? String, readOnly, onChange, forceList = true)
        "form_choice" -> SingleChoice(f.label, env.types.map { Option(it.first, it.second, false, null) }, value as? String, readOnly, onChange, forceList = true)
        "user_picker" -> if (env.people.isEmpty()) Text(if (value == null) "—" else "Set by Ops", color = Vayu.colors.muted)
            else SingleChoice(f.label, env.people.filter { it.third == (f.config["role"] as? String ?: "expert") }.map { Option(it.first, it.second, false, null) },
                (value as? Number)?.toLong()?.toString(), readOnly, { onChange((it as? String)?.toDouble()) }, forceList = true)
        "gps" -> Gps(f, value, readOnly, env, onChange)
        "photo", "video", "file" -> MediaTiles(f, value, readOnly, env)
        "signature" -> Signature(f, value as? String, readOnly, env)
        "image" -> FormImage(f, env)
        else -> Text(value?.toString() ?: "—", color = Vayu.colors.muted)
    }
}

@Composable
private fun TextInput(f: Field, value: String, missing: Boolean, readOnly: Boolean, env: FieldEnv,
                      keyboard: KeyboardType, onChange: (String) -> Unit) {
    val scan = f.type == "short_text" && f.config["scan"] == true && !readOnly
    val long = f.type == "long_text"
    Row(Modifier.fillMaxWidth().heightIn(min = if (long) 96.dp else 52.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.soft)
        .let { if (missing) it.border(2.dp, Vayu.colors.bad, RoundedCornerShape(12.dp)) else it }
        .padding(start = 14.dp, end = 6.dp), verticalAlignment = if (long) Alignment.Top else Alignment.CenterVertically) {
        if (f.type == "currency") Text("₹ ", color = Vayu.colors.muted)
        BasicTextField(value, onChange, readOnly = readOnly, singleLine = !long,
            keyboardOptions = KeyboardOptions(keyboardType = keyboard),
            textStyle = MaterialTheme.typography.bodyLarge.copy(color = Vayu.colors.ink,
                fontFamily = if (scan) FontFamily.Monospace else FontFamily.Default),
            cursorBrush = SolidColor(Vayu.colors.ink),
            modifier = Modifier.weight(1f).padding(vertical = 14.dp).semantics { contentDescription = f.label })
        (f.config["unit"] as? String)?.takeIf { it.isNotBlank() }?.let { Text(it, color = Vayu.colors.muted, modifier = Modifier.padding(end = 10.dp)) }
        if (scan) IconButton(onClick = { env.onScan(f) }, modifier = Modifier.size(40.dp).clip(CircleShape).background(Vayu.colors.bg)) {
            Icon(Icons.Outlined.QrCodeScanner, contentDescription = "Scan with the camera", tint = Vayu.colors.ink)
        }
    }
}

@Composable
private fun DateInput(f: Field, value: String?, readOnly: Boolean, env: FieldEnv, onChange: (Any?) -> Unit) {
    if (f.config["auto"] == true) {
        // stamped once, when the question first shows; never typed
        LaunchedEffect(f.key) { if (value == null && !readOnly) onChange(stamp(f.type, env.now())) }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Icons.Outlined.AccessTime, contentDescription = null, tint = Vayu.colors.ok, modifier = Modifier.size(18.dp))
            Text(if (value == null) "…" else "Recorded · " + when (f.type) {
                "time" -> time12(value); "date" -> dayLabel(value, LocalDate.now()); else -> shortTime(value)
            }, color = Vayu.colors.ok, fontSize = 14.sp)
        }
        return
    }
    val ctx = LocalContext.current
    val shown = when {
        value == null -> "Choose…"
        f.type == "time" -> time12(value)
        f.type == "date" -> dayLabel(value, LocalDate.now()).let { if (it.isEmpty()) value else it }
        else -> value.take(16).replace('T', ' ')
    }
    fun pickTime(day: String?) {
        val t = runCatching { LocalTime.parse((value ?: "").takeLast(5).take(5)) }.getOrDefault(LocalTime.now())
        TimePickerDialog(ctx, { _, h, m ->
            val hm = "%02d:%02d".format(h, m)
            onChange(if (day == null) hm else stamp("datetime", java.time.LocalDateTime.parse("${day}T$hm").atZone(java.time.ZoneId.systemDefault()).toInstant()))
        }, t.hour, t.minute, false).show()
    }
    Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.soft)
        .clickable(enabled = !readOnly, role = Role.Button) {
            if (f.type == "time") pickTime(null) else {
                val d = runCatching { LocalDate.parse(value!!.take(10)) }.getOrDefault(LocalDate.now())
                DatePickerDialog(ctx, { _, y, mo, day ->
                    val iso = LocalDate.of(y, mo + 1, day).toString()
                    if (f.type == "date") onChange(iso) else pickTime(iso)
                }, d.year, d.monthValue - 1, d.dayOfMonth).show()
            }
        }.padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(shown, color = if (value == null) Vayu.colors.muted else Vayu.colors.ink, modifier = Modifier.weight(1f))
        Icon(if (f.type == "time") Icons.Outlined.AccessTime else Icons.Outlined.CalendarMonth, contentDescription = null, tint = Vayu.colors.muted)
    }
}

private fun severityLabel(o: Option) = if (!o.isDefect) null
    else (o.severity ?: "minor").replaceFirstChar { it.uppercase() }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SingleChoice(label: String, options: List<Option>, value: String?, readOnly: Boolean, onChange: (Any?) -> Unit,
                 forceList: Boolean = false) {
    val layout = if (forceList && options.size > 8) ChoiceLayout.LIST else choiceLayout(options.map { it.label })
    val pick = { key: String -> if (!readOnly) onChange(if (key == value) null else key) }
    when (layout) {
        ChoiceLayout.ROW -> {
            val byLabel = options.associateBy { it.label }
            ChoiceRow(options.map { it.label to it.isDefect }, options.firstOrNull { it.key == value }?.label) { l -> byLabel[l]?.let { pick(it.key) } }
        }
        ChoiceLayout.STACK -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            options.forEach { o -> StackedOption(o.label, o.key == value, severityLabel(o)) { pick(o.key) } }
        }
        ChoiceLayout.LIST -> {
            var open by remember { mutableStateOf(false) }
            Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.soft)
                .clickable(enabled = !readOnly, role = Role.Button) { open = true }.padding(horizontal = 14.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(options.firstOrNull { it.key == value }?.label ?: value ?: "Choose…",
                    color = if (value == null) Vayu.colors.muted else Vayu.colors.ink, modifier = Modifier.weight(1f))
                Icon(Icons.Outlined.ExpandMore, contentDescription = null, tint = Vayu.colors.muted)
            }
            if (open) ModalBottomSheet(onDismissRequest = { open = false }, containerColor = Vayu.colors.bg) {
                Text(label, fontWeight = FontWeight.Bold, fontSize = 17.sp, color = Vayu.colors.ink,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
                LazyColumn(Modifier.fillMaxWidth().heightIn(max = 520.dp)) {
                    items(options, key = { it.key }) { o ->
                        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clickable(role = Role.Button) { pick(o.key); open = false }
                            .padding(horizontal = 20.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(o.label, color = Vayu.colors.ink, modifier = Modifier.weight(1f),
                                fontWeight = if (o.key == value) FontWeight.SemiBold else FontWeight.Normal)
                            if (o.key == value) Icon(Icons.Outlined.Check, contentDescription = "Chosen", tint = Vayu.colors.ink)
                        }
                    }
                }
                Spacer(Modifier.height(24.dp))
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun MultiChoice(options: List<Option>, chosen: List<String>, readOnly: Boolean, onChange: (Any?) -> Unit) {
    val toggle = { key: String, on: Boolean ->
        if (!readOnly) onChange((if (on) chosen + key else chosen - key).ifEmpty { null })
    }
    if (options.size <= 8) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { o -> ToggleChip(o.label, o.key in chosen) { toggle(o.key, it) } }
    } else Column {
        options.forEach { o ->
            val on = o.key in chosen
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(role = Role.Checkbox) { toggle(o.key, !on) },
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(22.dp).clip(RoundedCornerShape(6.dp)).background(if (on) Vayu.colors.primary else Vayu.colors.soft),
                    contentAlignment = Alignment.Center) {
                    if (on) Icon(Icons.Outlined.Check, contentDescription = null, tint = Vayu.colors.onPrimary, modifier = Modifier.size(16.dp))
                }
                Text(o.label, color = Vayu.colors.ink)
            }
        }
    }
}

@Composable
private fun Gps(f: Field, value: Any?, readOnly: Boolean, env: FieldEnv, onChange: (Any?) -> Unit) {
    var state by remember { mutableStateOf("idle") }
    val auto = f.config["auto"] != false
    val capture = { state = "busy"; env.onLocate(f) { fix -> state = if (fix == null) "unavailable" else "idle"; if (fix != null) onChange(fix) } }
    LaunchedEffect(f.key) { if (value == null && !readOnly && auto) capture() }
    val v = value as? Map<*, *>
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Icon(Icons.Outlined.LocationOn, contentDescription = null, tint = if (v != null) Vayu.colors.ok else Vayu.colors.muted, modifier = Modifier.size(18.dp))
        Text(when {
            v != null -> "Location recorded · %.4f, %.4f".format((v["lat"] as Number).toDouble(), (v["lng"] as Number).toDouble()) +
                ((v["accuracy"] as? Number)?.let { " (±${it.toInt()} m)" } ?: "")
            state == "busy" -> "Finding your location…"
            state == "unavailable" -> "GPS unavailable"
            else -> "Not recorded yet"
        }, color = if (v != null) Vayu.colors.ok else Vayu.colors.muted, fontSize = 14.sp, modifier = Modifier.weight(1f))
        if (!readOnly && state != "busy" && (v != null || state == "unavailable" || !auto))
            Text(if (v != null) "Update" else if (state == "unavailable") "Try again" else "Capture", color = Vayu.colors.info,
                fontWeight = FontWeight.SemiBold, fontSize = 14.sp, modifier = Modifier.clickable(role = Role.Button) { capture() }.padding(6.dp))
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun MediaTiles(f: Field, value: Any?, readOnly: Boolean, env: FieldEnv) {
    val ids = (value as? List<*>)?.filterIsInstance<String>().orEmpty()
    val mode = if (f.type == "file") "upload" else (f.config["capture"] as? String ?: "both")
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        ids.forEach { id -> env.files[id]?.let { Tile(f, it, env) } }
        if (!readOnly && ids.size < f.maxCount) {
            if (mode != "upload") AddTile(if (f.type == "video") Icons.Outlined.Videocam else Icons.Outlined.PhotoCamera, "Camera",
                if (f.type == "video") "Record a video" else "Take a photo") { env.onCamera(f) }
            if (mode == "both" && f.type != "file") AddTile(Icons.Outlined.PhotoLibrary, "Gallery", "Pick from gallery") { env.onGallery(f) }
            if (f.type == "file") AddTile(Icons.Outlined.AttachFile, "Add file", "Add a file") { env.onPickFile(f) }
        }
    }
}

@Composable
private fun AddTile(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, description: String, onClick: () -> Unit) {
    Column(Modifier.size(76.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.soft)
        .border(BorderStroke(1.5.dp, Vayu.colors.line2), RoundedCornerShape(12.dp))
        .clickable(role = Role.Button, onClick = onClick).semantics { contentDescription = description },
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Icon(icon, contentDescription = null, tint = Vayu.colors.ink2, modifier = Modifier.size(22.dp))
        Text(label, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink2)
    }
}

/** A small preview of a picture on the phone (decoded at tile size, off the main thread). */
@Composable
fun rememberThumb(path: String, size: Int = 160): ImageBitmap? = produceState<ImageBitmap?>(null, path) {
    value = withContext(Dispatchers.IO) {
        runCatching {
            val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(path, o)
            var s = 1
            while (o.outWidth / (s * 2) >= size && o.outHeight / (s * 2) >= size) s *= 2
            BitmapFactory.decodeFile(path, BitmapFactory.Options().apply { inSampleSize = s })?.asImageBitmap()
        }.getOrNull()
    }
}.value

@Composable
private fun Tile(f: Field, file: LocalFile, env: FieldEnv) {
    val thumb = if (file.contentType.startsWith("image/")) rememberThumb(file.path) else null
    val status = when { file.sent -> "sent"; file.error != null -> "not sent"; file.progress > 0f -> "sending"; else -> "waiting to send" }
    Box(Modifier.size(76.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.illo)
        .clickable(role = Role.Button) { env.onOpenFile(f, file) }.semantics { contentDescription = "${file.label}, $status" },
        contentAlignment = Alignment.Center) {
        if (thumb != null) Image(thumb, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        else Icon(when { file.kind == "video" -> Icons.Outlined.Videocam; file.contentType == "application/pdf" -> Icons.Outlined.PictureAsPdf; else -> Icons.Outlined.Image },
            contentDescription = null, tint = Vayu.colors.muted)
        when {
            file.sent -> Box(Modifier.align(Alignment.BottomEnd).padding(5.dp).size(18.dp).clip(CircleShape).background(Vayu.colors.ok),
                contentAlignment = Alignment.Center) { Icon(Icons.Outlined.Check, null, tint = androidx.compose.ui.graphics.Color.White, modifier = Modifier.size(12.dp)) }
            file.error != null -> Icon(Icons.Outlined.ErrorOutline, null, tint = Vayu.colors.bad,
                modifier = Modifier.align(Alignment.BottomEnd).padding(4.dp).size(18.dp).clip(CircleShape).background(Vayu.colors.bg))
            file.progress > 0f -> Box(Modifier.align(Alignment.BottomCenter).padding(8.dp).fillMaxWidth().height(4.dp)
                .clip(RoundedCornerShape(2.dp)).background(androidx.compose.ui.graphics.Color.Black.copy(alpha = .15f))) {
                Box(Modifier.fillMaxWidth(file.progress).height(4.dp).background(Vayu.colors.info))
            }
        }
    }
}

@Composable
private fun Signature(f: Field, value: String?, readOnly: Boolean, env: FieldEnv) {
    val file = value?.let { env.files[it] }
    if (file != null) Box(Modifier.fillMaxWidth().height(120.dp).clip(RoundedCornerShape(12.dp)).background(androidx.compose.ui.graphics.Color.White)
        .border(BorderStroke(1.dp, Vayu.colors.line2), RoundedCornerShape(12.dp))
        .clickable(enabled = !readOnly, role = Role.Button) { env.onSign(f) }) {
        rememberThumb(file.path, 600)?.let { Image(it, "Signature", contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize()) }
    } else if (!readOnly) AddTile(Icons.Outlined.Draw, "Sign", "Sign here") { env.onSign(f) }
    else Text("—", color = Vayu.colors.muted)
}

@Composable
private fun FormImage(f: Field, env: FieldEnv) {
    val id = f.config["asset"] as? String
    val bmp = produceState<ImageBitmap?>(null, id) { value = id?.let { env.asset(it) } }.value
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (f.label.isNotBlank()) Text(f.label, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
        if (bmp != null) Image(bmp, f.label, contentScale = ContentScale.FillWidth,
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)))
        else Text(if (id == null) "No picture." else "The picture shows once the phone has signal.", color = Vayu.colors.muted, fontSize = 13.sp)
    }
}

/** Answered for counting ("1 of 2"): media and lists count when not empty. */
fun answered(v: Any?) = !FormRules.isEmpty(v)

/** A big close (X) used on full-screen tools. */
@Composable
fun CloseButton(description: String, onClick: () -> Unit, tint: androidx.compose.ui.graphics.Color = Vayu.colors.ink) =
    IconButton(onClick = onClick) { Icon(Icons.Outlined.Close, contentDescription = description, tint = tint) }

/** Helper for screens that need a file in the draft's folder. */
fun newFile(dir: File, ext: String): File = File(dir, "${java.util.UUID.randomUUID()}.$ext")
