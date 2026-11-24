package `in`.carcid.vayu.ui.ops

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.ops.OpsData
import `in`.carcid.vayu.ui.components.OpsBottomBar
import `in`.carcid.vayu.ui.components.OpsTab
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.launch
import java.time.LocalDate

/** A screen pushed on top of the Ops tabs. */
sealed interface Route {
    data object Needs : Route
    data class Booking(val id: String) : Route
    data class Detail(val id: String, val part: Part, val group: String = "inspection") : Route
    data class Form(val id: String?) : Route
}

/** Ops' app: Today · Bookings · Dashboard, the bell (Needs you), bookings and their parts. */
@Composable
fun OpsHome(me: Me, data: OpsData, today: () -> LocalDate, onProfile: () -> Unit,
            /** Updates (submitted, started, new bookings…) from the server; problems come from loadNeeds. */
            bell: `in`.carcid.vayu.ui.BellState = `in`.carcid.vayu.ui.BellState(),
            onRead: (List<Long>?) -> Unit = {}, onBell: () -> Unit = {},
            /** A booking a tapped notice asks to open; [onOpened] says it was taken. */
            opening: String? = null, onOpened: () -> Unit = {}) {
    val scope = rememberCoroutineScope()
    val snack = remember { SnackbarHostState() }
    var tab by rememberSaveable { mutableStateOf(OpsTab.TODAY) }
    // a Dashboard tile opens Bookings with these filters (dates, stage, late / quick, expert)
    var preset by remember { mutableStateOf<Map<String, String>?>(null) }
    var tick by remember { mutableStateOf(0) }
    val stack = remember { mutableStateListOf<Route>() }
    var assigning by remember { mutableStateOf<Bk?>(null) }
    var labels by remember { mutableStateOf(Labels()) }
    var namesFresh by remember { mutableStateOf(false) }
    val env = OpsEnv(me, data, labels, today, tick, refresh = { tick++ }, say = { scope.launch { snack.showSnackbar(it) } })
    // null until the first load is back (so the bell never says "All clear" too early)
    var needs by remember { mutableStateOf<List<Need>?>(null) }
    var refreshing by remember { mutableStateOf(false) }
    var asked by remember { mutableStateOf(false) }
    // one load per Refresh: names first, then the lists (a second key here restarted it half-way)
    LaunchedEffect(tick) {
        refreshing = true
        if (labels.people.isEmpty()) Labels.saved(data).takeIf { it.people.isNotEmpty() }?.let { labels = it }
        // names (types, people, cities, cars) rarely change: once per session, and again on Refresh
        if (asked || !namesFresh) Labels.load(data).takeIf { it.people.isNotEmpty() || it.cities.isNotEmpty() || it.types.isNotEmpty() }
            ?.let { labels = it; namesFresh = true }
        loadNeeds(env.copy(labels = labels))?.let { needs = it }
        // Refresh says what happened (a fresh answer, or the saved copy without signal)
        if (asked) {
            asked = false
            val online = try { data.api.get("problems/reports"); true } catch (e: `in`.carcid.vayu.core.api.ApiError) { false }
            env.say(if (online) "Updated." else "No signal. Showing what was saved; changes need signal.")
        }
        refreshing = false
    }
    LaunchedEffect(opening) { opening?.let { stack.clear(); stack.add(Route.Booking(it)); onOpened() } }
    // a new notification (a push, or the bell read on coming back) means something changed: reload
    var newest by remember { mutableStateOf<Long?>(null) }
    LaunchedEffect(bell.notes.firstOrNull()?.id) {
        val id = bell.notes.firstOrNull()?.id
        if (newest != null && id != null && id != newest) tick++
        newest = id
    }
    // fresh again whenever the app comes back to the front (and on Refresh, and after every change)
    androidx.lifecycle.compose.LifecycleResumeEffect(Unit) { tick++; onPauseOrDispose {} }
    val push = { r: Route -> stack.add(r) }
    val pop = { if (stack.isNotEmpty()) stack.removeAt(stack.lastIndex) }
    val bar = @Composable { OpsBottomBar(tab, { tab = it; stack.clear() }, { asked = true; tick++ }, refreshing) }   // every tap counts (it restarts a load already running)
    if (stack.isNotEmpty()) BackHandler { pop() }

    Box(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        when (val r = stack.lastOrNull()) {
            null -> when (tab) {
                OpsTab.TODAY -> TodayScreen(env, needs?.size ?: 0, { push(Route.Needs) }, onProfile, { push(Route.Booking(it)) }, { assigning = it }, bar)
                OpsTab.BOOKINGS -> BookingsScreen(env, needs?.size ?: 0, { push(Route.Needs) }, onProfile, { push(Route.Booking(it)) }, { assigning = it }, preset = preset, onPresetUsed = { preset = null },
                    onNew = { push(Route.Form(null)) }, bar)
                OpsTab.DASHBOARD -> DashboardScreen(env, needs?.size ?: 0, { push(Route.Needs) }, onProfile, { preset = it; tab = OpsTab.BOOKINGS }, bar)
            }
            Route.Needs -> {
                LaunchedEffect(Unit) { onBell() }
                NeedsYouScreen(env, needs, onBack = { pop() }, onOpen = { push(Route.Booking(it)) },
                    updates = bell.copy(notes = bell.notes.filter { it.kind != "problem" }), onRead = onRead)
            }
            is Route.Booking -> BookingScreen(env, r.id, onBack = { pop() }, onPart = { push(Route.Detail(r.id, it)) },
                onAnswers = { push(Route.Detail(r.id, Part.ANSWERS, it)) }, onEdit = { push(Route.Form(r.id)) })
            is Route.Detail -> when (r.part) {
                Part.ANSWERS -> AnswersScreen(env, r.id, r.group) { pop() }
                Part.MEDIA -> MediaScreen(env, r.id) { pop() }
                Part.REVIEW -> ReviewScreen(env, r.id) { pop() }
                Part.HISTORY -> HistoryScreen(env, r.id) { pop() }
            }
            is Route.Form -> BookingFormScreen(env, r.id, onBack = { pop() }) { saved, assign ->
                pop()
                if (r.id == null) push(Route.Booking(saved))
                if (assign) scope.launch {
                    runCatching { data.load("bookings/$saved") }.getOrNull()?.let { assigning = Bk(it.data as kotlinx.serialization.json.JsonObject) }
                }
            }
        }
        SnackbarHost(snack, Modifier.align(Alignment.BottomCenter).padding(bottom = 88.dp))
    }
    assigning?.let { b ->
        AssignSheet(env, b, onClose = { assigning = null }) { expert ->
            scope.launch {
                try {
                    data.act("POST", "bookings/${b.id}/assign", kotlinx.serialization.json.buildJsonObject { put("expert", kotlinx.serialization.json.JsonPrimitive(expert)) })
                    assigning = null; env.say("Assigned to ${labels.person(expert)}."); tick++
                } catch (e: `in`.carcid.vayu.core.api.ApiError) { env.say(e.message) }
            }
        }
    }
}
