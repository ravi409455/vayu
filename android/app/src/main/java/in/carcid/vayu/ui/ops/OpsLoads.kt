package `in`.carcid.vayu.ui.ops

import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.ops.Loaded
import `in`.carcid.vayu.core.ops.OpsData
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.async
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import `in`.carcid.vayu.core.ops.MediaLinks

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

    /** A booking's file links, asked once for all its files (memory only: links expire, and this
     *  model is the signed-in person's own). [at]: when they came (elapsed ms). */
    private class Links(val at: Long, val useFor: Long, val byId: Map<String, MediaLinks>)
    private val links = HashMap<String, Deferred<Links?>>()

    /**
     * The link to [media] from [booking]'s links (one request for the whole photo screen, not one
     * per file), or null: not there, or the server could not say (the caller asks for that file alone).
     */
    suspend fun link(booking: String, media: String, now: () -> Long = android.os.SystemClock::elapsedRealtime): MediaLinks? {
        val got = synchronized(this) {
            val have = links[booking]
            val stale = have != null && have.isCompleted && have.getCompletedOrNull().let { it == null || now() - it.at > it.useFor }
            if (have != null && !stale) have
            else scope.async(Dispatchers.IO) {
                try {
                    val o = data.api.get("bookings/$booking/media-links") as? JsonObject ?: return@async null
                    val ttl = o["expires_in"]?.jsonPrimitive?.intOrNull ?: return@async null
                    val byId = (o["links"] as? JsonObject).orEmpty().mapNotNull { (k, v) -> MediaLinks.from(v)?.let { k to it } }.toMap()
                    Links(now(), ttl * 1000L * 5 / 6, byId)          // a link works for ttl; used for 5/6 of it
                } catch (e: ApiError) { null }
            }.also { links[booking] = it }
        }
        return got.await()?.byId?.get(media)
    }

    /** A link from [booking]'s links failed (expired, or the file changed): ask again next time. */
    @Synchronized
    fun forgetLinks(booking: String) { links.remove(booking) }
}

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
private fun <T> Deferred<T>.getCompletedOrNull(): T? = runCatching { getCompleted() }.getOrNull()
