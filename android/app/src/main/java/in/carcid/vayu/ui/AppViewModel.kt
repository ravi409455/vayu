package `in`.carcid.vayu.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.auth.TokenStore
import `in`.carcid.vayu.core.sync.JobStore
import `in`.carcid.vayu.ui.expert.JobsState
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
class AppViewModel(private val api: Api, private val tokens: TokenStore, private val deviceName: String,
                   /** The signed-in person's jobs file (one per user id). */
                   private val storeFor: (Int) -> JobStore,
                   private val clock: () -> Long = System::currentTimeMillis) : ViewModel() {
    private val _screen = MutableStateFlow<Screen>(Screen.Loading)
    val screen: StateFlow<Screen> = _screen
    private val _jobs = MutableStateFlow(JobsState())
    val jobs: StateFlow<JobsState> = _jobs
    private var store: JobStore? = null
    private var lastPassword = ""
    /** Below this version the app may finish a started job but not start new ones (enforced in Phase 14). */
    var minAppVersion = 0
        private set

    init { viewModelScope.launch { resume() } }

    private suspend fun resume() {
        if (tokens.access() == null) { _screen.value = Screen.SignIn(); return }
        // offline: open on the saved profile only for an app role with no pending password change
        val cached = tokens.me()?.takeIf { it["role"] in setOf("expert", "ops") && it["must_change"] == "false" }
            ?.let { Me(it["id"]!!.toIntOrNull() ?: 0, it["username"]!!, it["name"]!!, it["role"]!!, false, it["theme"]!!) }
        try {
            enter(api.me())
        } catch (e: ApiError) {
            if (e.code == "DEVICE_REVOKED") cached?.let { storeFor(it.id).clear() }
            if (e.code == ApiError.NETWORK && cached != null) {
                _screen.value = Screen.Home(cached)
                openStore(cached, offline = true)
            } else _screen.value = Screen.SignIn()
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

    private suspend fun enter(me: Me) {
        tokens.saveMe(mapOf("id" to me.id.toString(), "username" to me.username, "name" to me.name,
            "role" to me.role, "theme" to me.theme, "must_change" to me.mustChangePassword.toString()))
        if (me.mustChangePassword) { _screen.value = Screen.ChangePassword(); return }
        _screen.value = Screen.Home(me)
        openStore(me, offline = false)
        try {
            minAppVersion = api.heartbeat(drafts = 0, files = 0)     // nothing is stored on the phone yet
        } catch (e: ApiError) {
            if (e.code == "DEVICE_REVOKED") revoked()
        }
    }

    private fun openStore(me: Me, offline: Boolean) {
        if (me.role != "expert") return
        store = storeFor(me.id)
        show(offline = offline)
        if (!offline) sync()
    }

    private fun show(offline: Boolean, error: String? = null, syncing: Boolean = false) {
        val s = store ?: return
        val jobs = s.jobs()
        val at = s.syncedAt()?.let {
            java.time.Instant.ofEpochMilli(it).atZone(java.time.ZoneId.systemDefault()).toLocalTime()
                .let { t -> "%d:%02d".format(t.hour, t.minute) }
        }
        _jobs.value = JobsState(jobs, jobs.filter(s::readyOffline).map { it.id }.toSet(), syncing, offline, at, error)
    }

    /** Download jobs and forms (Refresh, opening the app). Without signal the saved copy stays. */
    fun sync() {
        val s = store ?: return
        _jobs.value = _jobs.value.copy(syncing = true)
        viewModelScope.launch {
            try {
                val payload = api.syncJobs(s.haveVersions(), s.since())
                s.apply(payload, clock())
                show(offline = false)
            } catch (e: ApiError) {
                when (e.code) {
                    ApiError.NETWORK -> show(offline = true)
                    "DEVICE_REVOKED" -> revoked()
                    else -> show(offline = false, error = e.message)
                }
            }
        }
    }

    /** Signed out from the server (another phone, or an Admin): nothing of theirs stays on this phone. */
    private fun revoked() {
        tokens.clear(); forgetJobs(); _screen.value = Screen.SignIn()
    }

    // 14c: unsent drafts must survive this (the server refuses a second phone while they exist)
    private fun forgetJobs() { store?.clear(); store = null; _jobs.value = JobsState() }

    /** Today by the server's clock (the phone's may be wrong). */
    fun today(): java.time.LocalDate = java.time.Instant.ofEpochMilli(clock() + (store?.clockOffset() ?: 0L))
        .atZone(java.time.ZoneId.systemDefault()).toLocalDate()

    fun openProfile() { (screen.value as? Screen.Home)?.let { _screen.value = Screen.Profile(it.me) } }
    fun closeProfile() { (screen.value as? Screen.Profile)?.let { _screen.value = Screen.Home(it.me) } }

    fun setTheme(theme: String) {
        val p = screen.value as? Screen.Profile ?: return
        _screen.value = p.copy(me = p.me.copy(theme = theme))           // show it at once
        viewModelScope.launch {
            try {
                val me = api.setTheme(theme)
                tokens.saveMe(mapOf("theme" to me.theme))
            } catch (e: ApiError) {
                _screen.value = p.copy(error = e.message)
            }
        }
    }

    fun signOut() {
        viewModelScope.launch {
            runCatching { api.logout() }
            tokens.clear()
            forgetJobs()
            _screen.value = Screen.SignIn()
        }
    }
}
