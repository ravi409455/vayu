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
import `in`.carcid.vayu.core.draft.JOB_CLOSED
import `in`.carcid.vayu.core.draft.LocalFile
import `in`.carcid.vayu.ui.components.ExpertBottomBar
import `in`.carcid.vayu.ui.components.ExpertTab
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.VayuTopBar
import `in`.carcid.vayu.ui.theme.Vayu

/** What still has to happen for a draft to leave the phone, in a few words (null: only files to send). */
fun waitingFor(d: `in`.carcid.vayu.core.draft.Draft, listed: Boolean): String? = when {
    d.problemCode == JOB_CLOSED -> "Closed on the server · discard it"
    d.submitSent -> null
    !listed && d.startedAt == null -> "No longer on your list · never started"
    !listed -> "No longer on your list · send or discard it"
    d.submittedAt == null -> "Not submitted yet"
    else -> "Answers waiting to send"
}

/**
 * Everything on the phone not yet at the server, by lead: answers not submitted, files to send,
 * files refused, drafts of leads no longer on the list. Exactly what sign-out waits for. Sent
 * copies can be cleared (Phone storage); unsent ones never.
 */
@Composable
fun UploadsScreen(me: Me, extras: ExpertExtras, onProfile: () -> Unit, onJobs: () -> Unit, onRefresh: () -> Unit,
                  onBell: () -> Unit = {}, refreshing: Boolean = false, say: (String) -> Unit = {}, onOpenLead: (String) -> Unit = {}) {
    var storage by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf(false) }
    if (storage) { StorageScreen(extras.storage, onBack = { storage = false }, say = say); return }
    var query by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf("") }
    var openId by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf<String?>(null) }
    // a file the server refused for good no longer blocks sign-out, but stays listed until removed
    val pending = extras.drafts.values.filter { it.unsent || it.files.any { f -> f.refused } }.sortedBy { it.code }.map { d -> d to d.files.filter { !it.verified } }
    val count = pending.sumOf { it.second.size }
    // one booking's files on their own screen
    pending.firstOrNull { it.first.bookingId == openId }?.let { (d, files) ->
        androidx.activity.compose.BackHandler { openId = null }
        val listed = d.bookingId in extras.listed
        Column(Modifier.fillMaxSize().background(Vayu.colors.bg).safeDrawingPadding()) {
            androidx.compose.material3.IconButton(onClick = { openId = null }, modifier = Modifier.padding(start = 6.dp, top = 10.dp)) {
                androidx.compose.material3.Icon(androidx.compose.material.icons.Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back to Uploads", tint = Vayu.colors.ink)
            }
            Text(d.customer.ifBlank { d.code }, fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink, modifier = Modifier.padding(horizontal = 20.dp))
            Text(d.code + if (files.isEmpty()) "" else " · ${files.size} file${if (files.size == 1) "" else "s"} to send",
                color = Vayu.colors.muted, modifier = Modifier.padding(horizontal = 20.dp))
            var confirm by remember { mutableStateOf(false) }
            var send by remember { mutableStateOf(false) }
            val why = waitingFor(d, listed)
            (if (d.problemCode == JOB_CLOSED) d.problem else why)?.let {
                Text(it, color = if (d.problemCode == JOB_CLOSED || !listed) Vayu.colors.bad else Vayu.colors.muted,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp))
            }
            when {
                d.problemCode == JOB_CLOSED -> SoftButton("Discard draft", { confirm = true }, Modifier.padding(horizontal = 20.dp).fillMaxWidth(), color = Vayu.colors.bad)
                !d.submitSent && !listed -> Row(Modifier.padding(horizontal = 20.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    SoftButton("Discard draft", { confirm = true }, Modifier.weight(1f), color = Vayu.colors.bad)
                    if (d.startedAt != null && !d.locked) SoftButton("Send", { send = true }, Modifier.weight(1f))
                }
                !d.submitSent && d.submittedAt == null -> SoftButton("Open lead", { openId = null; onOpenLead(d.bookingId) },
                    Modifier.padding(horizontal = 20.dp).fillMaxWidth())
            }
            if (confirm) androidx.compose.material3.AlertDialog(onDismissRequest = { confirm = false },
                title = { Text("Discard ${d.code}?") },
                text = { Text("Its answers and photos on this phone are cleared. This cannot be undone.") },
                confirmButton = { androidx.compose.material3.TextButton({ confirm = false; extras.onDiscard(d.bookingId); openId = null; say("Draft discarded.") }) {
                    Text("Discard draft", color = Vayu.colors.bad) } },
                dismissButton = { androidx.compose.material3.TextButton({ confirm = false }) { Text("Keep it") } })
            if (send) androidx.compose.material3.AlertDialog(onDismissRequest = { send = false },
                title = { Text("Send ${d.code} as it is?") },
                text = { Text("The answers are locked and sent to Ops, who decide what happens with this lead.") },
                confirmButton = { androidx.compose.material3.TextButton({ send = false; extras.onSend(d.bookingId); say("Sending.") }) { Text("Send") } },
                dismissButton = { androidx.compose.material3.TextButton({ send = false }) { Text("Not now") } })
            LazyColumn(Modifier.weight(1f).padding(horizontal = 20.dp, vertical = 8.dp)) {
                items(files.size) { FileRow(files[it], onRemove = { extras.onRemoveFile(d, files[it]); say("File removed.") }) }
            }
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
                Text(if (pending.isEmpty()) "Everything is sent." else "${pending.size} lead${if (pending.size == 1) "" else "s"} not sent yet · $count file${if (count == 1) "" else "s"}",
                    color = Vayu.colors.muted, modifier = Modifier.padding(top = 12.dp, bottom = 10.dp))
                if (pending.isNotEmpty()) SoftField(query, { query = it }, "Booking ID, customer or phone",
                    icon = androidx.compose.material.icons.Icons.Outlined.Search)
            }
            items(shown.size, key = { shown[it].first.bookingId }) { i ->
                val (d, files) = shown[i]
                val failed = files.count { it.error != null }
                val why = waitingFor(d, d.bookingId in extras.listed)
                Column(Modifier.fillMaxWidth().clickable(role = androidx.compose.ui.semantics.Role.Button) { openId = d.bookingId }) {
                    Row(Modifier.fillMaxWidth().heightIn(min = 64.dp), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(d.code, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
                            Text(listOfNotNull(d.customer.ifBlank { null }, why, if (failed > 0) "$failed need you" else null).joinToString(" · "),
                                fontSize = 13.sp, color = if (failed > 0 || d.problemCode == JOB_CLOSED) Vayu.colors.bad else Vayu.colors.muted)
                        }
                        if (files.isNotEmpty()) Box(Modifier.clip(RoundedCornerShape(12.dp)).background(if (failed > 0) Vayu.colors.badTint else Vayu.colors.infoTint)
                            .padding(horizontal = 10.dp, vertical = 4.dp)) {
                            Text("${files.size}", fontWeight = FontWeight.Bold, color = if (failed > 0) Vayu.colors.bad else Vayu.colors.info)
                        }
                        androidx.compose.material3.Icon(androidx.compose.material.icons.Icons.Outlined.ChevronRight, null, tint = Vayu.colors.muted)
                    }
                    HorizontalDivider(color = Vayu.colors.line)
                }
            }
            if (pending.isNotEmpty() && shown.isEmpty()) item {
                Text("No lead matches \"$query\".", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 20.dp))
            }
        }
        ExpertBottomBar(ExpertTab.UPLOADS, uploads = count, onTab = { if (it == ExpertTab.JOBS) onJobs() }, onRefresh = onRefresh, refreshing = refreshing)
    }
}

@Composable
private fun FileRow(f: LocalFile, onRemove: () -> Unit) {
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
                f.sent -> Text("Sent · the server is checking it", fontSize = 13.sp, color = Vayu.colors.muted)
                f.progress > 0f -> Box(Modifier.padding(top = 6.dp).fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)).background(Vayu.colors.line)) {
                    Box(Modifier.fillMaxWidth(f.progress).height(4.dp).background(Vayu.colors.info))
                }
                else -> Text("Waiting", fontSize = 13.sp, color = Vayu.colors.muted)
            }
        }
        if (f.refused) androidx.compose.material3.TextButton(onRemove) { Text("Remove", color = Vayu.colors.bad) }
        else if (f.sent) Unit
        else if (f.progress > 0f && f.error == null) Text("${(f.progress * 100).toInt()}%", fontSize = 13.sp, color = Vayu.colors.muted)
        else if (f.error != null) Box(Modifier.size(8.dp).clip(CircleShape).background(Vayu.colors.bad))
    }
    HorizontalDivider(color = Vayu.colors.line)
}
