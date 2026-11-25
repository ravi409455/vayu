package `in`.carcid.vayu.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.update.AppUpdate
import `in`.carcid.vayu.core.update.download
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import java.io.File

fun mb(bytes: Long): String = "%.0f MB".format(bytes / 1_048_576.0).let { if (bytes in 1 until 1_048_576) "1 MB" else it }

/** "Update available": what's new, download (with progress, checked), then Android's install prompt. */
@Composable
fun UpdateScreen(u: AppUpdate, onLater: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val file = remember(u.code) { File(ctx.cacheDir, "update/vayu-${u.code}.apk") }
    var got by remember { mutableLongStateOf(0L) }
    var busy by remember { mutableStateOf(false) }
    var ready by remember { mutableStateOf(file.exists()) }
    var error by remember { mutableStateOf<String?>(null) }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding().padding(horizontal = 24.dp)
        .verticalScroll(rememberScrollState())) {
        Spacer(Modifier.height(48.dp))
        Text("Update available", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.brand)
        Text("A new version of Vayu is ready", fontSize = 26.sp, lineHeight = 32.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink,
            modifier = Modifier.padding(top = 6.dp))
        Text("Version ${u.name}" + (if (u.size > 0) " · ${mb(u.size)}." else ".") +
            (if (u.required) " You need it for new work. Work you already started can be finished on this version." else ""),
            color = Vayu.colors.muted, modifier = Modifier.padding(top = 10.dp))
        if (u.notes.isNotEmpty()) {
            Text("What's new", fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, modifier = Modifier.padding(top = 24.dp, bottom = 6.dp))
            u.notes.forEach { Text("· $it", color = Vayu.colors.ink, modifier = Modifier.padding(vertical = 2.dp)) }
        }
        Spacer(Modifier.height(32.dp))
        if (busy) {
            Text("Downloading · ${mb(got)}" + (if (u.size > 0) " of ${mb(u.size)}" else ""), color = Vayu.colors.muted)
            LinearProgressIndicator(progress = { if (u.size > 0) (got.toFloat() / u.size).coerceIn(0f, 1f) else 0f },
                modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp), color = Vayu.colors.brand, trackColor = Vayu.colors.soft)
        }
        error?.let { Text(it, color = Vayu.colors.bad, modifier = Modifier.padding(bottom = 10.dp)) }
        PrimaryButton(if (ready) "Install update" else if (busy) "Downloading…" else "Download update", enabled = !busy, onClick = {
            if (ready) install(ctx, file) else {
            busy = true; error = null
            scope.launch {
                try {
                    file.parentFile?.listFiles()?.forEach { it.delete() }        // older downloads
                    download(OkHttpClient(), u, file) { got = it }
                    ready = true
                    install(ctx, file)
                } catch (e: ApiError) {
                    error = e.message
                } finally { busy = false }
            }
            }
        })
        Text("Android will ask you to confirm the install.", fontSize = 13.sp, color = Vayu.colors.muted,
            modifier = Modifier.padding(top = 8.dp).align(Alignment.CenterHorizontally))
        TextButton(onClick = onLater, modifier = Modifier.align(Alignment.CenterHorizontally).padding(top = 8.dp)) {
            Text("Later", color = Vayu.colors.brand)
        }
    }
}

/** Hand the checked APK to Android's installer (first time: allow installs from Vayu in Settings). */
private fun install(ctx: Context, file: File) {
    if (!ctx.packageManager.canRequestPackageInstalls()) {
        ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}")))
        return
    }
    val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", file)
    ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
}
