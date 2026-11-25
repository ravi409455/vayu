package `in`.carcid.vayu.ui.ops

import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.ops.Loaded
import `in`.carcid.vayu.core.ops.OpsData
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/**
 * Every Ops screen's loads, owned by OpsModel instead of the composables (F-018). A screen that opens
 * asks again (as before); two screens asking for the same address at once share one request, and
 * the last answer shows at once while the fresh one loads. The saved copy shows first when there is
 * nothing yet; "offline" only once loading fails.
 */
class OpsLoads(private val data: OpsData, private val scope: CoroutineScope) {
    private class Entry(val state: MutableStateFlow<State<Loaded?, String?>>) { var tick = -1; var job: Job? = null }

    // the most recently used 200 addresses (each search and filter is one)
    private val entries = object : LinkedHashMap<String, Entry>(64, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Entry>) = size > 200
    }

    /** [path]'s answer as it comes; asking again for [tick] while that load still runs joins it. */
    @Synchronized
    fun get(path: String, tick: Int): StateFlow<State<Loaded?, String?>> {
        val e = entries.getOrPut(path) { Entry(MutableStateFlow(State(null, null))) }
        if (e.tick == tick && e.job?.isActive == true) return e.state
        e.tick = tick
        e.job?.cancel()
        // all on IO: it only writes a StateFlow (thread-safe), so nothing waits for the main thread
        e.job = scope.launch(Dispatchers.IO) {
            if (e.state.value.value == null) data.saved(path)
                ?.let { if (e.state.value.value == null) e.state.value = State(it.copy(offline = false), null) }
            e.state.value = try { State(data.load(path), null) } catch (x: ApiError) { State(e.state.value.value, x.message) }
        }
        return e.state
    }
}
