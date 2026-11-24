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
) {
    private val _state = MutableStateFlow(JobsState())
    val state: StateFlow<JobsState> = _state
    private var store: JobStore? = null
    private var syncing: kotlinx.coroutines.Job? = null

    /** Show the saved jobs at once, then (with signal) fetch fresh ones. */
    fun open(userId: Int, offline: Boolean) {
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
                s.apply(api.syncJobs(s.haveVersions(), s.since()), clock())
                show(offline = false)
            } catch (e: ApiError) {
                when {
                    e.code == "DEVICE_REVOKED" -> onRevoked()
                    unreachable(e) -> show(offline = true)
                    else -> show(offline = false, error = e.message)
                }
            }
        }
    }

    /** Erase the saved jobs: the open person's, or [userId]'s when nobody is open yet. */
    // 14c: unsent drafts must survive this (the server refuses a second phone while they exist)
    fun forget(userId: Int? = null) {
        syncing?.cancel(); syncing = null                  // a download in flight must not write it back
        (store ?: userId?.let(storeFor))?.clear()
        store = null
        _state.value = JobsState()
    }

    /** Today by the server's clock (the phone's may be wrong). */
    fun today(): LocalDate = Instant.ofEpochMilli(clock() + (store?.clockOffset() ?: 0L))
        .atZone(ZoneId.systemDefault()).toLocalDate()

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
