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
import `in`.carcid.vayu.ui.expert.ExpertExtras
import `in`.carcid.vayu.ui.expert.ExpertHome
import `in`.carcid.vayu.ui.expert.InspectionEnv
import `in`.carcid.vayu.ui.expert.InspectionModel
import `in`.carcid.vayu.ui.expert.loadAsset
import android.os.StatFs
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
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
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                AppViewModel((application as VayuApp).graph, Build.MODEL) as T
        }
        setContent {
            val vm: AppViewModel = viewModel(factory = factory)
            androidx.lifecycle.compose.LifecycleResumeEffect(vm) { vm.onForeground(); onPauseOrDispose {} }
            AppRoot(vm)
        }
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
                val jobs by vm.jobs.state.collectAsState()
                ExpertHome(s.me, jobs, vm.jobs.today(), vm::openProfile, vm.jobs::sync, expertExtras(vm, s.me))
            } else `in`.carcid.vayu.ui.ops.OpsHome(s.me, remember(s.me.id) { vm.graph.ops(s.me.id) }, vm.jobs::today, vm::openProfile)
            is Screen.Profile -> {
                BackHandler { vm.closeProfile() }
                ProfileScreen(s, vm::closeProfile, vm::setTheme, vm::signOut)
            }
        }
    }
}

/** Drafts, notices and the inspection screens for the signed-in expert. */
@Composable
private fun expertExtras(vm: AppViewModel, me: `in`.carcid.vayu.core.api.Me): ExpertExtras {
    val ctx = LocalContext.current
    val drafts = vm.graph.drafts(me.id)
    val store = vm.graph.jobs(me.id)
    val tick by drafts.changes.collectAsState()
    val jobs by vm.jobs.state.collectAsState()
    return remember(tick, jobs) {
        ExpertExtras(
            drafts = drafts.all().associateBy { it.bookingId },
            notices = vm.jobs.notices(),
            updateNeeded = BuildConfig.VERSION_CODE < vm.minAppVersion,
            freeBytes = runCatching { StatFs(ctx.filesDir.path).availableBytes }.getOrDefault(Long.MAX_VALUE),
            sentBytes = drafts.sentBytes(),
            inspection = { job ->
                val verified = vm.jobs.verified()
                InspectionModel.begin(drafts, job, verified)
                InspectionEnv(InspectionModel(drafts, store, job.id, vm.jobs::now, vm.graph.kick), drafts, me.name.ifBlank { me.username },
                    verified, vm.jobs::now, store::list, store.types(),
                    asset = { id -> loadAsset(ctx.cacheDir, id, vm.graph.api::formAsset) },
                    opsChanges = vm.jobs.notices().filter { it.first == job.id }.map { it.second })
            },
            onDiscard = { drafts.discard(it) },
            onClearSent = { drafts.clearSentCopies() },
        )
    }
}
