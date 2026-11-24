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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.sync.Job
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

fun statusOf(j: Job): Pair<String, Tone> = when {
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
    return "${(h + 11) % 12 + 1}:${m.toString().padStart(2, '0')} ${if (h >= 12) "pm" else "am"}"
}

/** The expert's home: My jobs, and a job's details on top of it. */
@Composable
fun ExpertHome(me: Me, state: JobsState, today: LocalDate, onProfile: () -> Unit, onRefresh: () -> Unit,
               onStart: (Job) -> Unit) {
    var openId by rememberSaveable { mutableStateOf<String?>(null) }
    val open = state.jobs.firstOrNull { it.id == openId }
    if (open != null) {
        BackHandler { openId = null }
        JobDetailScreen(open, ready = open.id in state.ready, today = today, onBack = { openId = null },
            onStart = { onStart(open) })
    } else {
        MyJobsScreen(me, state, today, onProfile, onRefresh, onOpen = { openId = it.id })
    }
}

@Composable
fun MyJobsScreen(me: Me, state: JobsState, today: LocalDate, onProfile: () -> Unit, onRefresh: () -> Unit,
                 onOpen: (Job) -> Unit) {
    var tab by rememberSaveable { mutableStateOf(JobTab.TODAY) }
    var query by rememberSaveable { mutableStateOf("") }
    val needle = query.trim().lowercase()
    val shown = state.jobs.filter { tabOf(it, today) == tab }
        .filter { needle.isEmpty() || it.bookingId.lowercase().contains(needle) || it.customer.lowercase().contains(needle) }
        .let { if (tab == JobTab.DONE) it.reversed() else it }
    val todayCount = state.jobs.count { tabOf(it, today) == JobTab.TODAY }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        VayuTopBar("My jobs", me.initials, bellCount = 0, onBell = {}, onProfile = onProfile)
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
                SoftField(query, { query = it }, "Booking ID or customer", icon = Icons.Outlined.Search)
                Spacer(Modifier.height(12.dp))
                Segmented(listOf(if (todayCount > 0) "Today · $todayCount" else "Today", "Upcoming", "Done"),
                    tab.ordinal, { tab = JobTab.entries[it] })
                Spacer(Modifier.height(8.dp))
            }
            items(shown, key = { it.id }) { JobRow(it, today, onOpen) }
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
        ExpertBottomBar(ExpertTab.JOBS, uploads = 0, onTab = {}, onRefresh = onRefresh)
    }
}

@Composable
private fun JobRow(j: Job, today: LocalDate, onOpen: (Job) -> Unit) {
    val overdue = j.open && j.date.isNotEmpty() && j.date < today.toString()
    val tab = tabOf(j, today)
    val lead = when {
        overdue || tab != JobTab.TODAY -> runCatching { LocalDate.parse(j.date).format(SHORT_DAY) }.getOrDefault("")
        else -> j.time
    }
    val (label, tone) = statusOf(j)
    Column(Modifier.fillMaxWidth().clickable(role = Role.Button) { onOpen(j) }) {
        Row(Modifier.fillMaxWidth().heightIn(min = 64.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(lead, modifier = Modifier.width(52.dp), fontWeight = FontWeight.Bold, fontSize = 15.sp,
                color = when { overdue -> Vayu.colors.warn; j.open -> Vayu.colors.ink; else -> Vayu.colors.muted })
            Column(Modifier.weight(1f)) {
                Text(j.customer, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, maxLines = 1,
                    overflow = TextOverflow.Ellipsis)
                Text(j.bookingId, style = MaterialTheme.typography.bodyMedium, color = Vayu.colors.muted)
            }
            StatusDot(label, tone)
        }
        HorizontalDivider(color = Vayu.colors.line)
    }
}

@Composable
fun JobDetailScreen(j: Job, ready: Boolean, today: LocalDate, onBack: () -> Unit, onStart: () -> Unit) {
    val uri = LocalUriHandler.current
    val place = listOf(j.address, j.city).filter { it.isNotBlank() }.joinToString(", ")
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        IconButton(onClick = onBack, modifier = Modifier.padding(start = 6.dp, top = 10.dp)) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back to My jobs", tint = Vayu.colors.ink)
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            Text(j.customer, fontSize = 26.sp, lineHeight = 32.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink,
                modifier = Modifier.padding(top = 4.dp))
            Text(listOf(j.bookingId, listOf(dayLabel(j.date, today), time12(j.time)).filter { it.isNotEmpty() }
                .joinToString(", ")).filter { it.isNotEmpty() }.joinToString(" · "), color = Vayu.colors.muted)
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
            Spacer(Modifier.height(14.dp))
            Info("Car", listOf(j.car, j.type).filter { it.isNotBlank() }.joinToString(" · "))
            Info("Address", place)
            Info("Phone", phoneLabel(j.phone))
            if (ready) Row(Modifier.padding(top = 18.dp), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Outlined.CheckCircle, contentDescription = null, tint = Vayu.colors.ok, modifier = Modifier.size(18.dp))
                Text("Ready to work without signal", color = Vayu.colors.ok, style = MaterialTheme.typography.bodyMedium)
            }
        }
        if (j.open && j.assignedToMe) Box(Modifier.padding(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 22.dp)) {
            PrimaryButton(if (j.stage == "assigned") "Start inspection" else "Continue inspection", onStart)
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
