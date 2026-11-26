package `in`.carcid.vayu.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.ui.components.Avatar
import `in`.carcid.vayu.ui.components.ExpertBottomBar
import `in`.carcid.vayu.ui.components.ExpertTab
import `in`.carcid.vayu.ui.components.ListRow
import `in`.carcid.vayu.ui.components.OpsBottomBar
import `in`.carcid.vayu.ui.components.OpsTab
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SectionLabel
import `in`.carcid.vayu.ui.components.Segmented
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.VayuTopBar
import `in`.carcid.vayu.ui.theme.Vayu

/** The Vayu mark: a white V with two wind lines on a red rounded square (approved prototype). */
@Composable
fun VayuMark(size: Int = 34) {
    val brand = Vayu.colors.brand
    Canvas(Modifier.size(size.dp).semantics { contentDescription = "Vayu" }) {
        val s = this.size.width / 48f
        drawRoundRect(brand, cornerRadius = CornerRadius(13 * s))
        drawPath(Path().apply { moveTo(14 * s, 15 * s); lineTo(24 * s, 34 * s); lineTo(34 * s, 15 * s) },
            Color.White, style = Stroke(5 * s, cap = StrokeCap.Round, join = StrokeJoin.Round))
        drawLine(Color.White.copy(alpha = .75f), androidx.compose.ui.geometry.Offset(30 * s, 34 * s),
            androidx.compose.ui.geometry.Offset(38 * s, 34 * s), 3 * s, StrokeCap.Round)
        drawLine(Color.White.copy(alpha = .75f), androidx.compose.ui.geometry.Offset(33 * s, 39 * s),
            androidx.compose.ui.geometry.Offset(38 * s, 39 * s), 3 * s, StrokeCap.Round)
    }
}

@Composable
private fun Brand() = Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
    VayuMark(); Text("Vayu", fontWeight = FontWeight.Bold, fontSize = 19.sp, color = Vayu.colors.ink)
}

@Composable
private fun Illustration(height: Int, drawing: @Composable () -> Unit) {
    Box(Modifier.fillMaxWidth().height(height.dp), contentAlignment = Alignment.Center) { drawing() }
}

@Composable
private fun Shell(content: @Composable () -> Unit) {
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding().verticalScroll(rememberScrollState())
        .padding(horizontal = 24.dp, vertical = 20.dp)) { content() }
}

@Composable
fun SignInScreen(state: Screen.SignIn, onSignIn: (String, String) -> Unit) = Shell {
    var user by rememberSaveable { mutableStateOf("") }
    var pass by remember { mutableStateOf("") }          // never saved to disk (no rememberSaveable)
    var show by remember { mutableStateOf(false) }
    Brand()
    Illustration(300) { SignInDrawing() }
    Text("Sign in", fontSize = 30.sp, lineHeight = 36.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
    Text("Welcome back. Your work is waiting.", color = Vayu.colors.muted)
    Spacer(Modifier.height(16.dp))
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        val focus = androidx.compose.ui.platform.LocalFocusManager.current
        SoftField(user, { user = it }, "Username", icon = Icons.Outlined.Person,
            imeAction = androidx.compose.ui.text.input.ImeAction.Next, onIme = { focus.moveFocus(androidx.compose.ui.focus.FocusDirection.Down) })
        SoftField(pass, { pass = it }, "Password", icon = Icons.Outlined.Lock,
            visualTransformation = if (show) VisualTransformation.None else PasswordVisualTransformation(), password = true,
            imeAction = androidx.compose.ui.text.input.ImeAction.Done, onIme = { if (!state.busy) onSignIn(user, pass) },
            trailing = {
                IconButton(onClick = { show = !show }) {
                    Icon(if (show) Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility,
                        contentDescription = if (show) "Hide password" else "Show password", tint = Vayu.colors.muted)
                }
            })
        if (state.error != null) Text(state.error, color = Vayu.colors.bad, style = MaterialTheme.typography.bodyMedium)
        PrimaryButton(if (state.busy) "Signing in…" else "Sign in", { onSignIn(user, pass) }, enabled = !state.busy)
        Text("Forgot your password? Ask your Admin.", color = Vayu.colors.muted, style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.align(Alignment.CenterHorizontally))
    }
}

@Composable
fun AdminRefusedScreen(onBack: () -> Unit) = Shell {
    Brand()
    Illustration(300) { AdminRefusedDrawing() }
    Text("Admin tools live on the web", fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
    Spacer(Modifier.height(8.dp))
    Text("The app is for Ops and experts. Open app.carcid.in on a laptop to manage forms, users and settings.",
        color = Vayu.colors.muted)
    Spacer(Modifier.height(28.dp))
    PrimaryButton("Sign in with another account", onBack)
}

@Composable
fun ChangePasswordScreen(state: Screen.ChangePassword, onSave: (String, String) -> Unit) = Shell {
    var a by remember { mutableStateOf("") }
    var b by remember { mutableStateOf("") }
    Brand()
    Illustration(210) { ChangePasswordDrawing() }
    Text("Choose your password", fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
    Text("Your Admin gave you a temporary one. Pick your own to carry on.", color = Vayu.colors.muted)
    Spacer(Modifier.height(16.dp))
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        SoftField(a, { a = it }, "New password", icon = Icons.Outlined.Lock, visualTransformation = PasswordVisualTransformation(), password = true)
        SoftField(b, { b = it }, "Type it again", icon = Icons.Outlined.Lock, visualTransformation = PasswordVisualTransformation(), password = true)
        if (state.error != null) Text(state.error, color = Vayu.colors.bad, style = MaterialTheme.typography.bodyMedium)
        PrimaryButton(if (state.busy) "Saving…" else "Save and continue", { onSave(a, b) }, enabled = !state.busy)
    }
}

@Composable
fun ProfileScreen(state: Screen.Profile, onBack: () -> Unit, onTheme: (String) -> Unit, onSignOut: () -> Unit,
                  /** Ops: switch a kind of notification on or off. */
                  onNotify: (String, Boolean) -> Unit = { _, _ -> },
                  /** Phone storage for App settings (experts); null hides App settings. */
                  storage: (() -> `in`.carcid.vayu.ui.expert.StorageInfo)? = null,
                  /** This build's version, and a newer one on offer (null: up to date). */
                  version: String = "", update: String? = null, onUpdate: () -> Unit = {},
                  /** The sign-out warning ([Screen.Profile.unsent]): sign out anyway, or stay. */
                  onSignOutAnyway: () -> Unit = {}, onStaySignedIn: () -> Unit = {}) {
    var page by rememberSaveable { mutableStateOf("") }
    if (page == "settings" && storage != null) {
        androidx.activity.compose.BackHandler { page = "" }
        AppSettingsScreen(onBack = { page = "" }, onStorage = { page = "storage" }, storage = storage())
        return
    }
    if (page == "storage" && storage != null) {
        `in`.carcid.vayu.ui.expert.StorageScreen(storage(), onBack = { page = "settings" })
        return
    }
    val me = state.me
    val themes = listOf("light", "dark", "system")
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        IconButton(onClick = onBack, modifier = Modifier.padding(6.dp)) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = Vayu.colors.ink)
        }
        Column(Modifier.padding(horizontal = 20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Avatar(me.initials, size = 64)
                Column {
                    Text(me.name.ifBlank { me.username }, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
                    Text("${me.role.replaceFirstChar { it.uppercase() }} · ${me.username}", color = Vayu.colors.muted)
                }
            }
            SectionLabel("Look")
            Segmented(listOf("Light", "Dark", "Match phone"), themes.indexOf(me.theme).coerceAtLeast(0), { onTheme(themes[it]) })
            if (state.error != null) Text(state.error, color = Vayu.colors.bad, modifier = Modifier.padding(top = 8.dp))
            // blocked notices drop new work, reminders and photo alerts without a word: say so (checked again on coming back)
            val ctx = androidx.compose.ui.platform.LocalContext.current
            var noticesOff by remember { mutableStateOf(false) }
            androidx.lifecycle.compose.LifecycleResumeEffect(Unit) {
                noticesOff = !androidx.core.app.NotificationManagerCompat.from(ctx).areNotificationsEnabled(); onPauseOrDispose {}
            }
            if (noticesOff) `in`.carcid.vayu.ui.components.SettingsNudge(
                "Notifications are off: new ${if (me.role == "ops") "bookings" else "leads"}, reminders and alerts won't show.",
                "Turn on", `in`.carcid.vayu.ui.components.noticeSettings(ctx), Modifier.padding(top = 16.dp))
            if (me.role == "ops") {
                SectionLabel("Notifications")
                NotifyRow("Problems", null) {}
                listOf("submitted" to "Submitted and completed", "started" to "Started and late starts", "new_bookings" to "New bookings")
                    .forEach { (key, label) -> NotifyRow(label, key !in me.muted) { onNotify(key, it) } }
            }
            if (storage != null) {
                SectionLabel("App")
                ListRow("App settings", subtitle = "Phone storage", onClick = { page = "settings" })
            }
            SectionLabel("Account")
            ListRow("Sign out", subtitle = "Signing in on another phone signs this one out", onClick = onSignOut)
            if (update != null) ListRow("Update available", subtitle = "Vayu $update · you have $version", onClick = onUpdate)
            else if (version.isNotBlank()) Text("Vayu $version · up to date", fontSize = 13.sp, color = Vayu.colors.muted,
                modifier = Modifier.padding(top = 16.dp))
        }
    }
    state.unsent?.let { SignOutUnsentSheet(it, onSignOutAnyway, onStaySignedIn) }
}

/** Signing out with leads not sent yet: they stay on this phone and send at the next sign-in here. */
@Composable
private fun SignOutUnsentSheet(leads: List<String>, onSignOut: () -> Unit, onStay: () -> Unit) =
    `in`.carcid.vayu.ui.components.VayuSheet(onStay, footer = {
        Row(Modifier.padding(horizontal = 20.dp).padding(top = 8.dp, bottom = 20.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            `in`.carcid.vayu.ui.components.SoftButton("Stay signed in", onStay, Modifier.weight(1f))
            PrimaryButton("Sign out", onSignOut, Modifier.weight(1f))
        }
    }) {
        Column(Modifier.padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Sign out with unsent work?", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
            @OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
            androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                leads.forEach { code ->
                    Text(code, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = Vayu.colors.ink,
                        modifier = Modifier.clip(androidx.compose.foundation.shape.RoundedCornerShape(8.dp)).background(Vayu.colors.soft)
                            .padding(horizontal = 10.dp, vertical = 4.dp))
                }
            }
            Text(if (leads.size == 1) "This lead is not sent yet. It stays on this phone and sends when you sign in again."
                else "These leads are not sent yet. They stay on this phone and send when you sign in again.", color = Vayu.colors.ink)
            Text("While you're signed out, nothing is sent. Sign in on this phone to send ${if (leads.size == 1) "it" else "them"}.", fontSize = 14.sp, color = Vayu.colors.muted)
        }
    }

/** One notification switch; [on] null means it can't be turned off ("Always on"). */
@Composable
private fun NotifyRow(label: String, on: Boolean?, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).let { m -> if (on == null) m else m.toggleable(on, role = androidx.compose.ui.semantics.Role.Switch, onValueChange = onChange) },
        verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = Vayu.colors.ink, modifier = Modifier.weight(1f))
        if (on == null) Text("Always on", color = Vayu.colors.muted, fontSize = 14.sp)
        else androidx.compose.material3.Switch(checked = on, onCheckedChange = null)
    }
}

/** App settings: what this phone keeps (more settings can join here). */
@Composable
fun AppSettingsScreen(onBack: () -> Unit, onStorage: () -> Unit, storage: `in`.carcid.vayu.ui.expert.StorageInfo) {
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        IconButton(onClick = onBack, modifier = Modifier.padding(6.dp)) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = Vayu.colors.ink)
        }
        Text("App settings", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink, modifier = Modifier.padding(horizontal = 20.dp))
        Column(Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
            ListRow("Phone storage", subtitle = "${`in`.carcid.vayu.ui.expert.sizeText(storage.freeBytes)} free", onClick = onStorage)
        }
    }
}
