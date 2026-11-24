package `in`.carcid.vayu.ui.expert

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.draft.LocalFile
import `in`.carcid.vayu.ui.components.ExpertBottomBar
import `in`.carcid.vayu.ui.components.ExpertTab
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.VayuTopBar
import `in`.carcid.vayu.ui.theme.Vayu

private fun size(bytes: Long): String = when {
    bytes >= 1L shl 30 -> "%.1f GB".format(bytes.toDouble() / (1L shl 30))
    bytes >= 1L shl 20 -> "%.0f MB".format(bytes.toDouble() / (1L shl 20))
    else -> "${bytes / 1024} KB"
}

/** Files still to send, by job, and the phone's space (sent copies can be cleared, unsent never). */
@Composable
fun UploadsScreen(me: Me, extras: ExpertExtras, onProfile: () -> Unit, onJobs: () -> Unit, onRefresh: () -> Unit) {
    val pending = extras.drafts.values.map { d -> d to d.files.filter { !it.sent } }.filter { it.second.isNotEmpty() }
    val count = pending.sumOf { it.second.size }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        VayuTopBar("Uploads", me.initials, bellCount = 0, onBell = {}, onProfile = onProfile)
        LazyColumn(Modifier.weight(1f).padding(horizontal = 20.dp)) {
            item {
                Text(if (count == 0) "Everything is sent." else "Sending $count file${if (count == 1) "" else "s"}",
                    color = Vayu.colors.muted, modifier = Modifier.padding(top = 12.dp, bottom = 4.dp))
            }
            pending.forEach { (d, files) ->
                item(d.bookingId) {
                    Text("${d.code} · ${d.customer}".uppercase(), fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                        color = Vayu.colors.muted, modifier = Modifier.padding(top = 20.dp, bottom = 4.dp))
                    files.forEach { FileRow(it) }
                }
            }
            item {
                Text("THIS PHONE", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.muted,
                    modifier = Modifier.padding(top = 24.dp, bottom = 4.dp))
                Column(Modifier.fillMaxWidth().heightIn(min = 58.dp), verticalArrangement = Arrangement.Center) {
                    Text("Free space", color = Vayu.colors.ink)
                    Text(size(extras.freeBytes), fontSize = 13.sp, color = if (extras.freeBytes < 2L shl 30) Vayu.colors.warn else Vayu.colors.muted)
                }
                HorizontalDivider(color = Vayu.colors.line)
                Row(Modifier.fillMaxWidth().heightIn(min = 64.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Photos already sent", color = Vayu.colors.ink)
                        Text("${size(extras.sentBytes)} · files not sent are never cleared", fontSize = 13.sp, color = Vayu.colors.muted)
                    }
                    if (extras.sentBytes > 0) SoftButton("Clear", extras.onClearSent)
                }
                Spacer(Modifier.height(24.dp))
            }
        }
        ExpertBottomBar(ExpertTab.UPLOADS, uploads = count, onTab = { if (it == ExpertTab.JOBS) onJobs() }, onRefresh = onRefresh)
    }
}

@Composable
private fun FileRow(f: LocalFile) {
    Row(Modifier.fillMaxWidth().heightIn(min = 60.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(40.dp).clip(RoundedCornerShape(8.dp)).background(Vayu.colors.illo)) {
            rememberThumb(f.path, 80)?.takeIf { f.contentType.startsWith("image/") }?.let {
                androidx.compose.foundation.Image(it, null, contentScale = androidx.compose.ui.layout.ContentScale.Crop, modifier = Modifier.fillMaxSize())
            }
        }
        Column(Modifier.weight(1f)) {
            Text(f.label, color = Vayu.colors.ink, fontWeight = FontWeight.SemiBold)
            when {
                f.error != null -> Text(f.error, fontSize = 13.sp, color = Vayu.colors.bad)
                f.progress > 0f -> Box(Modifier.padding(top = 6.dp).fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)).background(Vayu.colors.line)) {
                    Box(Modifier.fillMaxWidth(f.progress).height(4.dp).background(Vayu.colors.info))
                }
                else -> Text("Waiting", fontSize = 13.sp, color = Vayu.colors.muted)
            }
        }
        if (f.progress > 0f && f.error == null) Text("${(f.progress * 100).toInt()}%", fontSize = 13.sp, color = Vayu.colors.muted)
        else if (f.error != null) Box(Modifier.size(8.dp).clip(CircleShape).background(Vayu.colors.bad))
    }
    HorizontalDivider(color = Vayu.colors.line)
}
