package `in`.carcid.vayu.ui.ops

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.ops.OpsData
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

/**
 * Ops' home state, outside the screens (F-018): the reload counter every Ops screen keys its loads
 * on, the names (types, people, cities, cars), and the Needs you list. Each [reload] cancels the
 * load still running and starts again (names first, then the problem lists).
 */
class OpsModel(private val data: OpsData, me: Me, private val today: () -> LocalDate) : ViewModel() {
    /** The signed-in person as last read (permissions can change while the app runs). */
    @Volatile var me: Me = me
    private val _tick = MutableStateFlow(0)
    /** Bumped on every reload; screens reload what they show when it changes. */
    val tick: StateFlow<Int> = _tick
    private val _labels = MutableStateFlow(Labels())
    val labels: StateFlow<Labels> = _labels
    private val _needs = MutableStateFlow<List<Need>?>(null)
    /** null until the first load is back (so the bell never says "All clear" too early). */
    val needs: StateFlow<List<Need>?> = _needs
    private val _refreshing = MutableStateFlow(false)
    val refreshing: StateFlow<Boolean> = _refreshing
    private val _messages = Channel<String>(Channel.BUFFERED)
    /** Short messages for the snackbar ("Updated."). */
    val messages = _messages.receiveAsFlow()

    private var namesFresh = false
    private var job: Job? = null

    init { reload() }

    /** Load again; [asked]: the person pressed Refresh (names are fetched again, and the result is said). */
    fun reload(asked: Boolean = false) {
        _tick.value++
        job?.cancel()
        job = viewModelScope.launch {
            _refreshing.value = true
            try {
                if (_labels.value.people.isEmpty()) Labels.saved(data).takeIf { it.people.isNotEmpty() }?.let { _labels.value = it }
                // names rarely change: once per session, and again on Refresh
                if (asked || !namesFresh) Labels.load(data).takeIf { it.people.isNotEmpty() || it.cities.isNotEmpty() || it.types.isNotEmpty() }
                    ?.let { _labels.value = it; namesFresh = true }
                loadNeeds(env())?.let { _needs.value = it }
                if (asked) {
                    val online = try { data.api.get("problems/reports"); true } catch (e: ApiError) { false }
                    say(if (online) "Updated." else "No signal. Showing what was saved; changes need signal.")
                }
            } finally { _refreshing.value = false }
        }
    }

    fun say(message: String) { _messages.trySend(message) }

    /** Every screen's loads (F-018). */
    val loads = OpsLoads(data, viewModelScope)

    private val reloadNow = { reload() }
    private val sayNow = { m: String -> say(m) }
    /** What the Ops screens are given; the same lambdas every time, so an unchanged env compares equal. */
    fun env(me: Me = this.me, labels: Labels = _labels.value, tick: Int = _tick.value) = OpsEnv(me, data, labels, today, tick, reloadNow, sayNow, loads)
}
