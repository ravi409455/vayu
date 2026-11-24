package `in`.carcid.vayu.ui.expert

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.SdStorage
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.VayuTopBar
import `in`.carcid.vayu.ui.theme.Vayu

private fun size(bytes: Long): String = when {
    bytes >= 1L shl 30 -> "%.1f GB".format(bytes.toDouble() / (1L shl 30))
    bytes >= 1L shl 20 -> "%.0f MB".format(bytes.toDouble() / (1L shl 20))
    else -> "${bytes / 1024} KB"
}

/** Files still to send, by job, and the phone's space (sent copies can be cleared, unsent never). */
@Composable
fun UploadsScreen(me: Me, extras: ExpertExtras, onProfile: () -> Unit, onJobs: () -> Unit, onRefresh: () -> Unit,
                  onBell: () -> Unit = {}, refreshing: Boolean = false, say: (String) -> Unit = {}) {
    var storage by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf(false) }
    if (storage) { StorageScreen(extras.storage, onBack = { storage = false }, say = say); return }
    var query by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf("") }
    var openId by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf<String?>(null) }
    val pending = extras.drafts.values.map { d -> d to d.files.filter { !it.sent } }.filter { it.second.isNotEmpty() }
    val count = pending.sumOf { it.second.size }
    // one booking's files on their own screen
    pending.firstOrNull { it.first.bookingId == openId }?.let { (d, files) ->
        androidx.activity.compose.BackHandler { openId = null }
        Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
            androidx.compose.material3.IconButton(onClick = { openId = null }, modifier = Modifier.padding(start = 6.dp, top = 10.dp)) {
                androidx.compose.material3.Icon(androidx.compose.material.icons.Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back to Uploads", tint = Vayu.colors.ink)
            }
            Text(d.customer.ifBlank { d.code }, fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink, modifier = Modifier.padding(horizontal = 20.dp))
            Text("${d.code} · ${files.size} file${if (files.size == 1) "" else "s"} to send", color = Vayu.colors.muted, modifier = Modifier.padding(horizontal = 20.dp))
            LazyColumn(Modifier.weight(1f).padding(horizontal = 20.dp, vertical = 8.dp)) { items(files.size) { FileRow(files[it]) } }
        }
        return
    }
    val needle = query.trim().lowercase()
    val digits = needle.filter { it.isDigit() }
    val shown = pending.filter { (d, _) ->
        needle.isEmpty() || d.code.lowercase().contains(needle) || d.customer.lowercase().contains(needle) ||
            (digits.length >= 4 && (extras.phones[d.bookingId] ?: "").filter { it.isDigit() }.contains(digits))
    }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
        VayuTopBar("Uploads", me.initials, bellCount = extras.bell.unread, onBell = onBell, onProfile = onProfile) {
            androidx.compose.material3.IconButton(onClick = { storage = true }) {
                androidx.compose.material3.Icon(androidx.compose.material.icons.Icons.Outlined.SdStorage, contentDescription = "Phone storage", tint = Vayu.colors.ink)
            }
        }
        LazyColumn(Modifier.weight(1f).padding(horizontal = 20.dp)) {
            item {
                Text(if (count == 0) "Everything is sent." else "Sending $count file${if (count == 1) "" else "s"} from ${pending.size} job${if (pending.size == 1) "" else "s"}",
                    color = Vayu.colors.muted, modifier = Modifier.padding(top = 12.dp, bottom = 10.dp))
                if (pending.isNotEmpty()) SoftField(query, { query = it }, "Booking ID, customer or phone",
                    icon = androidx.compose.material.icons.Icons.Outlined.Search)
            }
            items(shown.size, key = { shown[it].first.bookingId }) { i ->
                val (d, files) = shown[i]
                val failed = files.count { it.error != null }
                Column(Modifier.fillMaxWidth().clickable(role = androidx.compose.ui.semantics.Role.Button) { openId = d.bookingId }) {
                    Row(Modifier.fillMaxWidth().heightIn(min = 64.dp), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(d.code, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
                            Text(d.customer + if (failed > 0) " · $failed need you" else "", fontSize = 13.sp,
                                color = if (failed > 0) Vayu.colors.bad else Vayu.colors.muted)
                        }
                        Box(Modifier.clip(RoundedCornerShape(12.dp)).background(if (failed > 0) Vayu.colors.badTint else Vayu.colors.infoTint)
                            .padding(horizontal = 10.dp, vertical = 4.dp)) {
                            Text("${files.size}", fontWeight = FontWeight.Bold, color = if (failed > 0) Vayu.colors.bad else Vayu.colors.info)
                        }
                        androidx.compose.material3.Icon(androidx.compose.material.icons.Icons.Outlined.ChevronRight, null, tint = Vayu.colors.muted)
                    }
                    HorizontalDivider(color = Vayu.colors.line)
                }
            }
            if (pending.isNotEmpty() && shown.isEmpty()) item {
                Text("No job matches \"$query\".", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 20.dp))
            }
        }
        ExpertBottomBar(ExpertTab.UPLOADS, uploads = count, onTab = { if (it == ExpertTab.JOBS) onJobs() }, onRefresh = onRefresh, refreshing = refreshing)
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
