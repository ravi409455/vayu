package `in`.carcid.vayu.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.Graph
import `in`.carcid.vayu.ui.expert.JobsModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed interface Screen {
    data object Loading : Screen
    data class SignIn(val busy: Boolean = false, val error: String? = null) : Screen
    data object AdminRefused : Screen
    data class ChangePassword(val busy: Boolean = false, val error: String? = null) : Screen
    data class Home(val me: Me) : Screen
    data class Profile(val me: Me, val error: String? = null) : Screen
}

/** Sign-in, the forced password change, routing by role, and the profile. */
class AppViewModel(val graph: Graph, private val deviceName: String,
                   private val clock: () -> Long = System::currentTimeMillis,
                   /** This build's version code (newer builds are offered as updates). */
                   val appVersion: Int = 0,
                   /** Time since the phone booted (ms), to notice a clock changed after a sync. */
                   private val elapsed: () -> Long? = { null }) : ViewModel() {
    private val api = graph.api
    private val tokens = graph.tokens
    private val _screen = MutableStateFlow<Screen>(Screen.Loading)
    val screen: StateFlow<Screen> = _screen
    val jobs = JobsModel(api, graph::jobs, viewModelScope, clock, onRevoked = ::revoked, drop = graph::forgetJobs,
        afterSync = { graph.prune(it); heartbeat(it); graph.onJobs(it) }, pinned = graph::pinned, elapsed = elapsed)
    /** A newer build on offer (null: this is the newest), and whether its screen is up. */
    val update = MutableStateFlow<`in`.carcid.vayu.core.update.AppUpdate?>(null)
    val showUpdate = MutableStateFlow(false)

    /** The update's download, here rather than in its screen (F-018): it carries on if the screen closes. */
    data class UpdateDownload(val got: Long = 0, val busy: Boolean = false, val ready: Boolean = false, val error: String? = null)
    val updateDownload = MutableStateFlow(UpdateDownload())

    /** Download [u] into [file] (checked against its SHA-256); one at a time. */
    fun downloadUpdate(u: `in`.carcid.vayu.core.update.AppUpdate, file: java.io.File) {
        if (updateDownload.value.busy) return
        updateDownload.value = UpdateDownload(busy = true)
        viewModelScope.launch {
            updateDownload.value = try {
                file.parentFile?.listFiles()?.forEach { it.delete() }        // older downloads
                `in`.carcid.vayu.core.update.download(api.http, u, file) { got -> updateDownload.value = updateDownload.value.copy(got = got) }
                UpdateDownload(got = updateDownload.value.got, ready = true)
            } catch (e: ApiError) { UpdateDownload(error = e.message) }
        }
    }
    /** A booking to open, from a tapped notice; the home screen takes it and sets it back to null. */
    val opening = MutableStateFlow<String?>(null)
    /** The bell (notifications from the server), read on sign-in, on coming back and on each push. */
    val bell = BellModel(api, viewModelScope) { graph.signedInId()?.let(graph::localNotes) }
    private var lastPassword = ""
    /** Below this version the app may finish a started job but not start new ones (enforced in Phase 14). */
    var minAppVersion = 0
        private set

    init {
        viewModelScope.launch { resume() }
        viewModelScope.launch { graph.pushes.collect { onPush() } }
        viewModelScope.launch { api.expired.collect { if (it) expired() } }
    }

    /** The sign-in ended while the app ran: sign in again; drafts, jobs and forms stay on the phone. */
    private fun expired() {
        if (screen.value !is Screen.Home && screen.value !is Screen.Profile) return
        bell.clear()
        _screen.value = Screen.SignIn(error = "Your sign-in has ended. Sign in again; your unsent work stays on this phone.")
    }

    private suspend fun resume() {
        if (tokens.access() == null) { _screen.value = Screen.SignIn(); return }
        // offline: open on the saved profile only for an app role with no pending password change
        // read before calling the server: a revoked phone's sign-in (and this id) is cleared by the call
        val savedId = tokens.me()?.get("id")?.toIntOrNull()
        val cached = tokens.me()?.takeIf { it["role"] in setOf("expert", "ops") && it["must_change"] == "false" }
            ?.let { Me(it["id"]!!.toIntOrNull() ?: 0, it["username"]!!, it["name"]!!, it["role"]!!, false, it["theme"]!!,
                it["perms"].orEmpty().split(",").filter { p -> p.isNotBlank() }.toSet()) }
        // open at once on the saved profile; the server's answer (or a sign-out) follows when it comes
        if (cached != null) {
            _screen.value = Screen.Home(cached)
            if (cached.role == "expert") jobs.open(cached.id, offline = true)
        }
        try {
            enter(api.me())
        } catch (e: ApiError) {
            when {
                e.code == "DEVICE_REVOKED" -> {
                    tokens.clear(); jobs.forget(savedId); savedId?.let { graph.forgetCopies(it); graph.forgetDrafts(it, all = false) }
                    graph.clearNotices(); bell.clear(); _screen.value = Screen.SignIn()
                }
                // no signal or the server is down: still signed in, already open on the saved copy
                JobsModel.unreachable(e) && cached != null -> {}
                else -> _screen.value = Screen.SignIn()
            }
        }
    }

    fun signIn(username: String, password: String) {
        if (username.isBlank() || password.isBlank()) {
            _screen.value = Screen.SignIn(error = "Enter your username and password."); return
        }
        _screen.value = Screen.SignIn(busy = true)
        viewModelScope.launch {
            try {
                lastPassword = password
                enter(api.login(username.trim(), password, deviceName))
            } catch (e: ApiError) {
                _screen.value = if (e.code == "ADMIN_USE_WEB") Screen.AdminRefused else Screen.SignIn(error = e.message)
            }
        }
    }

    fun backToSignIn() { _screen.value = Screen.SignIn() }

    fun changePassword(new: String, again: String) {
        if (new != again) { _screen.value = Screen.ChangePassword(error = "The two passwords don't match."); return }
        _screen.value = Screen.ChangePassword(busy = true)
        viewModelScope.launch {
            try {
                api.changePassword(lastPassword, new)
                lastPassword = ""
                enter(api.me())
            } catch (e: ApiError) {
                _screen.value = Screen.ChangePassword(error = e.message)
            }
        }
    }

    private suspend fun enter(server: Me) {
        val local = tokens.me()?.takeIf { it["theme_pending"] == "true" && it["id"] == server.id.toString() }?.get("theme")
        val me = if (local != null) server.copy(theme = local) else server
        tokens.saveMe(mapOf("id" to me.id.toString(), "username" to me.username, "name" to me.name,
            "role" to me.role, "theme" to me.theme, "must_change" to me.mustChangePassword.toString(),
            "perms" to me.permissions.joinToString(",")))
        if (me.mustChangePassword) { _screen.value = Screen.ChangePassword(); return }
        lastPassword = ""                             // only kept for a required password change
        _screen.value = Screen.Home(me)
        tokens.pendingLogout()?.let { old -> viewModelScope.launch { if (api.endOld(old)) tokens.setPendingLogout(null) } }
        if (me.role == "expert") jobs.open(me.id, offline = false)
        heartbeat(me.id)
        bell.refresh()
        graph.sendPushToken()                         // retried by WorkManager until it reaches the server
        checkUpdate()
        if (local != null) pushTheme()
        graph.kick()                                  // anything left from before goes out now
    }

    /** Once per sign-in / app start: a newer build is offered (its screen shows once; Profile keeps a way back). */
    private fun checkUpdate() {
        if (update.value != null) return
        viewModelScope.launch {
            try {
                update.value = `in`.carcid.vayu.core.update.parseUpdate(api.appLatest(), appVersion)
                if (update.value != null) showUpdate.value = true
            } catch (_: ApiError) {}
        }
    }

    /** Tell the server what this phone still holds (it refuses another phone while work is here). */
    private fun heartbeat(userId: Int) {
        viewModelScope.launch {
            pushTheme()                                  // a look chosen without signal
            val (drafts, files) = graph.drafts(userId).unsentCounts()
            try {
                minAppVersion = api.heartbeat(drafts = drafts, files = files)
            } catch (e: ApiError) {
                if (e.code == "DEVICE_REVOKED") revoked()
            }
        }
    }

    private fun signedIn(): Int? = when (val s = screen.value) { is Screen.Home -> s.me.id; is Screen.Profile -> s.me.id; else -> null }

    /** Signed out from the server (another phone, or an Admin): nothing of theirs stays on this phone. */
    private fun revoked() {
        signedIn()?.let { graph.forgetCopies(it); graph.forgetDrafts(it, all = false) }
        graph.clearNotices()                         // even when nobody could be told apart
        tokens.clear(); jobs.forget(); bell.clear(); _screen.value = Screen.SignIn()
    }

    /** The app came back to the front: experts get fresh jobs (and a new "today" after midnight). */
    fun onForeground() {
        val me = (screen.value as? Screen.Home)?.me ?: return
        if (me.role == "expert") jobs.sync()
        bell.refresh()
    }

    /** A push arrived: what it is about is fetched now (jobs for experts; Ops screens reload themselves). */
    fun onPush() = onForeground()

    /** Ops: one kind of notification on or off. Shown at once; put back if the server refuses. */
    fun setNotify(key: String, on: Boolean) {
        val p = screen.value as? Screen.Profile ?: return
        val was = p.me
        _screen.value = p.copy(me = was.copy(muted = if (on) was.muted - key else was.muted + key), error = null)
        viewModelScope.launch {
            try {
                val me = api.setNotify(key, on)
                (screen.value as? Screen.Profile)?.let { _screen.value = it.copy(me = it.me.copy(muted = me.muted)) }
            } catch (e: ApiError) {
                (screen.value as? Screen.Profile)?.let { _screen.value = it.copy(me = it.me.copy(muted = was.muted),
                    error = if (e.code == ApiError.NETWORK) "No signal. Try again when you're online." else e.message) }
            }
        }
    }

    fun openProfile() { (screen.value as? Screen.Home)?.let { _screen.value = Screen.Profile(it.me) } }
    fun closeProfile() { (screen.value as? Screen.Profile)?.let { _screen.value = Screen.Home(it.me) } }

    /** The look changes at once and is kept on the phone; the server learns it when it can. */
    fun setTheme(theme: String) {
        val p = screen.value as? Screen.Profile ?: return
        _screen.value = p.copy(me = p.me.copy(theme = theme), error = null)
        tokens.saveMe(mapOf("theme" to theme, "theme_pending" to "true"))
        viewModelScope.launch { pushTheme() }
    }

    /** Send a look chosen without signal (no message if it still can't: it tries again later). */
    private suspend fun pushTheme() {
        val saved = tokens.me() ?: return
        if (saved["theme_pending"] != "true") return
        try {
            api.setTheme(saved["theme"] ?: return)
            tokens.saveMe(mapOf("theme_pending" to "false"))
        } catch (e: ApiError) {
            if (e.code != ApiError.NETWORK && e.status < 500) tokens.saveMe(mapOf("theme_pending" to "false"))
        }
    }

    fun signOut() {
        val p = screen.value as? Screen.Profile
        if (p != null) {
            // the same drafts Uploads lists, by name
            // a draft file that can't be read may hold work: sign-out deletes drafts, so it stops here
            if (graph.drafts(p.me.id).unreadable().isNotEmpty()) {
                _screen.value = p.copy(error = "A draft on this phone can't be read, so signing out could lose work. " +
                    "Keep the phone as it is and tell your Ops team.")
                return
            }
            val waiting = graph.drafts(p.me.id).all().filter { it.unsent }.map { it.code }.sorted()
            if (waiting.isNotEmpty()) {
                _screen.value = p.copy(error = "Not sent yet: ${waiting.joinToString(", ")}. Open Uploads to send, finish or discard " +
                    "${if (waiting.size == 1) "it" else "them"}, then sign out.")
                return
            }
        }
        viewModelScope.launch {
            // no signal: the server still thinks this phone is signed in; end it at the next sign-in
            val refresh = tokens.refresh()
            if (`in`.carcid.vayu.core.attempt { api.logout() }.isFailure && refresh != null) tokens.setPendingLogout(refresh)
            // nothing is unsent (checked above), so nothing of theirs needs to stay
            signedIn()?.let { graph.forgetCopies(it); graph.forgetDrafts(it, all = true) }
            graph.clearNotices()
            tokens.clear()
            jobs.forget()
            bell.clear()
            _screen.value = Screen.SignIn()
        }
    }
}
