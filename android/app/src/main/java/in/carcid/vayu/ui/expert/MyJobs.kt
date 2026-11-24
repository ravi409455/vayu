package `in`.carcid.vayu.ui.expert

import androidx.activity.compose.BackHandler
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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.outlined.Call
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Directions
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.draft.Draft
import `in`.carcid.vayu.core.sync.Job
import `in`.carcid.vayu.ui.components.Banner
import `in`.carcid.vayu.ui.components.SoftButton
import androidx.compose.runtime.remember
import `in`.carcid.vayu.ui.components.ExpertBottomBar
import `in`.carcid.vayu.ui.components.ExpertTab
import `in`.carcid.vayu.ui.components.OfflineStrip
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.Segmented
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.StatusDot
import `in`.carcid.vayu.ui.components.Tone
import `in`.carcid.vayu.ui.components.VayuTopBar
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.launch
import java.net.URLEncoder
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

/** What the expert's home shows: the synced jobs and how fresh they are. */
data class JobsState(
    val jobs: List<Job> = emptyList(),
    val ready: Set<String> = emptySet(),        // job ids whose forms are all on the phone
    val syncing: Boolean = false,
    val offline: Boolean = false,
    val syncedAt: String? = null,               // "10:42", shown in the offline strip
    val error: String? = null,
)

enum class JobTab { TODAY, UPCOMING, DONE }

fun tabOf(j: Job, today: LocalDate): JobTab = when {
    !j.open -> JobTab.DONE
    j.date.isEmpty() || j.date <= today.toString() -> JobTab.TODAY     // overdue stays on top, with today's
    else -> JobTab.UPCOMING
}

fun statusOf(j: Job, d: Draft? = null): Pair<String, Tone> = when {
    d != null && d.locked && d.files.any { !it.sent } -> "Sending ${d.files.count { it.sent }}/${d.files.size}" to Tone.WARN
    d != null && d.locked && !d.submitSent -> "Sending" to Tone.WARN
    d != null && !d.locked && !j.assignedToMe -> "Reassigned" to Tone.BAD
    d != null && !d.locked && j.stage == "cancelled" -> "Cancelled" to Tone.BAD
    d != null && !d.locked -> "In progress" to Tone.INFO
    !j.assignedToMe -> "Reassigned" to Tone.BAD
    j.stage == "in_progress" -> "In progress" to Tone.INFO
    j.stage == "submitted" -> "Uploading" to Tone.WARN
    j.stage == "completed" -> "Done" to Tone.OK
    j.stage == "cancelled" -> "Cancelled" to Tone.BAD
    else -> "To start" to Tone.NEUTRAL
}

private val SHORT_DAY = DateTimeFormatter.ofPattern("d MMM", Locale.ENGLISH)
private val LONG_DAY = DateTimeFormatter.ofPattern("EEE d MMM", Locale.ENGLISH)

/** "Today", "Tomorrow", "Yesterday" or "Tue 3 Dec". */
fun dayLabel(date: String, today: LocalDate): String {
    val d = runCatching { LocalDate.parse(date) }.getOrNull() ?: return ""
    return when (d) {
        today -> "Today"; today.plusDays(1) -> "Tomorrow"; today.minusDays(1) -> "Yesterday"
        else -> d.format(LONG_DAY)
    }
}

/** "+91 98765 00000" for Indian mobile numbers, anything else as stored. */
fun phoneLabel(p: String): String =
    Regex("""^\+91(\d{5})(\d{5})$""").find(p.filterNot { it.isWhitespace() })?.let { "+91 ${it.groupValues[1]} ${it.groupValues[2]}" } ?: p

/** "3:30 pm" from "15:30". */
fun time12(hhmm: String): String {
    val (h, m) = hhmm.split(":").mapNotNull { it.toIntOrNull() }.let { if (it.size < 2) return "" else it[0] to it[1] }
    // a no-break space: "3:30 pm" never splits across lines
    return "${(h + 11) % 12 + 1}:${m.toString().padStart(2, '0')}\u00A0${if (h >= 12) "pm" else "am"}"
}

/** A server time in words, on this phone's clock: "Today, 2:14 pm", "Mon 23 Nov, 9:15 am". */
fun whenStamp(iso: String, today: java.time.LocalDate): String = runCatching {
    val t = java.time.OffsetDateTime.parse(iso).atZoneSameInstant(java.time.ZoneId.systemDefault())
    "${dayLabel(t.toLocalDate().toString(), today)}, ${time12("%02d:%02d".format(t.hour, t.minute))}"
}.getOrDefault(iso)

/** What the expert's home needs beyond the job list: drafts, notices, and the inspection screens. */
class ExpertExtras(
    val drafts: Map<String, Draft> = emptyMap(),
    /** Ops changes since the last look: (booking id, text). */
    val notices: List<Pair<String, String>> = emptyList(),
    /** This app is older than the server accepts: finish started jobs, start no new ones. */
    val updateNeeded: Boolean = false,
    val freeBytes: Long = Long.MAX_VALUE,
    val sentBytes: Long = 0,
    val inspection: ((Job) -> InspectionEnv)? = null,
    val onDiscard: (String) -> Unit = {},
    val onClearSent: () -> Unit = {},
    /** Customer phones by booking id (Uploads search). */
    val phones: Map<String, String> = emptyMap(),
) {
    /** Phone storage, as Uploads and App settings show it. */
    val storage: StorageInfo get() = StorageInfo(freeBytes, sentBytes, drafts.values.sumOf { d -> d.files.count { !it.sent } }) {
        sentBytes.also { onClearSent() }
    }
}

private const val GB = 1024L * 1024 * 1024

/** Why a job can't be started on this phone now (null: it can). A started draft can always go on. */
fun cannotStart(j: Job, d: Draft?, ready: Boolean, extras: ExpertExtras): String? = when {
    d != null -> null
    extras.updateNeeded -> "Update the app to start new jobs."
    extras.freeBytes < GB / 2 -> "The phone is almost full. Clear sent photos on the Uploads tab first."
    !ready -> "This job's form isn't on the phone yet. Connect once and tap Refresh."
    else -> null
}

/** The expert's home: My jobs or Uploads, a job's details, and the inspection on top. */
@Composable
fun ExpertHome(me: Me, state: JobsState, today: LocalDate, onProfile: () -> Unit, onRefresh: () -> Unit,
               extras: ExpertExtras = ExpertExtras()) {
    var openId by rememberSaveable { mutableStateOf<String?>(null) }
    var inspectId by rememberSaveable { mutableStateOf<String?>(null) }
    var uploads by rememberSaveable { mutableStateOf(false) }
    var bell by rememberSaveable { mutableStateOf(false) }
    val snack = remember { androidx.compose.material3.SnackbarHostState() }
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    val say: (String) -> Unit = { m -> scope.launch { snack.currentSnackbarData?.dismiss(); snack.showSnackbar(m) } }
    // Refresh says what happened once it is done (it is often too quick to see the spin)
    var asked by remember { mutableStateOf(false) }
    val refresh = { asked = true; onRefresh() }
    androidx.compose.runtime.LaunchedEffect(state.syncing) {
        if (!state.syncing && asked) {
            asked = false
            say(when { state.offline -> "No signal. Showing the jobs saved" + (state.syncedAt?.let { " at $it" } ?: "") + "."
                state.error != null -> state.error; else -> "Jobs up to date." })
        }
    }
    val inspecting = state.jobs.firstOrNull { it.id == inspectId }
    val open = state.jobs.firstOrNull { it.id == openId }
    Box(Modifier.fillMaxSize()) {
        when {
            inspecting != null && extras.inspection != null -> InspectionScreen(remember(inspecting.id) { extras.inspection.invoke(inspecting) },
                onClose = { inspectId = null })
            bell -> {
                BackHandler { bell = false }
                NotificationsScreen(onBack = { bell = false })
            }
            open != null -> {
                BackHandler { openId = null }
                val d = extras.drafts[open.id]
                JobDetailScreen(open, ready = open.id in state.ready, today = today, onBack = { openId = null },
                    draft = d, blocked = cannotStart(open, d, open.id in state.ready, extras),
                    notices = extras.notices.filter { it.first == open.id }.map { it.second },
                    onStart = { inspectId = open.id }, onDiscard = { extras.onDiscard(open.id); say("Draft discarded.") })
            }
            uploads -> {
                BackHandler { uploads = false }
                UploadsScreen(me, extras, onProfile, onJobs = { uploads = false }, onRefresh = refresh,
                    onBell = { bell = true }, refreshing = state.syncing, say = say)
            }
            else -> MyJobsScreen(me, state, today, onProfile, refresh, extras, onOpen = { j ->
                val d = extras.drafts[j.id]
                if (d != null && d.locked) inspectId = j.id else openId = j.id
            }, onUploads = { uploads = true }, onDiscard = { extras.onDiscard(it); say("Draft discarded.") },
                onSubmitAnyway = { inspectId = it.id }, onBell = { bell = true })
        }
        androidx.compose.material3.SnackbarHost(snack, Modifier.align(Alignment.BottomCenter).padding(bottom = 96.dp))
    }
}

/** The expert's bell. Notifications (new jobs, moved times, stuck uploads) arrive with push, Phase 17. */
@Composable
fun NotificationsScreen(onBack: () -> Unit) {
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        IconButton(onClick = onBack, modifier = Modifier.padding(start = 6.dp, top = 10.dp)) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = Vayu.colors.ink)
        }
        Text("Notifications", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink, modifier = Modifier.padding(horizontal = 20.dp))
        Text("Nothing yet. New jobs, changed times and photos that are stuck will show here.",
            color = Vayu.colors.muted, modifier = Modifier.padding(horizontal = 20.dp, vertical = 16.dp))
    }
}

@Composable
fun MyJobsScreen(me: Me, state: JobsState, today: LocalDate, onProfile: () -> Unit, onRefresh: () -> Unit,
                 extras: ExpertExtras = ExpertExtras(), onOpen: (Job) -> Unit, onUploads: () -> Unit = {},
                 onDiscard: (String) -> Unit = {}, onSubmitAnyway: (Job) -> Unit = {}, onBell: () -> Unit = {}) {
    var closed by rememberSaveable { mutableStateOf(setOf<String>()) }
    var tab by rememberSaveable { mutableStateOf(JobTab.TODAY) }
    var query by rememberSaveable { mutableStateOf("") }
    val needle = query.trim().lowercase()
    val shown = state.jobs.filter { tabOf(it, today) == tab }
        .filter { needle.isEmpty() || it.bookingId.lowercase().contains(needle) || it.customer.lowercase().contains(needle) }
        .let { if (tab == JobTab.DONE) it.reversed() else it }
    val todayCount = state.jobs.count { tabOf(it, today) == JobTab.TODAY }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        VayuTopBar("My jobs", me.initials, bellCount = 0, onBell = onBell, onProfile = onProfile)
        // a thin bar while jobs download (Refresh, reopening); fixed height so nothing jumps
        Box(Modifier.fillMaxWidth().height(3.dp).padding(horizontal = 20.dp)) {
            if (state.syncing) LinearProgressIndicator(Modifier.fillMaxSize().semantics { contentDescription = "Updating jobs" },
                color = Vayu.colors.brand, trackColor = Vayu.colors.soft)
        }
        LazyColumn(Modifier.weight(1f).padding(horizontal = 20.dp)) {
            item {
                Spacer(Modifier.height(14.dp))
                if (state.offline) {
                    OfflineStrip("Offline" + (state.syncedAt?.let { " · as of $it" } ?: ""))
                    Spacer(Modifier.height(12.dp))
                } else if (state.error != null) {
                    Text(state.error, color = Vayu.colors.bad, style = MaterialTheme.typography.bodyMedium)
                    Spacer(Modifier.height(12.dp))
                }
                val banners = buildList {
                    extras.notices.forEach { (id, text) -> add("ops:$id:$text" to (text to Tone.WARN)) }
                    if (extras.freeBytes < 2 * GB) add("space" to ("%.1f GB free. Clear sent photos on the Uploads tab before it runs out.".format(extras.freeBytes.toDouble() / GB) to Tone.WARN))
                    if (extras.updateNeeded) add("update" to ("Update needed to start new jobs. Started jobs can still be finished." to Tone.BAD))
                }.filter { it.first !in closed }
                banners.forEach { (key, b) ->
                    Banner(b.first, b.second, { closed = closed + key })
                    Spacer(Modifier.height(10.dp))
                }
                SoftField(query, { query = it }, "Booking ID or customer", icon = Icons.Outlined.Search)
                Spacer(Modifier.height(12.dp))
                Segmented(listOf(if (todayCount > 0) "Today · $todayCount" else "Today", "Upcoming", "Done"),
                    tab.ordinal, { tab = JobTab.entries[it] })
                Spacer(Modifier.height(8.dp))
            }
            items(shown, key = { it.id }) { j ->
                val d = extras.drafts[j.id]
                JobRow(j, today, d, onOpen)
                // a draft for a job taken away or cancelled: the expert decides what happens to it
                if (d != null && !d.locked && (!j.assignedToMe || j.stage == "cancelled")) Row(Modifier.fillMaxWidth().padding(bottom = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    SoftButton("Discard draft", { onDiscard(j.id) }, Modifier.weight(1f), color = Vayu.colors.bad)
                    SoftButton("Submit anyway", { onSubmitAnyway(j) }, Modifier.weight(1f))
                }
            }
            if (shown.isEmpty()) item {
                Text(when {
                    state.syncing && state.jobs.isEmpty() -> "Getting your jobs…"
                    needle.isNotEmpty() -> "No job matches \"$query\"."
                    tab == JobTab.TODAY -> "Nothing for today."
                    tab == JobTab.UPCOMING -> "Nothing coming up."
                    else -> "Nothing finished in the last 7 days."
                }, color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 24.dp))
            }
        }
        ExpertBottomBar(ExpertTab.JOBS, uploads = extras.drafts.values.sumOf { d -> d.files.count { !it.sent } },
            onTab = { if (it == ExpertTab.UPLOADS) onUploads() }, onRefresh = onRefresh, refreshing = state.syncing)
    }
}

@Composable
private fun JobRow(j: Job, today: LocalDate, d: Draft?, onOpen: (Job) -> Unit) {
    val overdue = j.open && j.date.isNotEmpty() && j.date < today.toString()
    val tab = tabOf(j, today)
    val lead = when {
        overdue || tab != JobTab.TODAY -> runCatching { LocalDate.parse(j.date).format(SHORT_DAY) }.getOrDefault("")
        else -> j.time
    }
    val (label, tone) = statusOf(j, d)
    Column(Modifier.fillMaxWidth().clickable(role = Role.Button) { onOpen(j) }) {
        Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(lead, modifier = Modifier.width(52.dp), fontWeight = FontWeight.Bold, fontSize = 15.sp, maxLines = 1, softWrap = false,
                color = when { overdue -> Vayu.colors.warn; j.open -> Vayu.colors.ink; else -> Vayu.colors.muted })
            Column(Modifier.weight(1f)) {
                // name "…" and status; the booking ID in full; car · type; then a note if there is one
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(j.customer.ifBlank { j.bookingId }, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, maxLines = 1,
                        overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    StatusDot(label, tone)
                }
                Text(j.bookingId, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Vayu.colors.ink2)
                listOf(j.car, j.type).filter { it.isNotBlank() }.joinToString(" · ").takeIf { it.isNotEmpty() }?.let {
                    Text(it, fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                when {
                    d != null && !d.locked && !j.assignedToMe -> "Given to another expert"
                    d != null && !d.locked && j.stage == "cancelled" -> "Cancelled; your draft is still sent"
                    j.stage == "completed" -> when (j.report) { "ready" -> "Report ready"; "failed" -> "Report problem (Ops will fix)"; else -> "Report being made" }
                    else -> null
                }?.let { Text(it, fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1, overflow = TextOverflow.Ellipsis) }
            }
        }
        HorizontalDivider(color = Vayu.colors.line)
    }
}

@Composable
fun JobDetailScreen(j: Job, ready: Boolean, today: LocalDate, onBack: () -> Unit, onStart: () -> Unit,
                    draft: Draft? = null, blocked: String? = null, notices: List<String> = emptyList(), onDiscard: () -> Unit = {}) {
    val uri = LocalUriHandler.current
    val place = listOf(j.address, j.city).filter { it.isNotBlank() }.joinToString(", ")
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        IconButton(onClick = onBack, modifier = Modifier.padding(start = 6.dp, top = 10.dp)) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back to My jobs", tint = Vayu.colors.ink)
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            Text(j.customer, fontSize = 26.sp, lineHeight = 32.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink,
                modifier = Modifier.padding(top = 4.dp))
            Text(j.bookingId, color = Vayu.colors.ink2, fontWeight = FontWeight.Medium)
            Text(listOf(dayLabel(j.date, today), time12(j.time)).filter { it.isNotEmpty() }.joinToString(", "), color = Vayu.colors.muted)
            Row(Modifier.padding(top = 20.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                // digits only: a stored "*#06#"-style code must never reach the dialer
                val digits = j.phone.filter { it in '0'..'9' }
                Action(Icons.Outlined.Call, "Call", Modifier.weight(1f), enabled = digits.isNotEmpty()) {
                    uri.openUri("tel:" + (if (j.phone.trimStart().startsWith("+")) "+" else "") + digits)
                }
                Action(Icons.AutoMirrored.Outlined.Chat, "WhatsApp", Modifier.weight(1f), enabled = digits.isNotEmpty()) {
                    uri.openUri("https://wa.me/$digits")
                }
                Action(Icons.Outlined.Directions, "Directions", Modifier.weight(1f), enabled = place.isNotEmpty()) {
                    uri.openUri("https://www.google.com/maps/search/?api=1&query=" + URLEncoder.encode(place, "UTF-8"))
                }
            }
            notices.forEach { Spacer(Modifier.height(12.dp)); Banner(it, Tone.WARN, {}) }
            Spacer(Modifier.height(14.dp))
            Info("Car", j.car)
            Info("Inspection", j.type)
            Info("Address", place)
            Info("Phone", phoneLabel(j.phone))
            if (ready) Row(Modifier.padding(top = 18.dp), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Outlined.CheckCircle, contentDescription = null, tint = Vayu.colors.ok, modifier = Modifier.size(18.dp))
                Text("Ready to work without signal", color = Vayu.colors.ok, style = MaterialTheme.typography.bodyMedium)
            }
        }
        val mine = j.open && j.assignedToMe
        if (mine || draft != null) Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 22.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (blocked != null) Text(blocked, color = Vayu.colors.bad, style = MaterialTheme.typography.bodyMedium)
            if (draft != null && !draft.locked && !mine) SoftButton("Discard draft", onDiscard, Modifier.fillMaxWidth(), color = Vayu.colors.bad)
            PrimaryButton(when {
                draft?.locked == true -> "See what was sent"
                draft != null && !mine -> "Submit anyway"
                draft != null || j.stage != "assigned" -> "Continue inspection"
                else -> "Start inspection"
            }, onStart, enabled = blocked == null)
        }
    }
}

@Composable
private fun Action(icon: ImageVector, label: String, modifier: Modifier, enabled: Boolean, onClick: () -> Unit) {
    Column(modifier.heightIn(min = 72.dp).clip(RoundedCornerShape(14.dp)).background(Vayu.colors.soft)
        .clickable(enabled = enabled, role = Role.Button, onClick = onClick),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        val tint = if (enabled) Vayu.colors.ink else Vayu.colors.muted
        Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(22.dp))
        Spacer(Modifier.height(6.dp))
        Text(label, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = tint)
    }
}

@Composable
private fun Info(label: String, value: String) {
    if (value.isBlank()) return
    Column(Modifier.fillMaxWidth().heightIn(min = 58.dp), verticalArrangement = Arrangement.Center) {
        Text(label, fontSize = 12.sp, color = Vayu.colors.muted)
        Text(value, color = Vayu.colors.ink)
    }
    HorizontalDivider(color = Vayu.colors.line)
}
