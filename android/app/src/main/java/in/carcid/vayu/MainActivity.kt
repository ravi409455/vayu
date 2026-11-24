package `in`.carcid.vayu

import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.auth.PrefsTokenStore
import `in`.carcid.vayu.core.sync.JobStore
import `in`.carcid.vayu.ui.expert.ExpertHome
import `in`.carcid.vayu.ui.AdminRefusedScreen
import `in`.carcid.vayu.ui.AppViewModel
import `in`.carcid.vayu.ui.ChangePasswordScreen
import `in`.carcid.vayu.ui.HomeScreen
import `in`.carcid.vayu.ui.ProfileScreen
import `in`.carcid.vayu.ui.Screen
import `in`.carcid.vayu.ui.SignInScreen
import `in`.carcid.vayu.ui.theme.ThemeMode
import `in`.carcid.vayu.ui.theme.Vayu
import `in`.carcid.vayu.ui.theme.VayuTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val tokens = PrefsTokenStore(applicationContext)
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                AppViewModel(Api(BuildConfig.API_URL, tokens), tokens, Build.MODEL,
                    storeFor = { JobStore(java.io.File(filesDir, "jobs-$it.json")) }) as T
        }
        setContent { AppRoot(viewModel(factory = factory)) }
    }
}

fun themeOf(s: Screen): ThemeMode = when ((s as? Screen.Home)?.me?.theme ?: (s as? Screen.Profile)?.me?.theme) {
    "dark" -> ThemeMode.DARK
    "system" -> ThemeMode.SYSTEM
    else -> ThemeMode.LIGHT          // sign-in and the default are Light, like the web
}

@Composable
fun AppRoot(vm: AppViewModel) {
    val screen by vm.screen.collectAsState()
    VayuTheme(themeOf(screen)) {
        when (val s = screen) {
            Screen.Loading -> Box(Modifier.fillMaxSize().background(Vayu.colors.bg))
            is Screen.SignIn -> SignInScreen(s, vm::signIn)
            Screen.AdminRefused -> AdminRefusedScreen(vm::backToSignIn)
            is Screen.ChangePassword -> ChangePasswordScreen(s, vm::changePassword)
            is Screen.Home -> if (s.me.role == "expert") {
                val jobs by vm.jobs.collectAsState()
                ExpertHome(s.me, jobs, vm.today(), vm::openProfile, vm::sync, onStart = {})  // check-in: Phase 14b
            } else HomeScreen(s.me, vm::openProfile)
            is Screen.Profile -> {
                BackHandler { vm.closeProfile() }
                ProfileScreen(s, vm::closeProfile, vm::setTheme, vm::signOut)
            }
        }
    }
}
