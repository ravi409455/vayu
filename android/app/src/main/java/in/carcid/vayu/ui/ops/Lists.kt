package `in`.carcid.vayu.ui.ops

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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.FilterList
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.ops.count
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.ops.s
import `in`.carcid.vayu.ui.components.Avatar
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.Segmented
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.StatusDot
import `in`.carcid.vayu.ui.components.Tone
import `in`.carcid.vayu.ui.components.VayuTopBar
import `in`.carcid.vayu.ui.components.toneColor
import `in`.carcid.vayu.ui.expert.SingleChoice
import `in`.carcid.vayu.ui.expert.time12
import `in`.carcid.vayu.ui.theme.Vayu
import `in`.carcid.vayu.core.forms.Option
import java.net.URLEncoder
import java.time.format.DateTimeFormatter
import java.util.Locale

private fun initials(name: String) = name.split(" ").filter { it.isNotBlank() }.take(2).joinToString("") { it.first().uppercase() }

/** Ops' home (variant B): how the day is going, who needs an expert, each expert's jobs. */
@Composable
fun TodayScreen(env: OpsEnv, needs: Int, onBell: () -> Unit, onProfile: () -> Unit, onOpen: (String) -> Unit, onAssign: (Bk) -> Unit,
                bottomBar: @Composable () -> Unit) {
    val t = env.today()
    val day = rememberLoad(env, "bookings?date_from=$t&date_to=$t&order=schedule")
    val all = day.value?.data?.rows().orEmpty().map(::Bk).filter { it.stage != "cancelled" }
    var open by rememberSaveable { mutableStateOf(setOf<Int>()) }
    val online = day.value?.offline == false
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        VayuTopBar("Today", env.me.initials, bellCount = needs, onBell = onBell, onProfile = onProfile)
        LazyColumn(Modifier.weight(1f).padding(horizontal = 20.dp)) {
            item {
                Text(t.format(DateTimeFormatter.ofPattern("EEEE, d MMMM", Locale.ENGLISH)), color = Vayu.colors.muted)
                OfflineNote(day.value)
                day.error?.takeIf { day.value == null }?.let { Text(it, color = Vayu.colors.bad, modifier = Modifier.padding(top = 12.dp)) }
                if (all.isNotEmpty()) DayCard(all)
            }
            val unassigned = all.filter { it.stage == "draft" }
            if (unassigned.isNotEmpty()) {
                item { Section("Unassigned · ${unassigned.size}") }
                items(unassigned, key = { it.id }) { b ->
                    BookingRow(b, listOf(env.labels.city(b.a("city")), env.labels.type(b.type)).filter { it.isNotBlank() }.joinToString(" · "), t,
                        onOpen = { onOpen(b.id) }) { PillButton("Assign", online && env.can("bookings.assign")) { onAssign(b) } }
                }
            }
            val experts = all.mapNotNull { it.expert }.distinct()
            if (experts.isNotEmpty()) item { Section("Experts") }
            experts.forEach { id ->
                val jobs = all.filter { it.expert == id }
                item(key = "e$id") {
                    val name = env.labels.person(id)
                    val onSite = jobs.firstOrNull { it.stage == "in_progress" }
                    val next = jobs.firstOrNull { it.stage == "assigned" }
                    val status = when {
                        onSite != null -> "On site · ${onSite.code}"
                        next != null -> "Next at ${time12(next.time)}"
                        else -> "All done"
                    }
                    val expanded = id in open
                    Column {
                        Row(Modifier.fillMaxWidth().heightIn(min = 64.dp).clickable(role = Role.Button) { open = if (expanded) open - id else open + id }
                            .semantics { contentDescription = "$name, $status, ${if (expanded) "collapse" else "expand"}" },
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Avatar(initials(name), size = 36)
                            Column(Modifier.weight(1f)) {
                                Text(name, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
                                Text(status, fontSize = 13.sp, color = Vayu.colors.muted)
                            }
                            Text("${jobs.count { it.stage == "completed" || it.stage == "submitted" }} of ${jobs.size}", color = Vayu.colors.muted, fontSize = 14.sp)
                            Icon(if (expanded) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, null, tint = Vayu.colors.muted)
                        }
                        if (expanded) jobs.forEach { b ->
                            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(role = Role.Button) { onOpen(b.id) }.padding(start = 48.dp),
                                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                Text(b.time, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, fontSize = 14.sp)
                                Text(b.customer, color = Vayu.colors.ink, fontSize = 14.sp, modifier = Modifier.weight(1f), maxLines = 1)
                                opsStatus(b).let { StatusDot(it.first, it.second) }
                            }
                        }
                        HorizontalDivider(color = Vayu.colors.line)
                    }
                }
            }
            if (day.value != null && all.isEmpty()) item {
                Text("Nothing booked for today.", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 24.dp))
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
        bottomBar()
    }
}

/** "4 of 12 jobs done" with one bar split by stage and its legend. */
@Composable
private fun DayCard(all: List<Bk>) {
    val done = all.count { it.stage == "completed" || it.stage == "submitted" }
    val parts = listOf(
        Triple(done, Tone.OK, "done"),
        Triple(all.count { it.stage == "in_progress" }, Tone.INFO, "on site"),
        Triple(all.count { it.stage == "assigned" }, Tone.NEUTRAL, "to start"),
        Triple(all.count { it.stage == "draft" }, Tone.WARN, "unassigned"),
    )
    Column(Modifier.padding(top = 16.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Vayu.colors.soft).padding(16.dp)) {
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("$done", fontSize = 34.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
            Text("of ${all.size} jobs done", color = Vayu.colors.muted, modifier = Modifier.padding(bottom = 6.dp))
        }
        Row(Modifier.padding(vertical = 10.dp).fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)).background(Vayu.colors.line)) {
            parts.filter { it.first > 0 }.forEach { (n, tone, _) -> Box(Modifier.weight(n.toFloat()).height(8.dp).background(toneColor(tone))) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            parts.drop(1).filter { it.first > 0 }.forEach { (n, tone, label) -> StatusDot("$n $label", tone) }
        }
    }
}

/** Bookings: search, Today / Upcoming / All, one filter sheet; "Need an expert" first. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BookingsScreen(env: OpsEnv, needs: Int, onBell: () -> Unit, onProfile: () -> Unit, onOpen: (String) -> Unit, onAssign: (Bk) -> Unit,
                   onNew: () -> Unit, bottomBar: @Composable () -> Unit) {
    val t = env.today()
    var view by rememberSaveable { mutableStateOf(0) }
    var search by rememberSaveable { mutableStateOf("") }
    var term by remember { mutableStateOf("") }
    var filters by rememberSaveable { mutableStateOf(mapOf<String, String>()) }
    var sheet by remember { mutableStateOf(false) }
    var pages by remember(view, term, filters) { mutableStateOf(1) }
    LaunchedEffect(search) { kotlinx.coroutines.delay(350); term = search.trim() }
    fun query(page: Int) = buildList {
        when (view) {
            0 -> { add("date_from=$t"); add("date_to=$t"); add("order=schedule") }
            1 -> { add("date_from=${t.plusDays(1)}"); add("order=schedule") }
        }
        if (term.isNotEmpty()) add("search=" + URLEncoder.encode(term, "UTF-8"))
        filters.forEach { (k, v) -> add("$k=" + URLEncoder.encode(v, "UTF-8")) }
        if (page > 1) add("page=$page")
    }.joinToString("&")
    val loads = (1..pages).map { rememberLoad(env, "bookings?" + query(it)) }
    val first = loads.first().value
    val rows = loads.flatMap { it.value?.data?.rows().orEmpty() }.map(::Bk)
    val total = first?.data?.count() ?: 0
    val online = first?.offline == false
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        VayuTopBar("Bookings", env.me.initials, bellCount = needs, onBell = onBell, onProfile = onProfile) {
            if (env.can("bookings.create")) IconButton(onClick = onNew, enabled = online) {
                Icon(Icons.Outlined.Add, contentDescription = "New booking", tint = if (online) Vayu.colors.ink else Vayu.colors.muted)
            }
        }
        LazyColumn(Modifier.weight(1f).padding(horizontal = 20.dp)) {
            item {
                OfflineNote(first)
                Spacer(Modifier.height(12.dp))
                SoftField(search, { search = it }, "Name, phone, booking ID, chassis", icon = Icons.Outlined.Search)
                Row(Modifier.padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Segmented(listOf("Today", "Upcoming", "All"), view, { view = it }, Modifier.weight(1f))
                    Row(Modifier.heightIn(min = 44.dp).clip(RoundedCornerShape(12.dp)).background(if (filters.isEmpty()) Vayu.colors.soft else Vayu.colors.primary)
                        .clickable(role = Role.Button) { sheet = true }.padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.FilterList, null, tint = if (filters.isEmpty()) Vayu.colors.ink else Vayu.colors.onPrimary, modifier = Modifier.size(18.dp))
                        Text(if (filters.isEmpty()) " Filter" else " Filter · ${filters.size}", fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                            color = if (filters.isEmpty()) Vayu.colors.ink else Vayu.colors.onPrimary)
                    }
                }
            }
            val need = rows.filter { it.stage == "draft" }
            val rest = rows.filter { it.stage != "draft" }
            if (need.isNotEmpty()) {
                item { Section("Need an expert · ${need.size}") }
                items(need, key = { "n" + it.id }) { b ->
                    BookingRow(b, "${b.code} · ${env.labels.city(b.a("city"))}", t, onOpen = { onOpen(b.id) }) {
                        PillButton("Assign", online && env.can("bookings.assign")) { onAssign(b) }
                    }
                }
            }
            if (rest.isNotEmpty()) {
                item { Section("Scheduled · ${rest.size}") }
                items(rest, key = { "s" + it.id }) { b ->
                    BookingRow(b, listOf(b.code, env.labels.person(b.expert)).filter { it.isNotBlank() }.joinToString(" · "), t, onOpen = { onOpen(b.id) })
                }
            }
            if (first != null && rows.isEmpty()) item {
                Text(if (term.isNotEmpty()) "Nothing matches \"$term\"." else "No bookings here.", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 24.dp))
            }
            if (rows.size < total) item {
                SoftButton("Show more (${total - rows.size} left)", { pages++ }, Modifier.fillMaxWidth().padding(vertical = 12.dp))
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
        bottomBar()
    }
    if (sheet) ModalBottomSheet(onDismissRequest = { sheet = false }, containerColor = Vayu.colors.bg) {
        var draft by remember { mutableStateOf(filters) }
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Filter", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink)
            Text("City", fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
            SingleChoice("City", env.labels.cities.map { Option(it.key, it.value, false, null) }, draft["city"], false,
                { draft = if (it == null) draft - "city" else draft + ("city" to it as String) }, forceList = true)
            Text("Expert", fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
            SingleChoice("Expert", env.labels.experts.map { Option(it.s("id"), it.s("name").ifBlank { it.s("username") }, false, null) }, draft["expert"], false,
                { draft = if (it == null) draft - "expert" else draft + ("expert" to it as String) }, forceList = true)
            Text("Inspection type", fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
            SingleChoice("Inspection type", env.labels.types.map { Option(it.first, it.second, false, null) }, draft["type"], false,
                { draft = if (it == null) draft - "type" else draft + ("type" to it as String) }, forceList = true)
            Text("Stage", fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
            SingleChoice("Stage", listOf("draft" to "Unassigned", "assigned" to "To start", "in_progress" to "On site", "submitted" to "Uploading",
                "completed" to "Done", "cancelled" to "Cancelled").map { Option(it.first, it.second, false, null) }, draft["stage"], false,
                { draft = if (it == null) draft - "stage" else draft + ("stage" to it as String) }, forceList = true)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                SoftButton("Clear", { draft = emptyMap(); filters = emptyMap(); sheet = false }, Modifier.weight(1f))
                PrimaryButton("Show bookings", { filters = draft; sheet = false }, Modifier.weight(1f))
            }
        }
    }
}

/** The bell: what needs a person (Problems), and Updates (with notifications, Phase 17). */
@Composable
fun NeedsYouScreen(env: OpsEnv, problems: List<Need>, onBack: () -> Unit, onOpen: (String) -> Unit) {
    var tab by rememberSaveable { mutableStateOf(0) }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader("Needs you", onBack = onBack)
        Box(Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
            Segmented(listOf(if (problems.isEmpty()) "Problems" else "Problems · ${problems.size}", "Updates"), tab, { tab = it })
        }
        LazyColumn(Modifier.weight(1f).padding(horizontal = 20.dp)) {
            if (tab == 1) item { Text("Updates (new bookings, jobs started, submitted) arrive here with notifications.", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 24.dp)) }
            else if (problems.isEmpty()) item { Text("All clear. Nothing needs you right now.", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 24.dp)) }
            else items(problems, key = { it.key }) { n ->
                Row(Modifier.fillMaxWidth().heightIn(min = 68.dp).clickable(role = Role.Button) { onOpen(n.booking) },
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Box(Modifier.size(10.dp).clip(CircleShape).background(toneColor(n.tone)))
                    Column(Modifier.weight(1f)) {
                        Text(n.title, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
                        Text(n.meta, fontSize = 13.sp, color = Vayu.colors.muted)
                    }
                }
                HorizontalDivider(color = Vayu.colors.line)
            }
        }
    }
}

/** One thing that needs a person (web: lib/problems.ts). */
data class Need(val key: String, val booking: String, val tone: Tone, val title: String, val meta: String)

/** Every problem queue as one list, most urgent first. */
suspend fun loadNeeds(env: OpsEnv): List<Need> {
    val t = env.today()
    // a failed list counts as empty; a cancelled load (a newer one started) must stay cancelled
    suspend fun rows(path: String) = try { env.data.load(path).data.rows() } catch (e: `in`.carcid.vayu.core.api.ApiError) { emptyList() }
    val conflicts = rows("bookings?problem=conflict").map(::Bk)
    val open = rows("bookings?stage=draft&date_from=$t&date_to=$t&order=schedule").map(::Bk)
    val stuck = rows("problems/stuck-uploads")
    val pdf = rows("problems/reports")
    val types = rows("bookings?problem=type_change").map(::Bk)
    return conflicts.map { Need("c" + it.id, it.id, Tone.BAD, "Two experts inspected ${it.code}", "${it.customer} · choose which counts") } +
        open.map { Need("a" + it.id, it.id, Tone.WARN, "${it.code} has no expert", "Today at ${time12(it.time)} · ${it.customer}") } +
        stuck.map { Need("s" + it.s("id"), it.s("booking"), Tone.BAD, "Photos stuck: ${it.s("booking_id")}", "${it.s("expert")} · ${it.s("field_key")}") } +
        pdf.map { Need("p" + it.s("booking"), it.s("booking"), if (it.s("stale") == "true") Tone.WARN else Tone.BAD,
            if (it.s("stale") == "true") "Report out of date: ${it.s("booking_id")}" else "Report failed for ${it.s("booking_id")}",
            it.s("error").ifBlank { "Answers changed after the PDF was made" }) } +
        types.map { Need("t" + it.id, it.id, Tone.WARN, "Your type change wasn't applied", "${it.code} · ${it.typeRejected ?: "the expert started another type"}") }
}
