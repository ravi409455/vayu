package `in`.carcid.vayu.ui.ops

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.FilterList
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.core.ops.s
import `in`.carcid.vayu.ui.components.DatePick
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.ToggleChip
import `in`.carcid.vayu.ui.components.VayuSheet
import `in`.carcid.vayu.ui.theme.Vayu
import java.net.URLEncoder
import kotlinx.serialization.json.JsonObject
import `in`.carcid.vayu.core.ops.rows
import java.time.LocalDate

/**
 * The Bookings filters: one map shared by the quick row, the Filter view and Dashboard tiles.
 * "dates" is absent for today (the default), or "upcoming", "all", or "range" with date_from / date_to.
 * "expert" holds one id or several ("3,7").
 */
object BookingFilters {
    private val DATE_KEYS = setOf("dates", "date_from", "date_to")

    fun query(f: Map<String, String>, today: LocalDate): List<String> = buildList {
        when (f["dates"]) {
            null -> { add("date_from=$today"); add("date_to=$today") }
            "upcoming" -> add("date_from=${today.plusDays(1)}")
            "range" -> { f["date_from"]?.let { add("date_from=$it") }; f["date_to"]?.let { add("date_to=$it") } }
        }
        if (f["dates"] != "all") add("order=schedule")
        f.filterKeys { it !in DATE_KEYS }.forEach { (k, v) -> add("$k=" + URLEncoder.encode(v, "UTF-8")) }
    }

    /** A Dashboard tile's filters (date_from / date_to and more) as this map. */
    fun fromTile(tile: Map<String, String>) = if ("date_from" in tile || "date_to" in tile) tile + ("dates" to "range") else tile + ("dates" to "all")

    private fun day(s: String?) = s?.let { runCatching { LocalDate.parse(it) }.getOrNull() }

    fun dateWord(f: Map<String, String>): String = when (f["dates"]) {
        null -> "Today"
        "upcoming" -> "Upcoming"
        "all" -> "All dates"
        else -> {
            val a = day(f["date_from"]); val b = day(f["date_to"])
            when {
                a != null && b != null -> rangeLabel(a, b)
                a != null -> "From ${rangeLabel(a, a)}"
                b != null -> "Until ${rangeLabel(b, b)}"
                else -> "All dates"
            }
        }
    }

    /** How many filters are on: today's date is the default, so it doesn't count; an answer and its value count once. */
    fun count(f: Map<String, String>): Int = f.keys.count { it !in DATE_KEYS && it != "value" } + (if (f["dates"] != null) 1 else 0)

    /** A new type (or none) drops the answer: its questions belong to the old type. */
    fun withType(f: Map<String, String>, type: String?) = if (type == f["type"]) f else set(f, "type", type) - "answer" - "value"

    fun experts(f: Map<String, String>): Set<String> = f["expert"]?.split(",")?.filter { it.isNotBlank() }?.toSet().orEmpty()
    fun withExperts(f: Map<String, String>, ids: Set<String>) = if (ids.isEmpty()) f - "expert" else f + ("expert" to ids.sorted().joinToString(","))
    fun expertsWord(n: Int) = if (n == 1) "1 expert" else "$n experts"
    fun set(f: Map<String, String>, key: String, value: String?) = if (value == null) f - key else f + (key to value)

    /** "Today · In progress · 2 experts". */
    fun words(f: Map<String, String>, labels: Labels, answer: String? = null): List<String> = listOfNotNull(
        dateWord(f), f["stage"]?.let { STAGE_WORDS[it] }, f["timing"]?.let { if (it == "late") "Started late" else "Too quick" },
        f["type"]?.let(labels::type), f["city"]?.let(labels::city), experts(f).size.takeIf { it > 0 }?.let(::expertsWord), answer)

    /** The questions a type can be filtered by (choices and yes / no); none until a type is picked. */
    @Composable
    fun answerFields(env: OpsEnv, type: String?): List<JsonObject> =
        rememberLoad(env, if (type != null && env.can("submissions.view")) "bookings/answer-fields?type=" + URLEncoder.encode(type, "UTF-8") else null)
            .value?.data?.rows().orEmpty()
}

private fun expertOptions(labels: Labels) = labels.experts.map { it.s("id") to it.s("name").ifBlank { it.s("username") } }

/** One quick filter: dark when on, its value in words, "…" if it must shrink. */
@Composable
private fun QuickChip(text: String, on: Boolean, description: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Row(modifier.heightIn(min = 44.dp).clip(RoundedCornerShape(12.dp))
        .background(if (on) Vayu.colors.primary else Vayu.colors.bg)
        .border(1.dp, if (on) Vayu.colors.primary else Vayu.colors.line2, RoundedCornerShape(12.dp))
        .clickable(role = Role.Button, onClick = onClick).padding(start = 12.dp, end = 6.dp)
        .semantics { contentDescription = description },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(text, fontSize = 14.sp, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal, maxLines = 1, softWrap = false,
            overflow = TextOverflow.Ellipsis, color = if (on) Vayu.colors.onPrimary else Vayu.colors.ink, modifier = Modifier.weight(1f, fill = false))
        Icon(Icons.Outlined.ExpandMore, null, tint = if (on) Vayu.colors.onPrimary else Vayu.colors.muted, modifier = Modifier.size(16.dp))
    }
}

/** Status ▾ · Experts ▾ · Filter, always on one line; each change applies at once. */
@Composable
fun QuickFilters(f: Map<String, String>, labels: Labels, onChange: (Map<String, String>) -> Unit, onAll: () -> Unit) {
    var menu by remember { mutableStateOf(false) }
    var experts by remember { mutableStateOf(false) }
    val stage = f["stage"]
    val chosen = BookingFilters.experts(f)
    Row(Modifier.padding(top = 12.dp).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        // Status keeps its few words whole; only Experts gives way on a narrow screen
        Box {
            QuickChip(stage?.let { STAGE_WORDS[it] } ?: "Status", stage != null, "Status: ${stage?.let { STAGE_WORDS[it] } ?: "any"}") { menu = true }
            DropdownMenu(menu, { menu = false }, containerColor = Vayu.colors.bg) {
                (listOf<String?>(null) + STAGE_WORDS.keys).forEach { k ->
                    DropdownMenuItem(text = { Text(k?.let { STAGE_WORDS[it] } ?: "Any status", color = Vayu.colors.ink,
                        fontWeight = if (k == stage) FontWeight.SemiBold else FontWeight.Normal) },
                        trailingIcon = { if (k == stage) Icon(Icons.Outlined.Check, "Chosen", tint = Vayu.colors.ink) },
                        onClick = { menu = false; onChange(BookingFilters.set(f, "stage", k)) })
                }
            }
        }
        QuickChip(if (chosen.isEmpty()) "Experts" else BookingFilters.expertsWord(chosen.size), chosen.isNotEmpty(),
            "Experts: ${if (chosen.isEmpty()) "any" else "${chosen.size} chosen"}", Modifier.weight(1f, fill = false)) { experts = true }
        val n = BookingFilters.count(f)
        Row(Modifier.heightIn(min = 44.dp).widthIn(min = 44.dp).clip(RoundedCornerShape(12.dp))
            .background(if (n == 0) Vayu.colors.bg else Vayu.colors.primary)
            .border(1.dp, if (n == 0) Vayu.colors.line2 else Vayu.colors.primary, RoundedCornerShape(12.dp))
            .clickable(role = Role.Button, onClick = onAll).padding(horizontal = 8.dp)
            .semantics { contentDescription = if (n == 0) "All filters" else "All filters, $n on" },
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
            Icon(Icons.Outlined.FilterList, null, tint = if (n == 0) Vayu.colors.ink else Vayu.colors.onPrimary, modifier = Modifier.size(18.dp))
            if (n > 0) Text(" $n", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.onPrimary, maxLines = 1, softWrap = false)
        }
    }
    if (experts) ExpertsSheet(expertOptions(labels), chosen, { experts = false }) { onChange(BookingFilters.withExperts(f, it)) }
}

/** Pick several experts: tick boxes, a search when the list is long, Done says how many. */
@Composable
fun ExpertsSheet(options: List<Pair<String, String>>, chosen: Set<String>, onDismiss: () -> Unit, onDone: (Set<String>) -> Unit) {
    var draft by remember { mutableStateOf(chosen) }
    var find by remember { mutableStateOf("") }
    VayuSheet(onDismiss, footer = {
        Row(Modifier.padding(horizontal = 20.dp).padding(top = 8.dp, bottom = 20.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SoftButton("Any expert", { onDone(emptySet()); onDismiss() }, Modifier.weight(1f))
            PrimaryButton(if (draft.isEmpty()) "Done" else "Done · ${draft.size} chosen", { onDone(draft); onDismiss() }, Modifier.weight(1f))
        }
    }) {
        Text("Experts", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink, modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
        if (options.size > 8) Box(Modifier.padding(horizontal = 20.dp, vertical = 4.dp)) { SoftField(find, { find = it }, "Find an expert", icon = Icons.Outlined.Search) }
        options.filter { find.isBlank() || it.second.contains(find.trim(), ignoreCase = true) }.forEach { (id, name) ->
            val on = id in draft
            Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clickable(role = Role.Checkbox) { draft = if (on) draft - id else draft + id }
                .padding(horizontal = 20.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(22.dp).clip(RoundedCornerShape(6.dp)).background(if (on) Vayu.colors.primary else Vayu.colors.soft), contentAlignment = Alignment.Center) {
                    if (on) Icon(Icons.Outlined.Check, contentDescription = null, tint = Vayu.colors.onPrimary, modifier = Modifier.size(16.dp))
                }
                Text(name, color = Vayu.colors.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            }
        }
    }
}

/** Pick one, or "Any …" to take the filter off. */
@Composable
private fun PickSheet(title: String, any: String, options: List<Pair<String, String>>, value: String?, onDismiss: () -> Unit, onPick: (String?) -> Unit) =
    VayuSheet(onDismiss) {
        var find by remember { mutableStateOf("") }
        Text(title, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink, modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
        // a long list (a type's questions, cities) gets a find box, like Experts
        if (options.size > 8) Box(Modifier.padding(horizontal = 20.dp, vertical = 4.dp)) { SoftField(find, { find = it }, "Find", icon = Icons.Outlined.Search) }
        (listOf<Pair<String?, String>>(null to any) + options.filter { find.isBlank() || it.second.contains(find.trim(), ignoreCase = true) }).forEach { (k, label) ->
            Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clickable(role = Role.Button) { onDismiss(); onPick(k) }.padding(horizontal = 20.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(label, color = Vayu.colors.ink, modifier = Modifier.weight(1f), fontWeight = if (k == value) FontWeight.SemiBold else FontWeight.Normal)
                if (k == value) Icon(Icons.Outlined.Check, contentDescription = "Chosen", tint = Vayu.colors.ink)
            }
        }
        Spacer(Modifier.height(24.dp))
    }

/** Every filter looks the same: its name, then a grey box with the value (✕ takes it off) or "Any …". */
@Composable
fun FilterBox(label: String?, value: String?, any: String, modifier: Modifier = Modifier, onClear: (() -> Unit)? = null, onOpen: () -> Unit) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (label != null) Text(label, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.soft)
            .clickable(role = Role.Button, onClick = onOpen).padding(start = 14.dp, end = 4.dp)
            .semantics { contentDescription = "${label ?: any}: ${value ?: "any"}" },
            verticalAlignment = Alignment.CenterVertically) {
            Text(value ?: any, color = if (value == null) Vayu.colors.muted else Vayu.colors.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            if (value != null && onClear != null) Box(Modifier.size(44.dp).clip(CircleShape).clickable(role = Role.Button, onClick = onClear)
                .semantics { contentDescription = "Remove ${label ?: any}" }, contentAlignment = Alignment.Center) {
                Icon(Icons.Outlined.Close, null, tint = Vayu.colors.muted, modifier = Modifier.size(18.dp))
            }
            else Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.ExpandMore, null, tint = Vayu.colors.muted) }
        }
    }
}

/** The full Filter view: every filter, starting from what the quick row shows; applied with "Show bookings". */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FilterSheet(f: Map<String, String>, env: OpsEnv, onDismiss: () -> Unit, onApply: (Map<String, String>) -> Unit) {
    val labels = env.labels
    val today = env.today()
    var draft by remember { mutableStateOf(f) }
    val fields = BookingFilters.answerFields(env, draft["type"])
    val question = fields.firstOrNull { it.s("field") == draft["answer"] }
    var open by remember { mutableStateOf<String?>(null) }
    VayuSheet(onDismiss, footer = {
        Row(Modifier.padding(horizontal = 20.dp).padding(top = 8.dp, bottom = 20.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SoftButton("Cancel", onDismiss, Modifier.weight(1f))
            PrimaryButton("Show bookings", { onApply(if (draft["value"] == null) draft - "answer" else draft); onDismiss() }, Modifier.weight(1f))
        }
    }) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Filter", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Vayu.colors.ink, modifier = Modifier.weight(1f))
                Text("Clear all", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.info,
                    modifier = Modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button) { draft = emptyMap() }.padding(12.dp))
            }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Dates", fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(null to "Today", "upcoming" to "Upcoming", "all" to "All dates", "range" to "Pick dates").forEach { (k, label) ->
                        ToggleChip(label, draft["dates"] == k) {
                            draft = (draft - "date_from" - "date_to").let { if (k == null) it - "dates" else it + ("dates" to k) }
                            if (k == "range") open = "from"
                        }
                    }
                }
                if (draft["dates"] == "range") Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterBox(null, draft["date_from"]?.let { BookingFilters.dateWord(mapOf("dates" to "range", "date_from" to it, "date_to" to it)) }, "From",
                        Modifier.weight(1f)) { open = "from" }
                    FilterBox(null, draft["date_to"]?.let { BookingFilters.dateWord(mapOf("dates" to "range", "date_from" to it, "date_to" to it)) }, "To",
                        Modifier.weight(1f)) { open = "to" }
                }
            }
            FilterBox("Status", draft["stage"]?.let { STAGE_WORDS[it] }, "Any status", onClear = { draft = draft - "stage" }) { open = "stage" }
            val experts = BookingFilters.experts(draft)
            FilterBox("Experts", expertOptions(labels).filter { it.first in experts }.joinToString(", ") { it.second }.ifEmpty { null }, "Any expert",
                onClear = { draft = draft - "expert" }) { open = "expert" }
            FilterBox("Inspection type", draft["type"]?.let(labels::type), "Any type", onClear = { draft = BookingFilters.withType(draft, null) }) { open = "type" }
            // an answer only once a type is picked, from that type's questions only
            if (draft["type"] != null && fields.isNotEmpty()) {
                FilterBox("Answer", question?.s("label"), "Any question", onClear = { draft = draft - "answer" - "value" }) { open = "answer" }
                if (question != null) FilterBox(question.s("label"), draft["value"]?.let { v -> answerOptions(question).firstOrNull { it.first == v }?.second ?: v },
                    "Choose an answer", onClear = { draft = draft - "value" }) { open = "value" }
            }
            FilterBox("City", draft["city"]?.let(labels::city), "Any city", onClear = { draft = draft - "city" }) { open = "city" }
        }
    }
    when (open) {
        "from", "to" -> DatePick(draft["date_$open"]?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: today,
            if (open == "to") draft["date_from"]?.let { runCatching { LocalDate.parse(it) }.getOrNull() } else null,
            onPick = { d ->
                draft = draft + ("date_$open" to d.toString()) + ("dates" to "range")
                // a "To" before the "From" would show nothing: move it along
                if (open == "from" && draft["date_to"]?.let { it < d.toString() } == true) draft = draft + ("date_to" to d.toString())
                open = if (open == "from" && draft["date_to"] == null) "to" else null
            }, onDismiss = { open = null })
        "stage" -> PickSheet("Status", "Any status", STAGE_WORDS.toList(), draft["stage"], { open = null }) { draft = BookingFilters.set(draft, "stage", it) }
        "type" -> PickSheet("Inspection type", "Any type", labels.types.map { it.first to it.second }, draft["type"], { open = null }) { draft = BookingFilters.withType(draft, it) }
        "city" -> PickSheet("City", "Any city", labels.cities.toList(), draft["city"], { open = null }) { draft = BookingFilters.set(draft, "city", it) }
        "answer" -> PickSheet("Answer", "Any question", fields.map { it.s("field") to it.s("label") }, draft["answer"], { open = null }) {
            draft = (draft - "answer" - "value").let { m -> if (it == null) m else m + ("answer" to it) }
            if (it != null) open = "value"                                      // straight on to its answer
        }
        "value" -> question?.let { q -> PickSheet(q.s("label"), "Any answer", answerOptions(q), draft["value"], { open = null }) { draft = BookingFilters.set(draft, "value", it) } }
        "expert" -> ExpertsSheet(expertOptions(labels), BookingFilters.experts(draft), { open = null }) { draft = BookingFilters.withExperts(draft, it) }
    }
}

/** Today's status chips: "All 7", "Unassigned 1", …; a second tap goes back to All. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun StatusChips(counts: List<Pair<String?, Int>>, chosen: String?, onPick: (String?) -> Unit) {
    FlowRow(Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        counts.forEach { (k, n) ->
            val on = k == chosen
            val label = k?.let { STAGE_WORDS[it] } ?: "All"
            Row(Modifier.heightIn(min = 40.dp).clip(RoundedCornerShape(20.dp))
                .background(if (on) Vayu.colors.primary else Vayu.colors.bg)
                .border(1.dp, if (on) Vayu.colors.primary else Vayu.colors.line2, RoundedCornerShape(20.dp))
                .clickable(role = Role.Tab) { onPick(if (on) null else k) }.padding(horizontal = 12.dp)
                .semantics { contentDescription = "$label, $n${if (on) ", chosen" else ""}" },
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(label, fontSize = 14.sp, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal, maxLines = 1, softWrap = false,
                    color = if (on) Vayu.colors.onPrimary else Vayu.colors.ink)
                Text("$n", fontSize = 14.sp, maxLines = 1, softWrap = false, color = if (on) Vayu.colors.onPrimary else Vayu.colors.muted)
            }
        }
    }
}

