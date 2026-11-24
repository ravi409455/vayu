package `in`.carcid.vayu.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.ui.expert.time12
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId

/** One line in the bell (server: apps/notify). [booking] opens the job or booking. */
data class Note(val id: Long, val kind: String, val title: String, val body: String, val booking: String?,
                val at: OffsetDateTime?, val read: Boolean)

data class BellState(val notes: List<Note> = emptyList(), val unread: Int = 0, val loaded: Boolean = false)

fun parseNotes(o: JsonObject): BellState = BellState(
    notes = o["results"]?.jsonArray.orEmpty().map { it.jsonObject }.map { n ->
        fun s(k: String) = n[k]?.jsonPrimitive?.contentOrNull
        Note(n["id"]?.jsonPrimitive?.longOrNull ?: 0, s("kind").orEmpty(), s("title").orEmpty(), s("body").orEmpty(),
            s("booking"), s("created_at")?.let { runCatching { OffsetDateTime.parse(it) }.getOrNull() },
            n["read"]?.jsonPrimitive?.booleanOrNull ?: false)
    },
    unread = o["unread"]?.jsonPrimitive?.intOrNull ?: 0, loaded = true)

/**
 * The signed-in person's bell: the server's notices plus the phone's own (reminders, photos not
 * sending), read on open, on coming back to the app and on each push.
 */
class BellModel(private val api: Api, private val scope: CoroutineScope,
                /** The signed-in person's own phone notices (null: none). */
                private val localOf: () -> `in`.carcid.vayu.core.alerts.LocalNotes? = { null }) {
    private val _state = MutableStateFlow(BellState())
    val state: StateFlow<BellState> = _state
    private var server = BellState()

    fun refresh() {
        scope.launch {
            try { server = parseNotes(api.notifications()) } catch (_: ApiError) {}
            merge()
        }
    }

    private fun merge() {
        val mine = localOf()?.all().orEmpty().map { n ->
            Note(n.id, n.kind, n.title, n.body, n.booking, n.at.atOffset(java.time.ZoneOffset.UTC), n.read)
        }
        _state.value = BellState((server.notes + mine).sortedByDescending { it.at?.toInstant() },
            server.unread + mine.count { !it.read }, loaded = server.loaded || mine.isNotEmpty())
    }

    /** Marked read here at once; the server is told when it can be (a later refresh corrects it). */
    fun read(ids: List<Long>?) {
        val s = _state.value
        val gone = s.notes.filter { !it.read && (ids == null || it.id in ids) }
        if (gone.isEmpty()) return
        _state.value = s.copy(notes = s.notes.map { if (it in gone) it.copy(read = true) else it },
            unread = (s.unread - gone.size).coerceAtLeast(0))
        val phone = gone.filter { it.id < 0 }.map { it.id }
        if (phone.isNotEmpty()) localOf()?.read(if (ids == null) null else phone)
        val fromServer = gone.filter { it.id > 0 }.map { it.id }
        if (fromServer.isEmpty()) return
        scope.launch {
            try {
                val left = api.markRead(if (ids == null) null else fromServer)
                server = server.copy(unread = left, notes = server.notes.map { if (it.id in fromServer || ids == null) it.copy(read = true) else it })
                merge()
            } catch (_: ApiError) {}
        }
    }

    fun clear() { server = BellState(); _state.value = BellState() }
}

/** "Today" / "Yesterday" / "2 Dec" groups, newest first; tapping a line opens its job. */
fun LazyListScope.noteRows(notes: List<Note>, today: LocalDate, onOpen: (Note) -> Unit) {
    val zone = ZoneId.systemDefault()
    notes.groupBy { it.at?.atZoneSameInstant(zone)?.toLocalDate() }.forEach { (day, list) ->
        item(key = "d$day") {
            Text(when (day) { null -> "Earlier"; today -> "Today"; today.minusDays(1) -> "Yesterday"
                else -> "${day.dayOfMonth} ${day.month.name.take(3).lowercase().replaceFirstChar { it.uppercase() }}" }.uppercase(),
                fontSize = 12.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.7.sp, color = Vayu.colors.muted,
                modifier = Modifier.padding(top = 22.dp, bottom = 4.dp))
        }
        items(list, key = { it.id }) { n ->
            Row(Modifier.fillMaxWidth().heightIn(min = 64.dp).clickable(role = Role.Button) { onOpen(n) }.padding(vertical = 10.dp),
                verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.padding(top = 6.dp).size(8.dp).clip(CircleShape)
                    .background(if (n.read) Vayu.colors.bg else if (n.kind == "problem") Vayu.colors.bad else Vayu.colors.brand))
                Column(Modifier.weight(1f)) {
                    Text(n.title, fontWeight = if (n.read) FontWeight.Normal else FontWeight.SemiBold, color = Vayu.colors.ink,
                        maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (n.body.isNotBlank()) Text(n.body, fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                n.at?.atZoneSameInstant(zone)?.let { t ->
                    Text(time12("%02d:%02d".format(t.hour, t.minute)), fontSize = 12.sp, color = Vayu.colors.muted)
                }
            }
            HorizontalDivider(color = Vayu.colors.line)
        }
    }
}
