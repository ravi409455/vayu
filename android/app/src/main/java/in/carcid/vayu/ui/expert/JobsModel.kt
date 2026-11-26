package `in`.carcid.vayu.ui.expert

import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.sync.JobStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/** The expert's jobs: the saved copy on the phone and syncing it with the server. */
class JobsModel(
    private val api: Api,
    /** The signed-in person's jobs file (one per user id). */
    private val storeFor: (Int) -> JobStore,
    private val scope: CoroutineScope,
    private val clock: () -> Long,
    /** The server signed this phone out. */
    private val onRevoked: () -> Unit,
    /** Erase a person's saved jobs for good. */
    private val drop: (Int) -> Unit,
    /** After a good sync: tidy what the phone no longer needs. */
    private val afterSync: (Int) -> Unit = {},
    /** Form versions a person's drafts are pinned to (kept on the phone through every sync). */
    private val pinned: (Int) -> Set<Int> = { emptySet() },
    /** Time since the phone booted (ms), which no clock change moves; null where there is none (tests). */
    private val elapsed: () -> Long? = { null },
) {
    private val _state = MutableStateFlow(JobsState())
    val state: StateFlow<JobsState> = _state
    private var store: JobStore? = null
    private var userId: Int? = null
    private var syncing: kotlinx.coroutines.Job? = null

    /** Show the saved jobs at once, then (with signal) fetch fresh ones. */
    fun open(userId: Int, offline: Boolean) {
        this.userId = userId
        store = storeFor(userId)
        show(offline = offline)
        if (!offline) sync()
    }

    /** Download jobs and forms (Refresh, opening the app). Without signal the saved copy stays. */
    fun sync() {
        val s = store ?: return
        if (_state.value.syncing) return                   // a second tap, or reopening mid-sync
        _state.value = _state.value.copy(syncing = true)
        syncing = scope.launch {
            try {
                val keep = userId?.let(pinned).orEmpty()
                val payload = api.syncJobs(s.haveVersions(), s.since(), keep)
                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { s.apply(payload, clock(), keep, elapsed()) }
                userId?.let(afterSync)
                show(offline = false)
            } catch (e: ApiError) {
                when {
                    e.code == "DEVICE_REVOKED" -> onRevoked()
                    unreachable(e) -> show(offline = true)
                    else -> show(offline = false, error = e.message)
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                // a full phone can't save the new list (N-3): never a crash; the last saved copy stays
                show(offline = false, error = "The phone's storage is full, so the new leads couldn't be saved. Free up space and refresh.")
            }
        }
    }

    /** Erase the saved jobs: the open person's, or [userId]'s when nobody is open yet. */
    // 14c: unsent drafts must survive this (the server refuses a second phone while they exist)
    fun forget(userId: Int? = null) {
        syncing?.cancel(); syncing = null                  // a download in flight must not write it back
        (this.userId ?: userId)?.let(drop)
        store = null; this.userId = null
        _state.value = JobsState()
    }

    /** Now by the server's clock (the phone's may be wrong). */
    fun now(): Instant = Instant.ofEpochMilli(clock() + (store?.clockOffset() ?: 0L))

    /**
     * The phone's time can be trusted today: it was checked against the server today, and since
     * then the phone has not restarted nor had its clock changed (the clock moved the same as the
     * time since boot, within 2 minutes).
     */
    fun verified(): Boolean {
        val s = store ?: return false
        val at = s.syncedAt() ?: return false
        val now = clock()
        val sinceBoot = s.syncedElapsed()?.let { e -> elapsed()?.let { it - e } }
        if (sinceBoot != null && (sinceBoot < 0 || kotlin.math.abs((now - at) - sinceBoot) > 2 * 60_000)) return false
        fun day(ms: Long) = Instant.ofEpochMilli(ms + s.clockOffset()).atZone(`in`.carcid.vayu.core.sync.IST).toLocalDate()
        return day(at) == day(now)
    }

    /** "Ops moved DEMO-7 · 2 Dec 10:30 → 4 Dec 4:30 pm": what others changed since the last sync. */
    fun notices(): List<Pair<String, String>> {
        val s = store ?: return emptyList()
        val shown = setOf("inspection_date", "inspection_time", "address", "customer_phone", "customer_name", "inspection_type", "car_make_model", "city")
        return s.jobs().flatMap { j ->
            s.changes(j.id).mapNotNull { row ->
                val ch = (row["changes"] as? kotlinx.serialization.json.JsonObject).orEmpty()
                fun pair(k: String) = (ch[k] as? kotlinx.serialization.json.JsonArray)?.map { (it as? kotlinx.serialization.json.JsonPrimitive)?.content.orEmpty() }
                val who = "Ops"
                when {
                    pair("inspection_date") != null || pair("inspection_time") != null -> {
                        val (d0, d1) = pair("inspection_date") ?: listOf(j.date, j.date)
                        val (t0, t1) = pair("inspection_time") ?: listOf(j.time, j.time)
                        j.id to "$who moved ${j.bookingId} · ${dayLabel(d0, today())} ${time12(t0.take(5))} → ${dayLabel(d1, today())} ${time12(t1.take(5))}"
                    }
                    ch.keys.any { it in shown } -> {
                        val k = ch.keys.first { it in shown }
                        val (a, b) = pair(k) ?: return@mapNotNull null
                        j.id to "$who changed ${j.bookingId} · ${k.replace('_', ' ')}: ${a.ifEmpty { "—" }} → ${b.ifEmpty { "—" }}"
                    }
                    else -> null
                }
            }
        }.distinct()
    }

    /** Today by the server's clock (the phone's may be wrong). */
    fun today(): LocalDate = Instant.ofEpochMilli(clock() + (store?.clockOffset() ?: 0L))
        .atZone(`in`.carcid.vayu.core.sync.IST).toLocalDate()

    private fun show(offline: Boolean, error: String? = null) {
        val s = store ?: return
        val jobs = s.jobs()
        val at = s.syncedAt()?.let { Instant.ofEpochMilli(it).atZone(ZoneId.systemDefault()).toLocalTime() }
            ?.let { "%d:%02d".format(it.hour, it.minute) }
        _state.value = JobsState(jobs, jobs.filter(s::readyOffline).map { it.id }.toSet(), false, offline, at, error)
    }

    companion object {
        /** No signal, or the server is down: either way, work from the saved copy. */
        fun unreachable(e: ApiError) = e.code == ApiError.NETWORK || e.status >= 500
    }
}
