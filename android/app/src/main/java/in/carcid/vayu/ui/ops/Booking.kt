package `in`.carcid.vayu.ui.ops

import `in`.carcid.vayu.core.ops.Inspection
import `in`.carcid.vayu.core.api.initials

import `in`.carcid.vayu.core.ARRIVED

import `in`.carcid.vayu.core.forms.PARTS
import `in`.carcid.vayu.core.forms.FormTree
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.FlowRow
import `in`.carcid.vayu.ui.components.TimePick
import `in`.carcid.vayu.ui.components.DatePick
import `in`.carcid.vayu.ui.expert.whenStamp
import `in`.carcid.vayu.ui.components.VayuSheet
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.outlined.Call
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.Directions
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material.icons.outlined.PersonAdd
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.forms.Option
import `in`.carcid.vayu.core.ops.o
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.s
import `in`.carcid.vayu.ui.components.Avatar
import `in`.carcid.vayu.ui.components.Banner
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.Tone
import `in`.carcid.vayu.ui.expert.SingleChoice
import `in`.carcid.vayu.ui.expert.phoneLabel
import `in`.carcid.vayu.ui.expert.dayLabel
import `in`.carcid.vayu.ui.expert.time12
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.net.URLEncoder
import java.time.LocalDate
import java.time.LocalTime

/** Where a booking's rows lead. */
enum class Part { ANSWERS, MEDIA, REVIEW, HISTORY }

/** The inspection that counts on a booking: the latest submitted one, else the latest draft. */
fun currentInspection(list: List<Inspection>): Inspection? =
    list.filter { it.status == "submitted" }.maxByOrNull { it.submittedAt }
        ?: list.filter { it.status == "draft" }.maxByOrNull { it.createdAt }

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun BookingScreen(env: OpsEnv, id: String, onBack: () -> Unit, onPart: (Part) -> Unit, onAnswers: (String) -> Unit, onEdit: () -> Unit) {
    val uri = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    val t = env.today()
    val load = rememberLoad(env, "bookings/$id")
    val insps = Inspection.list(rememberLoad(env, "bookings/$id/inspections").value?.data?.rows().orEmpty())
    val report = rememberLoad(env, "bookings/$id/report")
    val b = load.value?.data?.let { Bk(it as JsonObject) }
    var menu by remember { mutableStateOf(false) }
    var action by remember { mutableStateOf<String?>(null) }
    var compare by remember { mutableStateOf(false) }
    var saving by remember { mutableStateOf<String?>(null) }
    val online = load.value?.offline == false
    if (b == null) {
        Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
            SubHeader("Booking", onBack = onBack)
            Text(load.error ?: "Loading…", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp))
        }
        return
    }
    val insp = currentInspection(insps)
    val run: (String, String, JsonObject?, String) -> Unit = { method, path, body, done ->
        scope.launch {
            try { env.data.act(method, path, body); action = null; env.say(done); env.refresh() }
            catch (e: ApiError) { env.say(e.message) }
        }
    }
    val raw = rememberForms(env, insp)
    val data = Loaded3(b, insp, raw.mapValues { it.value?.let(FormTree::parse) }, raw, !online, insps)
    val filled = data.filled(t.toString())
    val actions = listOfNotNull(
        ("Edit booking" to "edit").takeIf { env.can("bookings.edit") && b.live },
        ((if (b.expert == null) "Assign an expert" else "Reassign") to "assign").takeIf { env.can("bookings.assign") && b.stage in setOf("draft", "assigned") },
        ("Reschedule" to "reschedule").takeIf { env.can("bookings.reschedule") && b.live },
        ("Change type" to "type").takeIf { env.can("bookings.edit") && b.stage in setOf("draft", "assigned") },
        ("Force release" to "release").takeIf { env.can("bookings.force_release") && b.stage == "in_progress" },
        ("Sign out the expert's phone" to "signout").takeIf { env.can("users.sign_out_devices") && b.expert != null },
        ("Cancel booking" to "cancel").takeIf { env.can("bookings.cancel") && b.live },
        ("Delete booking" to "delete").takeIf { env.can("bookings.delete") && b.stage == "draft" },
    )
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        // slim bar: the booking ID in full and the menu; the name scrolls with the page
        Row(Modifier.fillMaxWidth().padding(start = 6.dp, end = 6.dp, top = 8.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = Vayu.colors.ink) }
            Text(b.code, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            if (actions.isNotEmpty()) Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Outlined.MoreVert, contentDescription = "More actions", tint = Vayu.colors.ink) }
                DropdownMenu(menu, { menu = false }) {
                    actions.forEach { (label, key) ->
                        DropdownMenuItem(text = { Text(label + if (online) "" else " (needs signal)", color = if (key in setOf("cancel", "delete")) Vayu.colors.bad else Vayu.colors.ink) },
                            enabled = online, onClick = { menu = false; if (key == "edit") onEdit() else action = key })
                    }
                }
            }
        }
        HorizontalDivider(color = Vayu.colors.line)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            Text(b.customer.ifBlank { b.code }, fontSize = 24.sp, lineHeight = 30.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink,
                maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 14.dp, bottom = 8.dp))
            val why = if (b.stage == "cancelled") rememberLoad(env, "master-lists/cancel_reason/items").value?.data?.rows().orEmpty()
                .firstOrNull { it.s("key") == b.t.cancelReason }?.s("label") ?: b.t.cancelReason.replace('_', ' ') else ""
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                val (st, tone) = opsStatus(b)
                Chip(listOf(st, why).filter { it.isNotBlank() }.joinToString(" · "), tone)
                env.labels.type(b.type).takeIf { it.isNotBlank() }?.let { Chip(it) }
                slot(b, t).takeIf { it.isNotBlank() }?.let { Chip(it) }
                b.flags.filter { it.reviewedAt.isBlank() }.forEach { Chip(it.words, Tone.WARN) }
                if (b.unverifiedTime) Chip("Time not verified", Tone.WARN)
            }
            val digits = b.phone.filter { it in '0'..'9' }
            val place = listOf(b.a("address"), env.labels.city(b.a("city"))).filter { it.isNotBlank() }.joinToString(", ")
            Row(Modifier.padding(top = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Tile(Icons.Outlined.Call, "Call", digits.isNotEmpty()) { uri.openUri("tel:" + (if (b.phone.trimStart().startsWith("+")) "+" else "") + digits) }
                Tile(Icons.AutoMirrored.Outlined.Chat, "WhatsApp", digits.isNotEmpty()) { uri.openUri("https://wa.me/$digits") }
                Tile(Icons.Outlined.Directions, "Directions", place.isNotEmpty()) { uri.openUri("https://www.google.com/maps/search/?api=1&query=" + URLEncoder.encode(place, "UTF-8")) }
            }
            OfflineNote(load.value)
            if (b.conflict.isNotEmpty()) {
                val subs = insps.filter { it.status == "submitted" }
                Attention("Two experts inspected this car", subs.joinToString(". ") { "${env.labels.person(it.expert)} submitted ${whenStamp(it.submittedAt, env.today()).replaceFirstChar { c -> c.lowercase() }}" } +
                    ". Choose which one counts.", "Compare and choose", online && env.can("bookings.edit")) { compare = true }
            }
            // the expert's files won't come (a lost phone): Ops upload the required ones, then finish
            if (b.stage == "submitted" && env.can("media.manage")) {
                val miss = (rememberLoad(env, "bookings/$id/missing-files").value?.data as? JsonObject)?.get("missing")
                val rows = (miss as? kotlinx.serialization.json.JsonArray).orEmpty().mapNotNull { it as? JsonObject }
                if (rows.isNotEmpty()) {
                    val total = rows.sumOf { it.int("count") ?: 1 }
                    val need = rows.filter { (it["required"] as? JsonPrimitive)?.booleanOrNull == true }
                    Attention("Waiting for $total file${if (total == 1) "" else "s"} from the expert",
                        rows.joinToString(", ") { r -> r.s("label") + (if ((r.int("count") ?: 1) > 1) " (${r.int("count")})" else "") + (if (r in need) " · required" else "") } +
                            (if (need.isNotEmpty()) ". If they won't come, upload the required ones in Photos and videos, then finish without the rest."
                            else ". If they won't come, finish without them; files that arrive later are still added."),
                        if (need.isNotEmpty()) "Open photos and videos" else "Finish without the missing files",
                        online, tone = Tone.WARN) { if (need.isNotEmpty()) onPart(Part.MEDIA) else action = "finish:$total" }
                }
            }
            b.flags.sortedBy { it.reviewedAt.isNotBlank() }.forEach { f ->   // open ones first
                if (f.reviewedAt.isNotBlank()) Attention("${f.words} · Reviewed by ${env.labels.byUsername(f.reviewedBy)}, ${whenStamp(f.reviewedAt, t).replaceFirstChar { it.lowercase() }}",
                    "", null, false, tone = Tone.NEUTRAL) {}
                // one tap only: a second tap while it saves does nothing (no double review in History)
                else Attention(f.words, f.limit, (if (saving == f.flag) "Saving…" else "Mark reviewed").takeIf { env.can("bookings.review_timing") }, online, tone = Tone.WARN) {
                    if (saving == null) { saving = f.flag; scope.launch {
                        try { env.data.act("POST", "bookings/$id/timing-review", buildJsonObject { put("flag", f.flag) }); env.say("Marked reviewed."); env.refresh() }
                        catch (e: ApiError) { env.say(e.message) }
                        saving = null
                    } }
                }
            }
            b.typeRejected?.let { Attention("Your type change wasn't applied", env.labels.typeRejected(it), null, false) {} }
            if (b.stage == "completed" || b.conflict.isNotEmpty() || report.value?.data is JsonObject) {
                Section("Report")
                ReportCard(env, id, b)
            }
            Section("Inspection")
            if (insp == null || filled == null) Text(if (insp == null) "Not started yet." else "Loading…", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 12.dp))
            else {
                // one row: Check-in, Inspection and Wrap-up are tabs inside it
                val counts = PARTS.filter { filled.visiblePages(it).isNotEmpty() }.map { partCounts(data, filled, it) }
                val n = counts.sumOf { it.first }; val bad = counts.sumOf { it.second }
                NavRow("Inspection Data", "$n answer${if (n == 1) "" else "s"}" + if (bad > 0) " · $bad problem${if (bad == 1) "" else "s"}" else "",
                    if (bad > 0) Vayu.colors.warn else Vayu.colors.muted) { onAnswers("inspection") }
            }
            val media = rememberLoad(env, "bookings/$id/media").value?.data?.rows().orEmpty().filter { it.s("status") in ARRIVED }
            val photos = media.count { it.s("kind") == "photo" }; val videos = media.count { it.s("kind") == "video" }
            NavRow("Photos and videos", listOfNotNull("$photos photo${if (photos == 1) "" else "s"}", "$videos video${if (videos == 1) "" else "s"}".takeIf { videos > 0 }).joinToString(" · ")) { onPart(Part.MEDIA) }
            if (insp != null) {
                val sc = insp.scores
                val word = sc.o("overall").s("word").replaceFirstChar { it.uppercase() }
                Section("Review")
                val nRatings = sc.o("ratings").size; val nChecks = sc.o("key_checks").size
                val ov = insp.overrides; val changed = ov.o("ratings").size + (if (ov["overall"] != null) 1 else 0) +
                    sc.o("key_checks").values.count { (it as? JsonObject)?.s("edited") == "true" }
                NavRow("Overall: ${word.ifBlank { "—" }}", listOfNotNull("$nChecks Key Check${if (nChecks == 1) "" else "s"}".takeIf { nChecks > 0 },
                    "$nRatings rating${if (nRatings == 1) "" else "s"}".takeIf { nRatings > 0 },
                    "$changed changed by Ops".takeIf { changed > 0 }).joinToString(" · ")) { onPart(Part.REVIEW) }
                Section("Payment")
                val (title, sub) = paymentText(data)
                NavRow(title, sub) { onAnswers("end") }
            }
            Section("Details")
            Detail("Car", env.labels.car(b.a("car_make_model")))
            Detail("Address", place)
            Detail("Phone", phoneLabel(b.phone))
            Detail("Expert", env.labels.person(b.expert).ifBlank { "Not assigned" }) {
                if (env.can("bookings.assign") && b.stage in setOf("draft", "assigned")) IconButton(onClick = { action = "assign" }, enabled = online) {
                    Icon(Icons.Outlined.PersonAdd, if (b.expert == null) "Assign an expert" else "Reassign", tint = if (online) Vayu.colors.ink else Vayu.colors.muted)
                }
                // call the expert straight from the job
                env.labels.people.firstOrNull { it.int("id") == b.expert }?.s("phone")?.filter { it in '0'..'9' || it == '+' }?.takeIf { it.isNotEmpty() }?.let { ph ->
                    IconButton(onClick = { uri.openUri("tel:$ph") }) { Icon(Icons.Outlined.Call, "Call the expert", tint = Vayu.colors.ink) }
                }
            }
            NavRow("History", "") { onPart(Part.HISTORY) }
            Spacer(Modifier.height(24.dp))
        }
    }

    when (action) {
        "assign" -> AssignSheet(env, b, onClose = { action = null }) { expert -> run("POST", "bookings/$id/assign", buildJsonObject { put("expert", expert) }, "Assigned to ${env.labels.person(expert)}.") }
        "reschedule" -> ReasonDialog(env, "Reschedule", "reschedule_reason", withSlot = b, onClose = { action = null }) { reason, d, tm ->
            run("POST", "bookings/$id/reschedule", buildJsonObject { put("date", d); put("time", tm); put("reason", reason) },
                "Moved to ${listOf(dayLabel(d, env.today()), time12(tm)).filter { it.isNotBlank() }.joinToString(", ")}.")
        }
        "cancel" -> ReasonDialog(env, "Cancel this booking", "cancel_reason", withSlot = null, onClose = { action = null }) { reason, _, _ ->
            run("POST", "bookings/$id/cancel", buildJsonObject { put("reason", reason) }, "Booking cancelled.")
        }
        "type" -> TypeDialog(env, b, onClose = { action = null }) { run("POST", "bookings/$id/change-type", buildJsonObject { put("inspection_type", it) }, "Type changed to ${env.labels.type(it)}.") }
        "release" -> Confirm("Force release this booking?", "The expert is taken off the booking. If they still have a draft and submit it later, you'll see a conflict to resolve.",
            "Force release", { action = null }) { run("POST", "bookings/$id/force-release", JsonObject(emptyMap()), "Released. The booking can be assigned again.") }
        "signout" -> Confirm("Sign out ${env.labels.person(b.expert)}'s phone?", "Their phone signs out at once. Work not yet sent from it is refused by the server until they sign in again.",
            "Sign out the phone", { action = null }) { run("POST", "users/${b.expert}/sign-out-devices", JsonObject(emptyMap()), "Their phone is signed out.") }
        "delete" -> Confirm("Delete ${b.code}?", "The booking is removed. This can't be undone.", "Delete booking", { action = null }) {
            scope.launch {
                try { env.data.act("DELETE", "bookings/$id"); env.say("Deleted."); env.refresh(); onBack() } catch (e: ApiError) { env.say(e.message) }
            }
        }
    }
    action?.takeIf { it.startsWith("finish:") }?.removePrefix("finish:")?.let { n ->
        Confirm("Finish without the missing files?", "The booking is marked Completed and the report is made without $n file${if (n == "1") "" else "s"}. " +
            "If the expert's phone sends them later, they are added and the report is made again.", "Finish", { action = null }) {
            run("POST", "bookings/$id/finish", JsonObject(emptyMap()), "Finished. The report is being made.")
        }
    }
    if (compare) CompareSheet(env, insps.filter { it.status == "submitted" }, onClose = { compare = false }) { keep ->
        compare = false
        val who = env.labels.person(insps.firstOrNull { it.id == keep }?.expert)
        run("POST", "bookings/$id/resolve-conflict", buildJsonObject { put("inspection", keep) }, "Kept $who's inspection.")
    }
}

@Composable
private fun Attention(title: String, text: String, action: String?, enabled: Boolean, tone: Tone = Tone.BAD, onAction: () -> Unit) {
    val (bg, fg) = when (tone) {
        Tone.WARN -> Vayu.colors.warnTint to Vayu.colors.warn
        Tone.NEUTRAL -> Vayu.colors.soft to Vayu.colors.ink2          // done: calm, nothing to do
        else -> Vayu.colors.badTint to Vayu.colors.bad
    }
    Column(Modifier.padding(top = 14.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(bg).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, fontWeight = if (tone == Tone.NEUTRAL) FontWeight.Medium else FontWeight.Bold, color = fg, fontSize = if (tone == Tone.NEUTRAL) 14.sp else androidx.compose.ui.unit.TextUnit.Unspecified)
        if (text.isNotBlank()) Text(text, color = Vayu.colors.ink, fontSize = 14.sp)
        if (action != null) PillButton(action, enabled, onAction)
    }
}

@Composable
private fun Detail(label: String, value: String, actions: @Composable () -> Unit = {}) {
    Row(Modifier.fillMaxWidth().heightIn(min = 58.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(label, fontSize = 12.sp, color = Vayu.colors.muted)
            Text(value.ifBlank { "—" }, color = Vayu.colors.ink)
        }
        actions()
    }
    HorizontalDivider(color = Vayu.colors.line)
}

@Composable
private fun NavRow(title: String, sub: String, subColor: androidx.compose.ui.graphics.Color = Vayu.colors.muted, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 60.dp).clickable(role = Role.Button, onClick = onClick).padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, color = Vayu.colors.ink, fontWeight = FontWeight.SemiBold)
            if (sub.isNotBlank()) Text(sub, fontSize = 13.sp, color = subColor)
        }
        Icon(Icons.Outlined.ChevronRight, null, tint = Vayu.colors.muted)
    }
    HorizontalDivider(color = Vayu.colors.line)
}

@Composable
private fun Chip(text: String, tone: Tone? = null) {
    val (bg, fg) = when (tone) {
        Tone.OK -> Vayu.colors.okTint to Vayu.colors.ok; Tone.WARN -> Vayu.colors.warnTint to Vayu.colors.warn
        Tone.BAD -> Vayu.colors.badTint to Vayu.colors.bad; Tone.INFO -> Vayu.colors.infoTint to Vayu.colors.info
        else -> Vayu.colors.soft to Vayu.colors.ink2
    }
    Row(Modifier.heightIn(min = 28.dp).clip(RoundedCornerShape(14.dp)).background(bg).padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (tone != null) Box(Modifier.size(8.dp).clip(CircleShape).background(fg))
        Text(text, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = fg, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun RowScope.Tile(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, enabled: Boolean, onClick: () -> Unit) {
    val tint = if (enabled) Vayu.colors.ink else Vayu.colors.muted
    Column(Modifier.weight(1f).heightIn(min = 64.dp).clip(RoundedCornerShape(14.dp)).background(Vayu.colors.soft)
        .clickable(enabled = enabled, role = Role.Button, onClick = onClick),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(20.dp))
        Spacer(Modifier.height(4.dp))
        Text(label, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = tint, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
fun Confirm(title: String, text: String, yes: String, onClose: () -> Unit, onYes: () -> Unit) = AlertDialog(onDismissRequest = onClose,
    title = { Text(title) }, text = { Text(text) },
    confirmButton = { TextButton(onYes) { Text(yes, color = Vayu.colors.bad) } },
    dismissButton = { TextButton(onClose) { Text("Back") } })

/** Assign or reassign: every expert with today's load and whether they're free at the booking's time. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AssignSheet(env: OpsEnv, b: Bk, onClose: () -> Unit, onAssign: (Int) -> Unit) {
    val day = b.date.ifEmpty { env.today().toString() }
    val jobs = rememberLoad(env, "bookings?date_from=$day&date_to=$day&order=schedule").value?.data?.rows().orEmpty().map(::Bk).filter { it.stage != "cancelled" }
    var find by remember { mutableStateOf("") }
    var pick by remember { mutableStateOf(b.expert) }
    val at = runCatching { LocalTime.parse(b.time) }.getOrNull()
    VayuSheet(onClose, footer = {
        // always in view: pick an expert, assign, no scrolling
        Row(Modifier.padding(start = 20.dp, end = 20.dp, top = 10.dp, bottom = 20.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SoftButton("Cancel", onClose, Modifier.weight(1f))
            PrimaryButton(pick?.let { "Assign ${env.labels.person(it).split(" ").first()}" } ?: "Assign", { pick?.let(onAssign) },
                Modifier.weight(1f), enabled = pick != null && pick != b.expert)
        }
    }) {
        Column(Modifier.padding(horizontal = 20.dp)) {
            Text(if (b.expert == null) "Assign an expert" else "Reassign", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink)
            Text(listOf(b.code, slot(b, env.today()), env.labels.type(b.type), env.labels.city(b.a("city"))).filter { it.isNotBlank() }.joinToString(" · "),
                color = Vayu.colors.muted, fontSize = 14.sp)
            Spacer(Modifier.height(12.dp))
            SoftField(find, { find = it }, "Find an expert", icon = Icons.Outlined.Search)
            LazyColumn(Modifier.heightIn(max = 520.dp)) {
                items(env.labels.experts.filter { find.isBlank() || it.s("name").contains(find, true) || it.s("username").contains(find, true) },
                    key = { it.s("id") }) { u ->
                    val uid = u.int("id") ?: return@items
                    val theirs = jobs.filter { it.expert == uid && it.id != b.id }
                    val clash = at?.let { a -> theirs.firstOrNull { o -> runCatching { LocalTime.parse(o.time) }.getOrNull()?.let { java.time.Duration.between(it, a).abs().toMinutes() < 90 } == true } }
                    val name = u.s("name").ifBlank { u.s("username") }
                    Row(Modifier.fillMaxWidth().heightIn(min = 64.dp).clip(RoundedCornerShape(12.dp))
                        .background(if (pick == uid) Vayu.colors.soft else Vayu.colors.bg).clickable(role = Role.RadioButton) { pick = uid }.padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Avatar(initials(name), size = 36)
                        Column(Modifier.weight(1f)) {
                            Text(name, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
                            Text("${theirs.size} booking${if (theirs.size == 1) "" else "s"} that day", fontSize = 13.sp, color = Vayu.colors.muted)
                            Text(if (clash != null) "Busy: ${clash.code} at ${time12(clash.time)}" else if (at != null) "Free at ${time12(b.time)}" else "",
                                fontSize = 13.sp, color = if (clash != null) Vayu.colors.warn else Vayu.colors.ok)
                        }
                    }
                }
            }
        }
    }
}

/** Reschedule (new day, time, reason) or cancel (reason): reasons are the Admin's master lists. */
@Composable
private fun ReasonDialog(env: OpsEnv, title: String, list: String, withSlot: Bk?, onClose: () -> Unit, onDone: (String, String, String) -> Unit) {
    val reasons = rememberLoad(env, "master-lists/$list/items").value?.data?.rows().orEmpty().filter { it.s("archived") != "true" }
    var reason by remember { mutableStateOf<String?>(null) }
    var day by remember { mutableStateOf(withSlot?.date.orEmpty()) }
    var time by remember { mutableStateOf(withSlot?.time.orEmpty()) }
    var picking by remember { mutableStateOf<String?>(null) }
    if (picking == "day") DatePick(runCatching { LocalDate.parse(day) }.getOrNull(), notBefore = env.today(),
        onPick = { day = it.toString(); picking = null }, onDismiss = { picking = null })
    if (picking == "time") TimePick(runCatching { LocalTime.parse(time) }.getOrDefault(LocalTime.of(10, 0)),
        onPick = { time = "%02d:%02d".format(it.hour, it.minute); picking = null }, onDismiss = { picking = null })
    AlertDialog(onDismissRequest = onClose, containerColor = Vayu.colors.bg, title = { Text(title) }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (withSlot != null) {
                SoftButton("Day: " + dayLabel(day, env.today()).ifEmpty { "choose" }, { picking = "day" }, Modifier.fillMaxWidth())
                SoftButton("Time: " + time12(time).ifEmpty { "choose" }, { picking = "time" }, Modifier.fillMaxWidth())
            }
            Text("Reason", fontWeight = FontWeight.SemiBold)
            SingleChoice("Reason", reasons.map { Option(it.s("key"), it.s("label"), false, null) }, reason, false, { reason = it as String? }, forceList = true)
        }
    }, confirmButton = {
        TextButton({ reason?.let { onDone(it, day, time) } }, enabled = reason != null && (withSlot == null || (day.isNotEmpty() && time.isNotEmpty()))) { Text(title) }
    }, dismissButton = { TextButton(onClose) { Text("Back") } })
}

@Composable
private fun TypeDialog(env: OpsEnv, b: Bk, onClose: () -> Unit, onDone: (String) -> Unit) {
    var type by remember { mutableStateOf<String?>(b.type) }
    AlertDialog(onDismissRequest = onClose, title = { Text("Change inspection type") }, text = {
        SingleChoice("Inspection type", env.labels.types.filter { it.third }.map { Option(it.first, it.second, false, null) }, type, false, { type = it as String? })
    }, confirmButton = { TextButton({ type?.let(onDone) }, enabled = type != null && type != b.type) { Text("Change type") } },
        dismissButton = { TextButton(onClose) { Text("Back") } })
}

/** Two experts submitted: see both side by side (who, when, how many answers) and keep one. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CompareSheet(env: OpsEnv, subs: List<Inspection>, onClose: () -> Unit, onKeep: (String) -> Unit) {
    var keep by remember { mutableStateOf<String?>(null) }
    VayuSheet(onClose) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Which inspection counts?", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink)
            Text("The other one is kept but set aside.", color = Vayu.colors.muted, fontSize = 14.sp)
            subs.forEach { i ->
                val n = i.answers.values.sumOf { (it as? JsonObject)?.size ?: 0 }
                val word = i.scores.o("overall").s("word")
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (keep == i.id) Vayu.colors.primary else Vayu.colors.soft)
                    .clickable(role = Role.RadioButton) { keep = i.id }.padding(14.dp)) {
                    val fg = if (keep == i.id) Vayu.colors.onPrimary else Vayu.colors.ink
                    Text(env.labels.person(i.expert), fontWeight = FontWeight.Bold, color = fg)
                    Text("Submitted ${whenStamp(i.submittedAt, env.today()).replaceFirstChar { c -> c.lowercase() }} · $n answers" + if (word.isNotBlank()) " · $word" else "", color = fg, fontSize = 14.sp)
                }
            }
            PrimaryButton("Keep this one", { keep?.let(onKeep) }, enabled = keep != null)
        }
    }
}
