package `in`.carcid.vayu.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.auth.TokenStore
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
class AppViewModel(private val api: Api, private val tokens: TokenStore, private val deviceName: String) : ViewModel() {
    private val _screen = MutableStateFlow<Screen>(Screen.Loading)
    val screen: StateFlow<Screen> = _screen
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
            _screen.value = if (e.code == ApiError.NETWORK && cached != null) Screen.Home(cached) else Screen.SignIn()
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
        try {
            minAppVersion = api.heartbeat(drafts = 0, files = 0)     // nothing is stored on the phone yet
        } catch (e: ApiError) {
            if (e.code == "DEVICE_REVOKED") { tokens.clear(); _screen.value = Screen.SignIn() }
        }
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
        viewModelScope.launch {
            runCatching { api.logout() }
            tokens.clear()
            _screen.value = Screen.SignIn()
        }
    }
}
