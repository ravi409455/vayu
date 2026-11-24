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
                   private val clock: () -> Long = System::currentTimeMillis) : ViewModel() {
    private val api = graph.api
    private val tokens = graph.tokens
    private val _screen = MutableStateFlow<Screen>(Screen.Loading)
    val screen: StateFlow<Screen> = _screen
    val jobs = JobsModel(api, graph::jobs, viewModelScope, clock, onRevoked = ::revoked, drop = graph::forgetJobs,
        afterSync = { graph.prune(it); heartbeat(it) })
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
            when {
                e.code == "DEVICE_REVOKED" -> {
                    tokens.clear(); jobs.forget(cached?.id); cached?.let { graph.ops(it.id).clear() }; _screen.value = Screen.SignIn()
                }
                // no signal or the server is down: still signed in, so open on the saved copy
                JobsModel.unreachable(e) && cached != null -> {
                    _screen.value = Screen.Home(cached)
                    if (cached.role == "expert") jobs.open(cached.id, offline = true)
                }
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

    private suspend fun enter(me: Me) {
        tokens.saveMe(mapOf("id" to me.id.toString(), "username" to me.username, "name" to me.name,
            "role" to me.role, "theme" to me.theme, "must_change" to me.mustChangePassword.toString()))
        if (me.mustChangePassword) { _screen.value = Screen.ChangePassword(); return }
        _screen.value = Screen.Home(me)
        if (me.role == "expert") jobs.open(me.id, offline = false)
        heartbeat(me.id)
        graph.kick()                                  // anything left from before goes out now
    }

    /** Tell the server what this phone still holds (it refuses another phone while work is here). */
    private fun heartbeat(userId: Int) {
        viewModelScope.launch {
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
        signedIn()?.let { graph.ops(it).clear() }
        tokens.clear(); jobs.forget(); _screen.value = Screen.SignIn()
    }

    /** The app came back to the front: experts get fresh jobs (and a new "today" after midnight). */
    fun onForeground() {
        if ((screen.value as? Screen.Home)?.me?.role == "expert") jobs.sync()
    }

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
        val p = screen.value as? Screen.Profile
        if (p != null) {
            val (drafts, files) = graph.drafts(p.me.id).unsentCounts()
            if (drafts + files > 0) {
                _screen.value = p.copy(error = "This phone still has $drafts job${if (drafts == 1) "" else "s"} and $files file${if (files == 1) "" else "s"} " +
                    "not sent. Connect to the internet and wait until Uploads is empty, then sign out.")
                return
            }
        }
        viewModelScope.launch {
            runCatching { api.logout() }
            signedIn()?.let { graph.ops(it).clear() }
            tokens.clear()
            jobs.forget()
            _screen.value = Screen.SignIn()
        }
    }
}
