package `in`.carcid.vayu.ui.ops

import `in`.carcid.vayu.core.ops.ReportProblem
import `in`.carcid.vayu.core.ops.StuckUpload
import `in`.carcid.vayu.core.api.initials

import androidx.compose.ui.text.style.TextOverflow
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.async
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
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import `in`.carcid.vayu.ui.noteRows
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
import `in`.carcid.vayu.core.ops.a
import `in`.carcid.vayu.core.ops.count
import kotlinx.serialization.json.JsonObject
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.s
import `in`.carcid.vayu.ui.components.Avatar
import `in`.carcid.vayu.ui.components.Segmented
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.StatusDot
import `in`.carcid.vayu.ui.components.Tone
import `in`.carcid.vayu.ui.components.VayuTopBar
import `in`.carcid.vayu.ui.components.toneColor
import `in`.carcid.vayu.ui.expert.time12
import `in`.carcid.vayu.ui.expert.whenStamp
import `in`.carcid.vayu.ui.theme.Vayu
import java.net.URLEncoder
import java.time.format.DateTimeFormatter
import java.util.Locale


/** Ops' home (variant B): how the day is going, who needs an expert, each expert's jobs. */
@Composable
fun TodayScreen(env: OpsEnv, needs: Int, onBell: () -> Unit, onProfile: () -> Unit, onOpen: (String) -> Unit, onAssign: (Bk) -> Unit,
                bottomBar: @Composable () -> Unit) {
    val t = env.today()
    val day = rememberLoad(env, "bookings?date_from=$t&date_to=$t&order=schedule")
    val all = day.value?.data?.rows().orEmpty().map(::Bk).filter { it.stage != "cancelled" }
    var open by rememberSaveable { mutableStateOf(setOf<Int>()) }
    var pick by rememberSaveable { mutableStateOf<String?>(null) }      // the status chip: null = All
    val shown = if (pick == null) all else all.filter { it.stage == pick }
    val online = day.value?.offline == false
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        VayuTopBar("Today", env.me.initials, bellCount = needs, onBell = onBell, onProfile = onProfile)
        LazyColumn(Modifier.weight(1f).padding(horizontal = 20.dp)) {
            item {
                Text(t.format(DateTimeFormatter.ofPattern("EEEE, d MMMM", Locale.ENGLISH)), color = Vayu.colors.muted)
                OfflineNote(day.value)
                day.error?.takeIf { day.value == null }?.let { Text(it, color = Vayu.colors.bad, modifier = Modifier.padding(top = 12.dp)) }
                if (all.isNotEmpty()) {
                    DayCard(all)
                    StatusChips(listOf<Pair<String?, Int>>(null to all.size) + STAGE_WORDS.keys.filter { it != "cancelled" }
                        .map { k -> k to all.count { it.stage == k } }.filter { it.second > 0 || it.first == pick }, pick) { pick = it }
                }
            }
            val unassigned = shown.filter { it.stage == "draft" }
            if (unassigned.isNotEmpty()) {
                item { Section("Unassigned · ${unassigned.size}") }
                items(unassigned, key = { it.id }) { b ->
                    BookingRow(b, listOf(env.labels.type(b.type), env.labels.city(b.a("city"))).filter { it.isNotBlank() }.joinToString(" · "), t,
                        onOpen = { onOpen(b.id) }) { PillButton("Assign", online && env.can("bookings.assign")) { onAssign(b) } }
                }
            }
            val experts = shown.mapNotNull { it.expert }.distinct()
            if (experts.isNotEmpty()) item { Section("Experts") }
            experts.forEach { id ->
                val jobs = all.filter { it.expert == id }
                val listed = shown.filter { it.expert == id }
                item(key = "e$id") {
                    val name = env.labels.person(id)
                    val onSite = jobs.firstOrNull { it.stage == "in_progress" }
                    val next = jobs.firstOrNull { it.stage == "assigned" }
                    val status = when {
                        onSite != null -> "In progress · ${onSite.code}"
                        next != null -> "Next at ${time12(next.time)}"
                        else -> "All completed"
                    }
                    val expanded = id in open
                    Column {
                        Row(Modifier.fillMaxWidth().heightIn(min = 64.dp).clickable(role = Role.Button) { open = if (expanded) open - id else open + id }
                            .semantics { contentDescription = "$name, $status, ${if (expanded) "collapse" else "expand"}" },
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Avatar(initials(name), size = 36)
                            Column(Modifier.weight(1f)) {
                                Text(name, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(status, fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                            Text("${jobs.count { it.stage == "completed" || it.stage == "submitted" }} of ${jobs.size}", color = Vayu.colors.muted, fontSize = 14.sp, maxLines = 1, softWrap = false)
                            Icon(if (expanded) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, null, tint = Vayu.colors.muted)
                        }
                        // their bookings in a grey box under the name, full width (no empty gap on the left)
                        if (expanded) Column(Modifier.padding(bottom = 12.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Vayu.colors.soft).padding(horizontal = 12.dp)) {
                            listed.forEachIndexed { i, b ->
                                if (i > 0) HorizontalDivider(color = Vayu.colors.line)
                                Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button) { onOpen(b.id) }.padding(vertical = 8.dp),
                                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                    Text(time12(b.time), fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink2, fontSize = 14.sp, maxLines = 1, softWrap = false)
                                    Column(Modifier.weight(1f)) {
                                        Text(b.customer.ifBlank { b.code }, color = Vayu.colors.ink, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        Text(b.code, fontSize = 13.sp, color = Vayu.colors.ink2)
                                    }
                                    opsStatus(b).let { StatusDot(it.first, it.second) }
                                }
                            }
                        }
                        HorizontalDivider(color = Vayu.colors.line)
                    }
                }
            }
            if (day.value != null && all.isEmpty()) item {
                Text("Nothing booked for today.", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 24.dp))
            }
            else if (shown.isEmpty() && pick != null) item {
                Column(Modifier.padding(vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Nothing ${STAGE_WORDS[pick]?.lowercase()} today.", color = Vayu.colors.muted)
                    SoftButton("Show all", { pick = null }, Modifier.fillMaxWidth())
                }
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
        bottomBar()
    }
}

/** "4 of 12 completed" with one bar split by stage and its legend. */
@Composable
private fun DayCard(all: List<Bk>) {
    val done = all.count { it.stage == "completed" || it.stage == "submitted" }
    val parts = listOf(
        Triple(done, Tone.OK, "completed"),
        Triple(all.count { it.stage == "in_progress" }, Tone.INFO, "in progress"),
        Triple(all.count { it.stage == "assigned" }, Tone.NEUTRAL, "assigned"),
        Triple(all.count { it.stage == "draft" }, Tone.WARN, "unassigned"),
    )
    Column(Modifier.padding(top = 16.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Vayu.colors.soft).padding(16.dp)) {
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("$done", fontSize = 34.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
            Text("of ${all.size} completed", color = Vayu.colors.muted, modifier = Modifier.padding(bottom = 6.dp))
        }
        Row(Modifier.padding(vertical = 10.dp).fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)).background(Vayu.colors.line)) {
            parts.filter { it.first > 0 }.forEach { (n, tone, _) -> Box(Modifier.weight(n.toFloat()).height(8.dp).background(toneColor(tone))) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            parts.drop(1).filter { it.first > 0 }.forEach { (n, tone, label) -> StatusDot("$n $label", tone) }
        }
    }
}

/** Bookings: search, Status ▾ · Experts ▾ · Filter (today by default); Unassigned first. [filters] live in OpsHome, so they stay across tabs. */
@Composable
fun BookingsScreen(env: OpsEnv, needs: Int, onBell: () -> Unit, onProfile: () -> Unit, onOpen: (String) -> Unit, onAssign: (Bk) -> Unit,
                   filters: Map<String, String>, onFilters: (Map<String, String>) -> Unit, onNew: () -> Unit, bottomBar: @Composable () -> Unit) {
    val t = env.today()
    var search by rememberSaveable { mutableStateOf("") }
    var term by remember { mutableStateOf("") }
    var sheet by remember { mutableStateOf(false) }
    var pages by remember(term, filters) { mutableStateOf(1) }
    LaunchedEffect(search) { kotlinx.coroutines.delay(350); term = search.trim() }
    fun query(page: Int) = buildList {
        addAll(BookingFilters.query(filters, t))
        if (term.isNotEmpty()) add("search=" + URLEncoder.encode(term, "UTF-8"))
        if (page > 1) add("page=$page")
    }.joinToString("&")
    val loads = (1..pages).map { rememberLoad(env, "bookings?" + query(it)) }
    val first = loads.first().value
    val rows = loads.flatMap { it.value?.data?.rows().orEmpty() }.map(::Bk)
    val total = first?.data?.count() ?: 0
    val online = first?.offline == false
    // "Payment verified?: Not filled" for the Showing line (the questions load only with an answer filter on)
    val answer = filters["answer"]?.let { a ->
        answerWords(BookingFilters.answerFields(env, filters["type"]).firstOrNull { it.s("field") == a }, filters["value"]) }
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
                SoftField(search, { search = it }, "Name, phone, ID, chassis", icon = Icons.Outlined.Search)
                QuickFilters(filters, env.labels, onFilters) { sheet = true }
                // what the list shows, always (today is the default), with a way back to it
                Row(Modifier.padding(top = 4.dp).fillMaxWidth().heightIn(min = 44.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text((listOfNotNull(first?.let { "Showing $total" }) + BookingFilters.words(filters, env.labels, answer)).joinToString(" · "),
                        fontSize = 13.sp, color = Vayu.colors.ink2, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    if (filters.isNotEmpty()) Text("Clear", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.info,
                        modifier = Modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button) { onFilters(emptyMap()) }.padding(12.dp))
                }
            }
            val need = rows.filter { it.stage == "draft" }
            val rest = rows.filter { it.stage != "draft" }
            if (need.isNotEmpty()) {
                item { Section("Unassigned · ${need.size}") }
                items(need, key = { "n" + it.id }) { b ->
                    BookingRow(b, listOf(env.labels.type(b.type), env.labels.city(b.a("city"))).filter { it.isNotBlank() }.joinToString(" · "), t, onOpen = { onOpen(b.id) }) {
                        PillButton("Assign", online && env.can("bookings.assign")) { onAssign(b) }
                    }
                }
            }
            if (rest.isNotEmpty()) {
                item { Section("Scheduled · ${rest.size}") }
                items(rest, key = { "s" + it.id }) { b ->
                    BookingRow(b, listOf(env.labels.type(b.type), env.labels.person(b.expert)).filter { it.isNotBlank() }.joinToString(" · "), t, onOpen = { onOpen(b.id) })
                }
            }
            if (first == null) item { Text(if (term.isNotEmpty()) "Searching…" else "Loading…", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 24.dp)) }
            else if (rows.isEmpty()) item {
                val dated = filters["dates"] != "all"
                Column(Modifier.padding(vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(if (term.isNotEmpty()) "Nothing matches \"$term\"${if (dated) " · " + BookingFilters.dateWord(filters) else ""}." else "No bookings here.", color = Vayu.colors.muted)
                    // a search on some dates misses the others: one tap widens it
                    if (term.isNotEmpty() && dated) SoftButton("Search all dates", { onFilters(filters - "date_from" - "date_to" + ("dates" to "all")) }, Modifier.fillMaxWidth())
                }
            }
            if (rows.size < total) item {
                SoftButton("Show more (${total - rows.size} left)", { pages++ }, Modifier.fillMaxWidth().padding(vertical = 12.dp))
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
        bottomBar()
    }
    if (sheet) FilterSheet(filters, env, { sheet = false }, onFilters)
}

/** The values an answer filter offers: the field's choices, then "Not filled". */
fun answerOptions(f: JsonObject): List<Pair<String, String>> =
    f.a("options").mapNotNull { it as? JsonObject }.map { it.s("value") to it.s("label") } + (NOT_FILLED to "Not filled")

/** "Payment verified?: Not filled", as the Showing line says it. */
fun answerWords(f: JsonObject?, value: String?): String? {
    f ?: return null
    return f.s("label") + ": " + (answerOptions(f).firstOrNull { it.first == value }?.second ?: value.orEmpty())
}

const val NOT_FILLED = "__none__"

/** The bell: what needs a person (Problems), and Updates (with notifications, Phase 17). */
@Composable
fun NeedsYouScreen(env: OpsEnv, loaded: List<Need>?, onBack: () -> Unit, onOpen: (String) -> Unit,
                   updates: `in`.carcid.vayu.ui.BellState = `in`.carcid.vayu.ui.BellState(), onRead: (List<Long>?) -> Unit = {}) {
    val problems = loaded.orEmpty()
    var tab by rememberSaveable { mutableStateOf(0) }
    val unseen = updates.notes.count { !it.read }
    // looking at Updates counts as reading them (the dots stay until the next visit)
    LaunchedEffect(tab, unseen) { if (tab == 1 && unseen > 0) onRead(updates.notes.filter { !it.read }.map { it.id }) }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader("Needs you", onBack = onBack)
        Box(Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
            Segmented(listOf(if (problems.isEmpty()) "Problems" else "Problems · ${problems.size}",
                if (unseen == 0) "Updates" else "Updates · $unseen"), tab, { tab = it })
        }
        LazyColumn(Modifier.weight(1f).padding(horizontal = 20.dp)) {
            if (tab == 1) {
                if (updates.notes.isEmpty()) item {
                    Text(if (updates.loaded) "Nothing yet. Bookings started, submitted and completed, late starts and new bookings show here." else "Loading…",
                        color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 24.dp))
                }
                noteRows(updates.notes, env.today()) { n -> n.booking?.let(onOpen) }
            }
            else if (loaded == null) item { Text("Loading…", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 24.dp)) }
            else if (problems.isEmpty()) item { Text("All clear. Nothing needs you right now.", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 24.dp)) }
            else problems.groupBy { it.group }.forEach { (group, list) ->
              if (group.isNotBlank()) item(key = "h$group") {
                Section("$group · ${list.size}")
              }
              items(list, key = { it.key }) { n ->
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
}

/** One thing that needs a person (web: lib/problems.ts); [group] is its heading in the bell. */
data class Need(val key: String, val booking: String, val tone: Tone, val title: String, val meta: String, val group: String = "")

/** Every problem queue as one list, in groups, most urgent group first; null when none could be read (no signal, nothing saved): keep what shows. */
suspend fun loadNeeds(env: OpsEnv): List<Need>? {
    val t = env.today()
    val read = java.util.concurrent.atomic.AtomicInteger()
    // a failed list counts as empty; a cancelled load (a newer one started) must stay cancelled
    suspend fun rows(path: String) = try { env.data.load(path).data.rows().also { read.incrementAndGet() } } catch (e: `in`.carcid.vayu.core.api.ApiError) { emptyList() }
    // started late, finished too quickly: last 7 days, each until someone marks it reviewed (Admin / Ops only)
    fun flagged(f: String) = "bookings?timing=$f&reviewed=0&date_from=${t.minusDays(6)}&date_to=$t&order=schedule".takeIf { env.can("bookings.review_timing") }
    // all at once: on a weak signal the wait is the slowest one, not the sum
    val all = kotlinx.coroutines.coroutineScope {
        listOf("bookings?problem=conflict", "bookings?stage=draft&date_from=$t&date_to=$t&order=schedule", "problems/stuck-uploads",
            "problems/reports", "bookings?problem=type_change", flagged("late"), flagged("quick"),
            // unverified time: this week only (the mark never clears), like the web
            "bookings?problem=unverified_time&date_from=${t.minusDays(6)}&date_to=$t&order=schedule").map { async { it?.let { p -> rows(p) }.orEmpty() } }.awaitAll()
    }
    val (c, o, st, pd, ty) = all; val lt = all[5]; val qk = all[6]; val uv = all[7]
    fun timing(list: List<kotlinx.serialization.json.JsonObject>, f: String, group: String) = list.map(::Bk).mapNotNull { b ->
        b.flags.firstOrNull { it.flag == f }?.let { fl -> Need(f + b.id, b.id, Tone.WARN, "${b.code}: ${fl.words.replaceFirstChar { it.lowercase() }}",
            listOf(slot(b, t), b.customer).filter { it.isNotBlank() }.joinToString(" · "), group) } }
    if (read.get() == 0) return null
    return o.map(::Bk).map { Need("a" + it.id, it.id, Tone.WARN, "${it.code} has no expert", "Today at ${time12(it.time)} · ${it.customer}", "Unassigned today") } +
        c.map(::Bk).map { Need("c" + it.id, it.id, Tone.BAD, "Two experts inspected ${it.code}", "${it.customer} · choose which counts", "Conflicts") } +
        StuckUpload.list(st).map { Need("s" + it.id, it.booking, Tone.BAD, "Photos stuck: ${it.bookingId}",
            "${env.labels.byUsername(it.expert)} · ${it.fieldKey.replace('_', ' ').replaceFirstChar { c -> c.uppercase() }}", "Stuck uploads") } +
        // each row names its problem: failed / stuck (tried again by itself), or out of date (Ops press Regenerate, F-219)
        ReportProblem.list(pd).map { if (it.problem == "out_of_date")
                Need("p" + it.booking, it.booking, Tone.WARN, "Report out of date for ${it.bookingId}",
                    listOfNotNull(it.outOfDateSince?.takeIf { v -> v.isNotBlank() }?.let { v -> "Since ${whenStamp(v, t).replaceFirstChar { c -> c.lowercase() }}" },
                        "Regenerate it when you're done").joinToString(" · "), "Reports")
            else Need("p" + it.booking, it.booking, Tone.BAD, "Report failed for ${it.bookingId}",
                it.error.ifBlank { "It is tried again by itself" }, "Reports") } +
        ty.map(::Bk).map { Need("t" + it.id, it.id, Tone.WARN, "Your type change wasn't applied", "${it.code} · ${it.typeRejected?.let(env.labels::typeRejected) ?: "The expert started another type"}", "Type changes") } +
        timing(lt, "late", "Started late") + timing(qk, "quick", "Too quick") +
        uv.map(::Bk).filter { it.unverifiedTime }.map { Need("u" + it.id, it.id, Tone.WARN, "${it.code}: time not verified",
            listOf(slot(it, t), "the phone's clock was not checked that day, so its times may be off").filter { s -> s.isNotBlank() }.joinToString(" · "),
            "Unverified times") }
}
