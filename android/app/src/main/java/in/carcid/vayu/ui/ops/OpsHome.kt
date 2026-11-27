package `in`.carcid.vayu.ui.ops

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.ui.layout.layout
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.toMutableStateList
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

/** A screen pushed on top of the Ops tabs; saved with the screen (Serializable), so Android closing the app in the background keeps Ops' place. */
sealed interface Route : java.io.Serializable {
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
    // Bookings' filters live here, so they stay across tabs; a Dashboard tile sets them (dates, stage, late / quick, expert)
    var bookingFilters by rememberSaveable { mutableStateOf(mapOf<String, String>()) }
    // loading, names and Needs you live in OpsModel (F-018); one per signed-in person
    val model: OpsModel = androidx.lifecycle.viewmodel.compose.viewModel(key = "ops-${me.id}") { OpsModel(data, me, today) }
    val tick by model.tick.collectAsState()
    val labels by model.labels.collectAsState()
    val needs by model.needs.collectAsState()
    val refreshing by model.refreshing.collectAsState()
    LaunchedEffect(model) { model.messages.collect { snack.showSnackbar(it) } }
    val stack = rememberSaveable(saver = androidx.compose.runtime.saveable.listSaver(save = { it.toList() }, restore = { it.toMutableStateList() })) {
        mutableStateListOf<Route>()
    }
    var assigning by remember { mutableStateOf<Bk?>(null) }
    model.me = me
    val env = remember(me, labels, tick) { model.env(me, labels, tick) }
    LaunchedEffect(opening) { opening?.let { stack.clear(); stack.add(Route.Booking(it)); onOpened() } }
    // a new notification (a push, or the bell read on coming back) means something changed: reload
    var newest by remember { mutableStateOf<Long?>(null) }
    LaunchedEffect(bell.notes.firstOrNull()?.id) {
        val id = bell.notes.firstOrNull()?.id
        if (newest != null && id != null && id != newest) model.reload()
        newest = id
    }
    // fresh again whenever the app comes back to the front (and on Refresh, and after every change)
    androidx.lifecycle.compose.LifecycleResumeEffect(Unit) { model.reload(); onPauseOrDispose {} }
    val push = { r: Route -> stack.add(r) }
    val pop = { if (stack.isNotEmpty()) stack.removeAt(stack.lastIndex) }
    val bar = @Composable { OpsBottomBar(tab, { tab = it; stack.clear() }, { model.reload(asked = true) }, refreshing) }   // every tap counts (it restarts a load already running)
    if (stack.isNotEmpty()) BackHandler { pop() }
    else BackHandler(tab != OpsTab.TODAY) { tab = OpsTab.TODAY }        // Back from Bookings or Dashboard: Today first, then out

    Box(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        // the tab stays built under an opened screen, hidden (not drawn, not touchable, not read
        // out): Back shows it at once and where it was scrolled, instead of building it again (~90 ms)
        Box(Modifier.fillMaxSize().then(if (stack.isEmpty()) Modifier else Modifier.hiddenBelow())) {
            when (tab) {
                OpsTab.TODAY -> TodayScreen(env, needs?.size ?: 0, { push(Route.Needs) }, onProfile, { push(Route.Booking(it)) }, { assigning = it }, bar)
                OpsTab.BOOKINGS -> BookingsScreen(env, needs?.size ?: 0, { push(Route.Needs) }, onProfile, { push(Route.Booking(it)) }, { assigning = it }, bookingFilters, { bookingFilters = it },
                    onNew = { push(Route.Form(null)) }, bar)
                OpsTab.DASHBOARD -> DashboardScreen(env, needs?.size ?: 0, { push(Route.Needs) }, onProfile, { bookingFilters = BookingFilters.fromTile(it); tab = OpsTab.BOOKINGS }, bar)
            }
        }
        when (val r = stack.lastOrNull()) {
            null -> {}
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
                    `in`.carcid.vayu.core.attempt { data.load("bookings/$saved") }.getOrNull()?.let { (it.data as? kotlinx.serialization.json.JsonObject)?.let { o -> assigning = Bk(o) } }
                }
            }
        }
        SnackbarHost(snack, Modifier.align(Alignment.BottomCenter).padding(bottom = 88.dp))
    }
    assigning?.let { b ->
        AssignSheet(env, b, onClose = { assigning = null }) { expert ->
            env.actions.send("POST", "bookings/${b.id}/assign", kotlinx.serialization.json.buildJsonObject { put("expert", kotlinx.serialization.json.JsonPrimitive(expert)) },
                "Assigned to ${labels.person(expert)}.") { assigning = null }
        }
    }
}

/** Measured but not placed: nothing drawn, no touches, nothing for TalkBack; its state is kept. */
private fun Modifier.hiddenBelow() = clearAndSetSemantics {}.layout { m, c ->
    val p = m.measure(c)
    layout(p.width, p.height) {}
}
