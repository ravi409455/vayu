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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.edit
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.luminance
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
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
import `in`.carcid.vayu.ui.ProfileScreen
import `in`.carcid.vayu.ui.Screen
import `in`.carcid.vayu.ui.SignInScreen
import `in`.carcid.vayu.ui.theme.ThemeMode
import `in`.carcid.vayu.ui.theme.Vayu
import `in`.carcid.vayu.ui.theme.VayuTheme

class MainActivity : ComponentActivity() {
    private val factory = object : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            AppViewModel((application as VayuApp).graph, Build.MODEL, appVersion = BuildConfig.VERSION_CODE,
                elapsed = android.os.SystemClock::elapsedRealtime) as T
    }
    private val vm: AppViewModel by lazy { ViewModelProvider(this, factory)[AppViewModel::class.java] }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // a tapped notice: read here, not in a composable effect (after Android closed the app, the
        // tap arrives before the first frame and would be lost)
        if (savedInstanceState == null) opened(intent, vm)
        setContent {
            androidx.lifecycle.compose.LifecycleResumeEffect(vm) { vm.onForeground(); onPauseOrDispose {} }
            AppRoot(vm)
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        opened(intent, vm)
    }
}

/** A tapped notice opens its lead or booking. */
private fun opened(intent: android.content.Intent?, vm: AppViewModel) {
    intent?.getStringExtra(Notices.EXTRA_BOOKING)?.let { vm.opening.value = it; intent.removeExtra(Notices.EXTRA_BOOKING) }
}

fun themeOf(s: Screen): ThemeMode = when ((s as? Screen.Home)?.me?.theme ?: (s as? Screen.Profile)?.me?.theme) {
    "dark" -> ThemeMode.DARK
    "system" -> ThemeMode.SYSTEM
    else -> ThemeMode.LIGHT          // sign-in and the default are Light, like the web
}

@Composable
fun AppRoot(vm: AppViewModel) {
    val screen by vm.screen.collectAsState()
    val update by vm.update.collectAsState()
    val showUpdate by vm.showUpdate.collectAsState()
    VayuTheme(themeOf(screen)) {
        // status bar icons follow the app's own light / dark look, not the phone's setting
        val activity = androidx.activity.compose.LocalActivity.current as? ComponentActivity
        val dark = Vayu.colors.bg.luminance() < 0.5f
        androidx.compose.runtime.LaunchedEffect(dark) {
            val clear = android.graphics.Color.TRANSPARENT
            activity?.enableEdgeToEdge(
                statusBarStyle = if (dark) androidx.activity.SystemBarStyle.dark(clear) else androidx.activity.SystemBarStyle.light(clear, clear),
                navigationBarStyle = if (dark) androidx.activity.SystemBarStyle.dark(clear) else androidx.activity.SystemBarStyle.light(clear, clear))
        }
        val u = update
        if (u != null && showUpdate && (screen is Screen.Home || screen is Screen.Profile)) {
            BackHandler { vm.showUpdate.value = false }
            val dl by vm.updateDownload.collectAsState()
            `in`.carcid.vayu.ui.UpdateScreen(u, onLater = { vm.showUpdate.value = false }, state = dl, onDownload = { f -> vm.downloadUpdate(u, f) })
            return@VayuTheme
        }
        when (val s = screen) {
            Screen.Loading -> Box(Modifier.fillMaxSize().background(Vayu.colors.bg))
            is Screen.SignIn -> SignInScreen(s, vm::signIn)
            Screen.AdminRefused -> AdminRefusedScreen(vm::backToSignIn)
            is Screen.ChangePassword -> ChangePasswordScreen(s, vm::changePassword)
            is Screen.Home -> {
              AskForNotices()
              if (s.me.role == "expert" && !fileAccessGiven(vm.graph.backup != null)) {
                `in`.carcid.vayu.ui.expert.BackupAccessScreen()
            } else if (s.me.role == "expert") {
                val jobs by vm.jobs.state.collectAsState()
                ExpertHome(s.me, jobs, vm.jobs.today(), vm::openProfile, { vm.jobs.sync(); vm.graph.kick() }, expertExtras(vm, s.me))
            } else {
                val bell by vm.bell.state.collectAsState()
                `in`.carcid.vayu.ui.ops.OpsHome(s.me, remember(s.me.id) { vm.graph.ops(s.me.id) }, vm.jobs::today, vm::openProfile,
                    bell = bell, onRead = vm.bell::read, onBell = vm.bell::refresh,
                    opening = vm.opening.collectAsState().value, onOpened = { vm.opening.value = null })
            }
            }
            is Screen.Profile -> {
                BackHandler { vm.closeProfile() }
                val extras = if (s.me.role == "expert") expertExtras(vm, s.me) else null
                ProfileScreen(s, vm::closeProfile, vm::setTheme, { vm.signOut() }, vm::setNotify, storage = extras?.let { e -> { e.storage } },
                    version = BuildConfig.VERSION_NAME, update = update?.name, onUpdate = { vm.showUpdate.value = true },
                    onSignOutAnyway = { vm.signOut(confirmed = true) }, onStaySignedIn = vm::keepSignedIn)
            }
        }
    }
}

/** Android 13+: ask once, after sign-in, to show notices (new jobs, problems, reminders). */
@Composable
private fun AskForNotices() {
    if (Build.VERSION.SDK_INT < 33) return
    val ctx = LocalContext.current
    val ask = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) {}
    androidx.compose.runtime.LaunchedEffect(Unit) {
        if (androidx.core.content.ContextCompat.checkSelfPermission(ctx, android.Manifest.permission.POST_NOTIFICATIONS) !=
            android.content.pm.PackageManager.PERMISSION_GRANTED) ask.launch(android.Manifest.permission.POST_NOTIFICATIONS)
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
    val bell by vm.bell.state.collectAsState()
    val opening by vm.opening.collectAsState()
    val found = vm.graph.backup?.found?.collectAsState()?.value
    return remember(tick, jobs, bell, opening, found) {
        ExpertExtras(
            drafts = drafts.all().associateBy { it.bookingId },
            notices = vm.jobs.notices(),
            updateNeeded = BuildConfig.VERSION_CODE < vm.minAppVersion,
            freeBytes = runCatching { StatFs(ctx.filesDir.path).availableBytes }.getOrDefault(Long.MAX_VALUE),
            sentBytes = drafts.sentBytes(),
            inspection = { job ->
                val verified = vm.jobs.verified()
                val d = InspectionModel.begin(drafts, job, verified, store.bookingAnswers(job.id))
                // started on another phone: fetch the files the server already holds now, so they show
                // before the expert retakes them (F-10: "0 of 1", then "2 of 1" after a new photo)
                if (d.reconcile) vm.graph.kick()
                InspectionEnv(InspectionModel(drafts, store, job.id, vm.jobs::now, vm.graph.kick, vm.jobs::verified, vm.graph.backup), drafts, me.name.ifBlank { me.username },
                    verified, vm.jobs::now, store::list, store.types(),
                    asset = { id -> loadAsset(ctx.cacheDir, id, vm.graph.api::formAsset) },
                    opsChanges = vm.jobs.notices().filter { it.first == job.id }.map { it.second },
                    backup = vm.graph.backup, fileAccess = ::hasFileAccess)
            },
            onDiscard = { drafts.discard(it); vm.graph.backup?.dropBooking(it) },
            onClearSent = { drafts.clearSentCopies() },
            listed = jobs.jobs.map { it.id }.toSet(),
            onSend = { id -> InspectionModel(drafts, store, id, vm.jobs::now, vm.graph.kick).submit() },
            onRemoveFile = { d, f -> InspectionModel(drafts, store, d.bookingId, vm.jobs::now, vm.graph.kick, backup = vm.graph.backup).removeFile(f.part, f.field, f.id) },
            phones = jobs.jobs.associate { it.id to it.phone },
            bell = bell, onBell = vm.bell::refresh, onRead = vm.bell::read,
            opening = vm.opening.value, onOpened = { vm.opening.value = null },
            found = found,
        )
    }
}

/**
 * Experts turn on "All files access" once per install, for the backup copies (docs/plan-media-backup.md);
 * until then the app shows only that screen. Turned off later, it only warns (the camera keeps
 * working). [needed]: false where there are no backup copies (tests).
 */
@Composable
private fun fileAccessGiven(needed: Boolean): Boolean {
    if (!needed) return true
    val ctx = LocalContext.current
    val prefs = remember { ctx.getSharedPreferences("vayu.install", android.content.Context.MODE_PRIVATE) }
    var given by remember { mutableStateOf(prefs.getBoolean("files_ok", false)) }
    androidx.lifecycle.compose.LifecycleResumeEffect(Unit) {
        if (!given && hasFileAccess()) { prefs.edit { putBoolean("files_ok", true) }; given = true }
        onPauseOrDispose {}
    }
    return given
}
