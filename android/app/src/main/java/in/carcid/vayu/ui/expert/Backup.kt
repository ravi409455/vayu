package `in`.carcid.vayu.ui.expert

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Folder
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.backup.BackupCopies
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.theme.Vayu

/**
 * Open Android's "All files access" page for this app; phones without it get the list of all apps.
 * Tried directly: on Android 11+ checking first (resolveActivity) can wrongly say it isn't there.
 */
private fun open(ctx: android.content.Context) {
    val flags = android.content.Intent.FLAG_ACTIVITY_NEW_TASK
    runCatching {
        ctx.startActivity(android.content.Intent(android.provider.Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
            android.net.Uri.fromParts("package", ctx.packageName, null)).addFlags(flags))
    }.recoverCatching {
        ctx.startActivity(android.content.Intent(android.provider.Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION).addFlags(flags))
    }
}

/** After sign-in, once per install (experts): backup copies need "All files access". No skip. */
@Composable
fun BackupAccessScreen() {
    val ctx = LocalContext.current
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(top = 48.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Box(Modifier.size(72.dp).clip(RoundedCornerShape(20.dp)).background(Vayu.colors.brandTint), contentAlignment = Alignment.Center) {
                Icon(Icons.Outlined.Folder, contentDescription = null, tint = Vayu.colors.brand, modifier = Modifier.size(34.dp))
            }
            Text("Turn on file access", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
            Text("Vayu keeps a backup copy of every photo, video and file you take for a lead, in Documents › Vayu on this phone.",
                color = Vayu.colors.ink)
            Text("If the app is ever removed, the copies stay, so you can still send them to Ops.", color = Vayu.colors.muted)
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Vayu.colors.soft).padding(horizontal = 16.dp, vertical = 4.dp)) {
                listOf("Tap Open settings", "Turn on Allow access to manage all files", "Come back to Vayu").forEachIndexed { i, step ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Box(Modifier.size(24.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.bg), contentAlignment = Alignment.Center) {
                            Text("${i + 1}", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
                        }
                        Text(step, color = Vayu.colors.ink)
                    }
                }
            }
        }
        Column(Modifier.padding(horizontal = 24.dp).padding(top = 16.dp, bottom = 28.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            PrimaryButton("Open settings", { open(ctx) })
            Text("You need this to take photos, videos and files.", fontSize = 13.sp, color = Vayu.colors.muted,
                modifier = Modifier.align(Alignment.CenterHorizontally))
        }
    }
}

/** Under the inspection header: new files get no backup copy (access turned off, or the phone is full). */
@Composable
fun BackupWarning(phoneFull: Boolean, onFreeSpace: () -> Unit) {
    val ctx = LocalContext.current
    Row(Modifier.fillMaxWidth().background(Vayu.colors.badTint).padding(start = 16.dp, end = 12.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Icon(Icons.Outlined.WarningAmber, contentDescription = null, tint = Vayu.colors.bad, modifier = Modifier.size(20.dp))
        Text(if (phoneFull) "Phone is full. New photos have no backup copy." else "Backups are off. New photos have no backup copy.",
            fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.bad, modifier = Modifier.weight(1f))
        Box(Modifier.heightIn(min = 44.dp).clip(RoundedCornerShape(10.dp)).border(1.dp, Vayu.colors.bad, RoundedCornerShape(10.dp))
            .clickable(role = androidx.compose.ui.semantics.Role.Button) { if (phoneFull) onFreeSpace() else open(ctx) }.padding(horizontal = 14.dp),
            contentAlignment = Alignment.Center) {
            Text(if (phoneFull) "Free space" else "Turn on", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.bad)
        }
    }
}

/** On My leads after a reinstall: copies the app can't send any more, until they are deleted. */
@Composable
fun FoundCopiesCard(found: BackupCopies.Found, modifier: Modifier = Modifier) {
    val day = java.time.Instant.ofEpochMilli(found.deleteAt).atZone(java.time.ZoneId.systemDefault()).toLocalDate()
        .format(java.time.format.DateTimeFormatter.ofPattern("d MMM"))
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Vayu.colors.warnTint).padding(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Icons.Outlined.Folder, contentDescription = null, tint = Vayu.colors.warn, modifier = Modifier.size(20.dp))
            Text("Found copies from your earlier install", fontWeight = FontWeight.Bold, color = Vayu.colors.warn)
        }
        Text(found.codes.joinToString("  "), fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
        Text("${found.files} ${if (found.files == 1) "file" else "photos, videos and files"} the app can't send any more. Send them to Ops:",
            fontSize = 14.sp, color = Vayu.colors.ink)
        Text("Files app › Documents › Vayu › lead folder › Share", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
        Text("They will be deleted on $day.", fontSize = 13.sp, color = Vayu.colors.muted)
    }
}
