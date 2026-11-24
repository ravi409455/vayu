package `in`.carcid.vayu.ui.ops

import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.components.Avatar
import `in`.carcid.vayu.core.ops.a
import `in`.carcid.vayu.core.ops.o
import kotlinx.serialization.json.JsonObject
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.semantics.Role
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.clickable
import android.content.Intent
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.IosShare
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.ops.s
import `in`.carcid.vayu.core.writeAtomically
import `in`.carcid.vayu.ui.components.Segmented
import `in`.carcid.vayu.ui.components.VayuTopBar
import `in`.carcid.vayu.ui.expert.SingleChoice
import `in`.carcid.vayu.core.forms.Option
import `in`.carcid.vayu.ui.theme.Vayu
import java.io.File
import java.time.LocalDate

private val SPLITS = listOf("type" to "Type", "city" to "City", "expert" to "Expert", "stage" to "Stage")
private val DAY = java.time.format.DateTimeFormatter.ofPattern("d MMM", java.util.Locale.ENGLISH)

/** "2026-W46" -> "9 Nov" (the week's Monday), "2026-11" -> "Nov 2026", "2026-11-24" -> "24 Nov". */
fun periodLabel(p: String): String = runCatching {
    val day = java.time.format.DateTimeFormatter.ofPattern("d MMM", java.util.Locale.ENGLISH)
    when {
        "-W" in p -> LocalDate.parse(p + "-1", java.time.format.DateTimeFormatter.ISO_WEEK_DATE).format(day)
        p.length == 7 -> java.time.YearMonth.parse(p).format(java.time.format.DateTimeFormatter.ofPattern("MMM yyyy", java.util.Locale.ENGLISH))
        else -> LocalDate.parse(p).format(day)
    }
}.getOrDefault(p)

/** The period chosen and the same length just before it: Today, the last 7 days, the last 30 days. */
fun dashPeriod(choice: Int, today: LocalDate): Pair<LocalDate, LocalDate> = when (choice) {
    0 -> today to today
    1 -> today.minusDays(6) to today
    else -> today.minusDays(29) to today
}

/** "17–23 Nov" (one day: "24 Nov"). */
fun rangeLabel(a: LocalDate, b: LocalDate): String =
    if (a == b) a.format(DAY) else if (a.month == b.month) "${a.dayOfMonth}–${b.format(DAY)}" else "${a.format(DAY)} – ${b.format(DAY)}"

/** The change against the period before, coloured by whether more is better. */
data class Change(val text: String, val good: Boolean?)

fun change(now: Double?, before: Double?, unit: String = "", moreIsBetter: Boolean = true): Change {
    if (now == null || before == null) return Change("—", null)
    val d = now - before
    if (kotlin.math.abs(d) < 0.5) return Change("same", null)
    val n = "%.0f".format(kotlin.math.abs(d))
    return Change("${if (d > 0) "↑" else "↓"} $n$unit", (d > 0) == moreIsBetter)
}

/**
 * The phone dashboard (approved prototype): Today / Week / Month; Bookings and On site tiles with
 * the change against the period before (each opens the matching bookings); bookings per day;
 * a split by type, city, expert or stage; experts with their problems.
 */
@Composable
fun DashboardScreen(env: OpsEnv, needs: Int, onBell: () -> Unit, onProfile: () -> Unit, onOpenList: (Map<String, String>) -> Unit,
                    bottomBar: @Composable () -> Unit) {
    val ctx = LocalContext.current
    var choice by rememberSaveable { mutableStateOf(1) }
    var split by rememberSaveable { mutableStateOf("type") }
    var allExperts by rememberSaveable { mutableStateOf(false) }
    val (from, to) = dashPeriod(choice, env.today())
    val days = java.time.temporal.ChronoUnit.DAYS.between(from, to) + 1
    val load = rememberLoad(env, "dashboards/summary?date_from=$from&date_to=$to")
    val sum = load.value?.data as? JsonObject
    val now = sum?.o("period"); val before = sum?.o("previous")
    val perDay = rememberLoad(env, if (choice == 0) null else "dashboards/volume?group=${if (choice == 1) "day" else "week"}&by=stage&date_from=$from&date_to=$to")
        .value?.data?.rows().orEmpty()
    val splitRows = rememberLoad(env, "dashboards/volume?group=month&by=$split&date_from=$from&date_to=$to").value?.data?.rows().orEmpty()
    val dates = mapOf("date_from" to from.toString(), "date_to" to to.toString())
    // started late / too quick only for those who may see timing flags (the server leaves them out too)
    val timing = env.can("bookings.review_timing")
    fun num(o: JsonObject?, k: String) = o?.s(k)?.toDoubleOrNull()
    fun label(k: String) = when (split) {
        "type" -> env.labels.type(k); "city" -> env.labels.city(k); "expert" -> env.labels.person(k.toIntOrNull()).ifBlank { "Unassigned" }
        else -> STAGE_WORDS[k] ?: k
    }.ifBlank { "—" }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        VayuTopBar("Dashboard", env.me.initials, bellCount = needs, onBell = onBell, onProfile = onProfile) {
            if (env.can("dashboards.export")) IconButton(onClick = {
                val f = File(File(ctx.cacheDir, "reports").apply { mkdirs() }, "vayu-$from-$to-by-$split.csv")
                writeAtomically(f, ("$split,count\n" + splitRows.groupBy { it.s("key") }.map { (k, r) -> k to r.sumOf { it.s("count").toIntOrNull() ?: 0 } }
                    .sortedByDescending { it.second }.joinToString("\n") { (k, n) ->
                        listOf(label(k), "$n").joinToString(",") { v -> "\"" + v.replace("\"", "\"\"").let { if (it.firstOrNull() in setOf('=', '+', '-', '@', '\t', '\r', '\n')) "'$it" else it } + "\"" }
                    }).toByteArray())
                val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
                ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/csv").putExtra(Intent.EXTRA_STREAM, uri)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Share the numbers"))
            }) { Icon(Icons.Outlined.IosShare, contentDescription = "Share as a spreadsheet", tint = Vayu.colors.ink) }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            OfflineNote(load.value)
            Spacer(Modifier.height(12.dp))
            Segmented(listOf("Today", "Week", "Month"), choice, { choice = it; allExperts = false })
            Text("${rangeLabel(from, to)} · vs ${rangeLabel(from.minusDays(days), from.minusDays(1))}", fontSize = 13.sp, color = Vayu.colors.muted,
                modifier = Modifier.padding(top = 8.dp))
            if (sum == null) { Text(load.error ?: "Loading…", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 20.dp)); return@Column }

            Section("Bookings")
            Tiles(listOf(
                TileData("Bookings", "${now?.s("bookings")}", change(num(now, "bookings"), num(before, "bookings"))) { onOpenList(dates) },
                TileData("Completed", "${now?.s("completed")}", change(num(now, "completed"), num(before, "completed"))) { onOpenList(dates + ("stage" to "completed")) },
                TileData("Completion", num(now, "completion_rate")?.let { "${it.toInt()}%" } ?: "—",
                    change(num(now, "completion_rate"), num(before, "completion_rate"), " pts")) { onOpenList(dates + ("stage" to "completed")) },
                TileData("Cancelled", "${now?.s("cancelled")}", change(num(now, "cancelled"), num(before, "cancelled"), moreIsBetter = false)) { onOpenList(dates + ("stage" to "cancelled")) },
            ))
            Section("On site")
            Tiles(listOf(
                TileData("Avg time", num(now, "avg_minutes")?.let { fmtMinutes(it.toInt()) } ?: "—",
                    change(num(now, "avg_minutes"), num(before, "avg_minutes"), " min").copy(good = null)) { onOpenList(dates + ("stage" to "completed")) },
            ) + if (!timing) emptyList() else listOf(
                TileData("On time", num(now, "on_time")?.let { "${it.toInt()}%" } ?: "—", change(num(now, "on_time"), num(before, "on_time"), " pts")) { onOpenList(dates) },
                TileData("Started late", "${now?.s("late")}", change(num(now, "late"), num(before, "late"), moreIsBetter = false),
                    bad = (num(now, "late") ?: 0.0) > 0) { onOpenList(dates + ("timing" to "late")) },
                TileData("Too quick", "${now?.s("quick")}", change(num(now, "quick"), num(before, "quick"), moreIsBetter = false),
                    bad = (num(now, "quick") ?: 0.0) > 0) { onOpenList(dates + ("timing" to "quick")) },
            ))

            if (choice != 0) {
                Section(if (choice == 1) "Bookings per day" else "Bookings per week")
                val totals = perDay.groupBy { it.s("period") }.map { (p, r) -> p to r.sumOf { it.s("count").toIntOrNull() ?: 0 } }.sortedBy { it.first }
                // every day of the week shows, a quiet one as 0
                val bars = if (choice == 1) (0 until 7).map { i -> from.plusDays(i.toLong()).let { d -> d.dayOfWeek.name.take(3).lowercase().replaceFirstChar { it.uppercase() } to (totals.firstOrNull { it.first == d.toString() }?.second ?: 0) } }
                    else totals.map { periodLabel(it.first) to it.second }
                Bars(bars)
            }

            Section("Split by")
            SingleChoice("Split by", SPLITS.map { Option(it.first, it.second, false, null) }, split, false, { if (it != null) split = it as String })
            val parts = splitRows.groupBy { it.s("key") }.map { (k, r) -> k to r.sumOf { it.s("count").toIntOrNull() ?: 0 } }.sortedByDescending { it.second }
            val total = parts.sumOf { it.second }.coerceAtLeast(1); val top = (parts.maxOfOrNull { it.second } ?: 0).coerceAtLeast(1)
            Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                parts.forEach { (k, n) ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(label(k), color = Vayu.colors.ink, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                            Text("$n", fontWeight = FontWeight.Bold, color = Vayu.colors.ink, fontSize = 14.sp)
                            Text("${100 * n / total}%", color = Vayu.colors.muted, fontSize = 13.sp, modifier = Modifier.widthIn(min = 36.dp))
                        }
                        Box(Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)).background(Vayu.colors.line)) {
                            Box(Modifier.fillMaxWidth(n.toFloat() / top).height(8.dp).clip(RoundedCornerShape(4.dp)).background(Vayu.colors.ink))
                        }
                    }
                }
                if (parts.isEmpty()) Text("Nothing in this period yet.", color = Vayu.colors.muted)
            }

            val experts = sum.a("by_expert").map { it as JsonObject }
            if (experts.isNotEmpty()) {
                Section("By expert")
                (if (allExperts) experts else experts.take(5)).forEach { e ->
                    val id = e.int("expert"); val name = env.labels.person(id)
                    Row(Modifier.fillMaxWidth().heightIn(min = 60.dp).clickable(role = Role.Button) { onOpenList(dates + ("expert" to "$id")) }.padding(vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Avatar(name.split(" ").filter { it.isNotBlank() }.take(2).joinToString("") { it.take(1).uppercase() }, size = 36)
                        Column(Modifier.weight(1f)) {
                            Text(name, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(listOfNotNull("${e.s("bookings")} job${if (e.s("bookings") == "1") "" else "s"}", e.s("on_time").ifBlank { null }?.let { "$it% on time" })
                                .joinToString(" · "), fontSize = 13.sp, color = Vayu.colors.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        if (timing) {
                            e.int("late")?.takeIf { it > 0 }?.let { Badge("$it late") }
                            e.int("quick")?.takeIf { it > 0 }?.let { Badge("$it quick") }
                        }
                    }
                    HorizontalDivider(color = Vayu.colors.line)
                }
                if (experts.size > 5) SoftButton(if (allExperts) "Show fewer" else "Show all ${experts.size} experts", { allExperts = !allExperts },
                    Modifier.fillMaxWidth().padding(top = 8.dp))
            }
            Spacer(Modifier.height(24.dp))
        }
        bottomBar()
    }
}

private class TileData(val label: String, val value: String, val change: Change, val bad: Boolean = false, val onClick: () -> Unit)

/** Two tiles a row; a red one is a problem. Each opens the bookings behind its number. */
@Composable
private fun Tiles(tiles: List<TileData>) = Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
    tiles.chunked(2).forEach { row ->
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            row.forEach { t ->
                Column(Modifier.weight(1f).heightIn(min = 92.dp).clip(RoundedCornerShape(14.dp)).background(if (t.bad) Vayu.colors.badTint else Vayu.colors.soft)
                    .clickable(role = Role.Button, onClick = t.onClick).padding(horizontal = 14.dp, vertical = 12.dp)
                    .semantics(mergeDescendants = true) {}, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(t.label, fontSize = 13.sp, color = if (t.bad) Vayu.colors.bad else Vayu.colors.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(t.value, fontSize = 26.sp, lineHeight = 30.sp, fontWeight = FontWeight.Bold, color = if (t.bad) Vayu.colors.bad else Vayu.colors.ink, maxLines = 1)
                    Text(t.change.text, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1,
                        color = when (t.change.good) { true -> Vayu.colors.ok; false -> Vayu.colors.bad; null -> Vayu.colors.muted })
                }
            }
            if (row.size == 1) Spacer(Modifier.weight(1f))
        }
    }
}

/** Plain bars with their counts above and labels below; the last (now) is dark. */
@Composable
private fun Bars(bars: List<Pair<String, Int>>) {
    val top = (bars.maxOfOrNull { it.second } ?: 0).coerceAtLeast(1)
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Vayu.colors.soft).padding(14.dp)
        .semantics { contentDescription = "Bookings: " + bars.joinToString { "${it.first} ${it.second}" } }) {
        Row(Modifier.fillMaxWidth().height(120.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Bottom) {
            bars.forEachIndexed { i, (_, n) ->
                Column(Modifier.weight(1f).fillMaxHeight(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Bottom) {
                    Text("$n", fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink2)
                    Box(Modifier.padding(top = 4.dp).fillMaxWidth().fillMaxHeight(0.82f * n / top + 0.02f).clip(RoundedCornerShape(5.dp))
                        .background(if (i == bars.lastIndex) Vayu.colors.ink else Vayu.colors.line2))
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            bars.forEach { (l, _) -> Text(l, fontSize = 11.sp, color = Vayu.colors.muted, textAlign = TextAlign.Center, maxLines = 1, modifier = Modifier.weight(1f)) }
        }
    }
}

@Composable
private fun Badge(text: String) = Text(text, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Vayu.colors.bad, maxLines = 1, softWrap = false,
    modifier = Modifier.clip(RoundedCornerShape(11.dp)).background(Vayu.colors.badTint).padding(horizontal = 8.dp, vertical = 2.dp))
