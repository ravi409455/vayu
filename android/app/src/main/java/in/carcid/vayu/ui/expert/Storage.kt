package `in`.carcid.vayu.ui.expert

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.theme.Vayu

/** What Phone storage shows and does (experts: photos and videos kept on the phone). */
class StorageInfo(val freeBytes: Long, val sentBytes: Long, val waitingFiles: Int,
                  /** Remove the copies the server already has; returns the bytes freed. */
                  val freeUp: () -> Long)

fun sizeText(bytes: Long): String = when {
    bytes >= 1L shl 30 -> "%.1f GB".format(bytes.toDouble() / (1L shl 30))
    bytes >= 1L shl 20 -> "%.0f MB".format(bytes.toDouble() / (1L shl 20))
    else -> "${bytes / 1024} KB"
}

/** Phone storage: free space, and freeing the photos already sent (never ones still waiting). */
@Composable
fun StorageScreen(info: StorageInfo, onBack: () -> Unit, say: (String) -> Unit = {}) {
    BackHandler(onBack = onBack)
    var confirm by remember { mutableStateOf(false) }
    var sent by remember(info) { mutableStateOf(info.sentBytes) }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        IconButton(onClick = onBack, modifier = Modifier.padding(start = 6.dp, top = 10.dp)) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = Vayu.colors.ink)
        }
        Text("Phone storage", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink, modifier = Modifier.padding(horizontal = 20.dp))
        Column(Modifier.padding(horizontal = 20.dp, vertical = 12.dp)) {
            Column(Modifier.fillMaxWidth().heightIn(min = 58.dp), verticalArrangement = Arrangement.Center) {
                Text("Free space", color = Vayu.colors.ink)
                Text(sizeText(info.freeBytes) + if (info.freeBytes < 2L shl 30) " · running low" else "", fontSize = 13.sp,
                    color = if (info.freeBytes < 2L shl 30) Vayu.colors.warn else Vayu.colors.muted)
            }
            HorizontalDivider(color = Vayu.colors.line)
            Row(Modifier.fillMaxWidth().heightIn(min = 64.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Free up space", color = Vayu.colors.ink)
                    Text(if (sent > 0) "Removes ${sizeText(sent)} of photos already sent." else "Nothing to remove right now.",
                        fontSize = 13.sp, color = Vayu.colors.muted)
                }
                if (sent > 0) SoftButton("Free up", { confirm = true })
            }
            HorizontalDivider(color = Vayu.colors.line)
            Text(if (info.waitingFiles > 0) "${info.waitingFiles} file${if (info.waitingFiles == 1) "" else "s"} still waiting to send stay on the phone until they arrive."
                else "Photos still waiting to send are never removed.", fontSize = 13.sp, color = Vayu.colors.muted,
                modifier = Modifier.padding(top = 14.dp))
        }
    }
    if (confirm) AlertDialog(onDismissRequest = { confirm = false },
        title = { Text("Free up ${sizeText(sent)}?") },
        text = { Text("Photos and videos the server already has are removed from this phone. They stay safe on the server; nothing waiting to send is touched.") },
        confirmButton = { TextButton({ confirm = false; val n = info.freeUp(); sent = 0; say("Freed ${sizeText(n)}.") }) { Text("Free up") } },
        dismissButton = { TextButton({ confirm = false }) { Text("Keep them") } })
}
