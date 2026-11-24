package `in`.carcid.vayu.ui.ops

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
import `in`.carcid.vayu.core.ops.s
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
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.net.URLEncoder
import java.time.LocalDate
import java.time.LocalTime

/** Where a booking's rows lead. */
enum class Part { ANSWERS, MEDIA, RATINGS, REPORT, HISTORY }

/** The inspection that counts on a booking: the latest submitted one, else the latest draft. */
fun currentInspection(list: List<JsonObject>): JsonObject? =
    list.filter { it.s("status") == "submitted" }.maxByOrNull { it.s("submitted_at") }
        ?: list.filter { it.s("status") == "draft" }.maxByOrNull { it.s("created_at") }

@Composable
fun BookingScreen(env: OpsEnv, id: String, onBack: () -> Unit, onPart: (Part) -> Unit, onEdit: () -> Unit) {
    val uri = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    val t = env.today()
    val load = rememberLoad(env, "bookings/$id")
    val insps = rememberLoad(env, "bookings/$id/inspections").value?.data?.rows().orEmpty()
    val report = rememberLoad(env, "bookings/$id/report")
    val b = load.value?.data?.let { Bk(it as JsonObject) }
    var menu by remember { mutableStateOf(false) }
    var action by remember { mutableStateOf<String?>(null) }
    var compare by remember { mutableStateOf(false) }
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
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
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
        SubHeader(b.customer.ifBlank { b.code }, onBack = onBack) {
            // nothing to do (a cancelled or finished job without an expert): no empty menu
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
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            Text(listOf(b.code, env.labels.car(b.a("car_make_model")), env.labels.type(b.type)).filter { it.isNotBlank() }.joinToString(" · "), color = Vayu.colors.muted)
            OfflineNote(load.value)
            if (b.conflict.isNotEmpty()) {
                val subs = insps.filter { it.s("status") == "submitted" }
                Attention("Two experts inspected this car", subs.joinToString(". ") { "${env.labels.person(it.int("expert"))} submitted ${whenStamp(it.s("submitted_at"), env.today()).replaceFirstChar { c -> c.lowercase() }}" } +
                    ". Choose which one counts.", "Compare and choose", online && env.can("bookings.edit")) { compare = true }
            }
            b.typeRejected?.let { Attention("Your type change wasn't applied", env.labels.typeRejected(it), null, false) {} }
            Section("Details")
            Detail("When", slot(b, t))
            Detail("Customer", listOf(b.customer, phoneLabel(b.phone)).filter { it.isNotBlank() }.joinToString(" · ")) {
                val digits = b.phone.filter { it in '0'..'9' }
                if (digits.isNotEmpty()) {
                    IconButton(onClick = { uri.openUri("tel:" + (if (b.phone.trimStart().startsWith("+")) "+" else "") + digits) }) { Icon(Icons.Outlined.Call, "Call", tint = Vayu.colors.ink) }
                    IconButton(onClick = { uri.openUri("https://wa.me/$digits") }) { Icon(Icons.AutoMirrored.Outlined.Chat, "WhatsApp", tint = Vayu.colors.ink) }
                }
            }
            val place = listOf(b.a("address"), env.labels.city(b.a("city"))).filter { it.isNotBlank() }.joinToString(", ")
            Detail("Address", place) {
                if (place.isNotEmpty()) IconButton(onClick = { uri.openUri("https://www.google.com/maps/search/?api=1&query=" + URLEncoder.encode(place, "UTF-8")) }) {
                    Icon(Icons.Outlined.Directions, "Directions", tint = Vayu.colors.ink)
                }
            }
            Detail("Expert", env.labels.person(b.expert).ifBlank { "Not assigned" }) {
                if (env.can("bookings.assign") && b.stage in setOf("draft", "assigned")) IconButton(onClick = { action = "assign" }, enabled = online) {
                    Icon(Icons.Outlined.PersonAdd, if (b.expert == null) "Assign an expert" else "Reassign", tint = if (online) Vayu.colors.ink else Vayu.colors.muted)
                }
            }
            val why = if (b.stage == "cancelled") rememberLoad(env, "master-lists/cancel_reason/items").value?.data?.rows().orEmpty()
                .firstOrNull { it.s("key") == b.o.s("cancel_reason") }?.s("label") ?: b.o.s("cancel_reason").replace('_', ' ') else ""
            Detail("Status", listOf(opsStatus(b).first, why).filter { it.isNotBlank() }.joinToString(" · "))
            Section("Inspection")
            val answers = insp?.o("answers")?.values?.sumOf { (it as? JsonObject)?.count { e -> e.value.toString() !in setOf("null", "\"\"", "[]") } ?: 0 } ?: 0
            val media = rememberLoad(env, "bookings/$id/media").value?.data?.rows()?.size ?: 0
            val overall = insp?.o("scores")?.o("overall")?.s("word").orEmpty()
            val rep = report.value?.data as? JsonObject
            PartRow("Answers", if (insp == null) "None yet" else "$answers") { onPart(Part.ANSWERS) }
            PartRow("Photos and videos", "$media") { onPart(Part.MEDIA) }
            PartRow("Ratings and payment", overall.replaceFirstChar { it.uppercase() }.ifBlank { "—" }) { onPart(Part.RATINGS) }
            PartRow("Report", when {
                b.conflict.isNotEmpty() -> "Waits for your choice"
                b.stage == "cancelled" -> "None (cancelled)"
                rep == null -> if (b.stage == "completed") "Being made" else "After completion"
                rep.s("status") == "ready" && rep.s("stale") == "true" -> "Out of date"
                rep.s("status") == "ready" -> "Ready"
                else -> rep.s("status").replaceFirstChar { it.uppercase() }
            }) { onPart(Part.REPORT) }
            PartRow("History", "") { onPart(Part.HISTORY) }
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
        "release" -> Confirm("Force release this job?", "The expert is taken off the job. If they still have a draft and submit it later, you'll see a conflict to resolve.",
            "Force release", { action = null }) { run("POST", "bookings/$id/force-release", JsonObject(emptyMap()), "Released. The job can be assigned again.") }
        "signout" -> Confirm("Sign out ${env.labels.person(b.expert)}'s phone?", "Their phone signs out at once. Work not yet sent from it is refused by the server until they sign in again.",
            "Sign out the phone", { action = null }) { run("POST", "users/${b.expert}/sign-out-devices", JsonObject(emptyMap()), "Their phone is signed out.") }
        "delete" -> Confirm("Delete ${b.code}?", "The booking is removed. This can't be undone.", "Delete booking", { action = null }) {
            scope.launch {
                try { env.data.act("DELETE", "bookings/$id"); env.say("Deleted."); env.refresh(); onBack() } catch (e: ApiError) { env.say(e.message) }
            }
        }
    }
    if (compare) CompareSheet(env, insps.filter { it.s("status") == "submitted" }, onClose = { compare = false }) { keep ->
        compare = false
        val who = env.labels.person(insps.firstOrNull { it.s("id") == keep }?.int("expert"))
        run("POST", "bookings/$id/resolve-conflict", buildJsonObject { put("inspection", keep) }, "Kept $who's inspection.")
    }
}

@Composable
private fun Attention(title: String, text: String, action: String?, enabled: Boolean, onAction: () -> Unit) {
    Column(Modifier.padding(top = 14.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Vayu.colors.badTint).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, fontWeight = FontWeight.Bold, color = Vayu.colors.bad)
        Text(text, color = Vayu.colors.ink, fontSize = 14.sp)
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
private fun PartRow(label: String, value: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button, onClick = onClick), verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = Vayu.colors.ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        Text(value, color = Vayu.colors.muted)
        Icon(Icons.Outlined.ChevronRight, null, tint = Vayu.colors.muted)
    }
    HorizontalDivider(color = Vayu.colors.line)
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
    VayuSheet(onClose) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Text(if (b.expert == null) "Assign an expert" else "Reassign", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink)
            Text(listOf(b.code, slot(b, env.today()), env.labels.type(b.type), env.labels.city(b.a("city"))).filter { it.isNotBlank() }.joinToString(" · "),
                color = Vayu.colors.muted, fontSize = 14.sp)
            Spacer(Modifier.height(12.dp))
            SoftField(find, { find = it }, "Find an expert", icon = Icons.Outlined.Search)
            LazyColumn(Modifier.heightIn(max = 380.dp)) {
                items(env.labels.experts.filter { find.isBlank() || it.s("name").contains(find, true) || it.s("username").contains(find, true) },
                    key = { it.s("id") }) { u ->
                    val uid = u.int("id")!!
                    val theirs = jobs.filter { it.expert == uid && it.id != b.id }
                    val clash = at?.let { a -> theirs.firstOrNull { o -> runCatching { LocalTime.parse(o.time) }.getOrNull()?.let { java.time.Duration.between(it, a).abs().toMinutes() < 90 } == true } }
                    val name = u.s("name").ifBlank { u.s("username") }
                    Row(Modifier.fillMaxWidth().heightIn(min = 64.dp).clip(RoundedCornerShape(12.dp))
                        .background(if (pick == uid) Vayu.colors.soft else Vayu.colors.bg).clickable(role = Role.RadioButton) { pick = uid }.padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Avatar(name.split(" ").take(2).joinToString("") { it.take(1).uppercase() }, size = 36)
                        Column(Modifier.weight(1f)) {
                            Text(name, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
                            Text("${theirs.size} job${if (theirs.size == 1) "" else "s"} that day", fontSize = 13.sp, color = Vayu.colors.muted)
                            Text(if (clash != null) "Busy: ${clash.code} at ${time12(clash.time)}" else if (at != null) "Free at ${time12(b.time)}" else "",
                                fontSize = 13.sp, color = if (clash != null) Vayu.colors.warn else Vayu.colors.ok)
                        }
                    }
                }
            }
            Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                SoftButton("Cancel", onClose, Modifier.weight(1f))
                PrimaryButton(pick?.let { "Assign ${env.labels.person(it).split(" ").first()}" } ?: "Assign", { pick?.let(onAssign) },
                    Modifier.weight(1f), enabled = pick != null && pick != b.expert)
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
private fun CompareSheet(env: OpsEnv, subs: List<JsonObject>, onClose: () -> Unit, onKeep: (String) -> Unit) {
    var keep by remember { mutableStateOf<String?>(null) }
    VayuSheet(onClose) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Which inspection counts?", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink)
            Text("The other one is kept but set aside.", color = Vayu.colors.muted, fontSize = 14.sp)
            subs.forEach { i ->
                val n = i.o("answers").values.sumOf { (it as? JsonObject)?.size ?: 0 }
                val word = i.o("scores").o("overall").s("word")
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (keep == i.s("id")) Vayu.colors.primary else Vayu.colors.soft)
                    .clickable(role = Role.RadioButton) { keep = i.s("id") }.padding(14.dp)) {
                    val fg = if (keep == i.s("id")) Vayu.colors.onPrimary else Vayu.colors.ink
                    Text(env.labels.person(i.int("expert")), fontWeight = FontWeight.Bold, color = fg)
                    Text("Submitted ${whenStamp(i.s("submitted_at"), env.today()).replaceFirstChar { c -> c.lowercase() }} · $n answers" + if (word.isNotBlank()) " · $word" else "", color = fg, fontSize = 14.sp)
                }
            }
            PrimaryButton("Keep this one", { keep?.let(onKeep) }, enabled = keep != null)
        }
    }
}
