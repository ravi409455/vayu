package `in`.carcid.vayu.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.DirectionsCar
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
import androidx.compose.ui.draw.clip
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
private fun Illustration(icon: androidx.compose.ui.graphics.vector.ImageVector) {
    Box(Modifier.fillMaxWidth().height(240.dp), contentAlignment = Alignment.Center) {
        Box(Modifier.size(210.dp).clip(CircleShape).background(Vayu.colors.soft), contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, tint = Vayu.colors.ink, modifier = Modifier.size(120.dp))
            Icon(Icons.Outlined.CheckCircle, contentDescription = null, tint = Vayu.colors.brand,
                modifier = Modifier.align(Alignment.TopEnd).padding(28.dp).size(40.dp))
        }
    }
}

@Composable
private fun Shell(content: @Composable () -> Unit) {
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding().verticalScroll(rememberScrollState())
        .padding(horizontal = 24.dp, vertical = 20.dp)) { content() }
}

@Composable
fun SignInScreen(state: Screen.SignIn, onSignIn: (String, String) -> Unit) = Shell {
    var user by rememberSaveable { mutableStateOf("") }
    var pass by rememberSaveable { mutableStateOf("") }
    var show by remember { mutableStateOf(false) }
    Brand()
    Illustration(Icons.Outlined.DirectionsCar)
    Text("Sign in", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
    Text("Welcome back. Your jobs are waiting.", color = Vayu.colors.muted)
    Spacer(Modifier.height(16.dp))
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        SoftField(user, { user = it }, "Username", icon = Icons.Outlined.Person)
        SoftField(pass, { pass = it }, "Password", icon = Icons.Outlined.Lock,
            visualTransformation = if (show) VisualTransformation.None else PasswordVisualTransformation(),
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
    Illustration(Icons.Outlined.Lock)
    Text("Admin tools live on the web", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
    Spacer(Modifier.height(8.dp))
    Text("The app is for Ops and experts. Open app.carcid.in on a laptop to manage forms, users and settings.",
        color = Vayu.colors.muted)
    Spacer(Modifier.height(28.dp))
    PrimaryButton("Sign in with another account", onBack)
}

@Composable
fun ChangePasswordScreen(state: Screen.ChangePassword, onSave: (String, String) -> Unit) = Shell {
    var a by rememberSaveable { mutableStateOf("") }
    var b by rememberSaveable { mutableStateOf("") }
    Brand()
    Illustration(Icons.Outlined.Lock)
    Text("Choose your password", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
    Text("Your Admin gave you a temporary one. Pick your own to carry on.", color = Vayu.colors.muted)
    Spacer(Modifier.height(16.dp))
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        SoftField(a, { a = it }, "New password", icon = Icons.Outlined.Lock, visualTransformation = PasswordVisualTransformation())
        SoftField(b, { b = it }, "Type it again", icon = Icons.Outlined.Lock, visualTransformation = PasswordVisualTransformation())
        if (state.error != null) Text(state.error, color = Vayu.colors.bad, style = MaterialTheme.typography.bodyMedium)
        PrimaryButton(if (state.busy) "Saving…" else "Save and continue", { onSave(a, b) }, enabled = !state.busy)
    }
}

/** Home by role. The real My jobs (Phase 14) and Today (Phase 16) replace these bodies. */
@Composable
fun HomeScreen(me: Me, onProfile: () -> Unit) {
    val ops = me.role == "ops"
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        VayuTopBar(if (ops) "Today" else "My jobs", me.initials, bellCount = 0, onBell = {}, onProfile = onProfile)
        Box(Modifier.weight(1f).fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
            Text(if (ops) "Today's jobs arrive with Phase 16." else "Your jobs arrive with Phase 14.",
                color = Vayu.colors.muted)
        }
        if (ops) OpsBottomBar(OpsTab.TODAY, {}, {}) else ExpertBottomBar(ExpertTab.JOBS, uploads = 0, {}, {})
    }
}

@Composable
fun ProfileScreen(state: Screen.Profile, onBack: () -> Unit, onTheme: (String) -> Unit, onSignOut: () -> Unit) {
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
            SectionLabel("Account")
            ListRow("Sign out", subtitle = "Signing in on another phone signs this one out", onClick = onSignOut)
        }
    }
}
