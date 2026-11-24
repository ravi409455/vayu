package `in`.carcid.vayu.ui.ops

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

private val GROUPS = listOf("day", "week", "month")
private val SPLITS = listOf("type" to "Type", "city" to "City", "expert" to "Expert", "stage" to "Stage")

/** How many periods back the chart shows, and the first day of that range. */
/** "2026-W46" -> "9 Nov" (the week's Monday), "2026-11" -> "Nov 2026", "2026-11-24" -> "24 Nov". */
fun periodLabel(p: String): String = runCatching {
    val day = java.time.format.DateTimeFormatter.ofPattern("d MMM", java.util.Locale.ENGLISH)
    when {
        "-W" in p -> LocalDate.parse(p + "-1", java.time.format.DateTimeFormatter.ISO_WEEK_DATE).format(day)
        p.length == 7 -> java.time.YearMonth.parse(p).format(java.time.format.DateTimeFormatter.ofPattern("MMM yyyy", java.util.Locale.ENGLISH))
        else -> LocalDate.parse(p).format(day)
    }
}.getOrDefault(p)

fun dashRange(group: String, today: LocalDate): Pair<LocalDate, LocalDate> = when (group) {
    "day" -> today.minusDays(13) to today
    "week" -> today.minusWeeks(7).with(java.time.DayOfWeek.MONDAY) to today
    else -> today.minusMonths(5).withDayOfMonth(1) to today
}

/** One period chosen (day, week, month), one chart, one split, CSV to share. */
@Composable
fun DashboardScreen(env: OpsEnv, needs: Int, onBell: () -> Unit, onProfile: () -> Unit, bottomBar: @Composable () -> Unit) {
    val ctx = LocalContext.current
    var group by rememberSaveable { mutableStateOf(1) }
    var split by rememberSaveable { mutableStateOf("type") }
    val g = GROUPS[group]
    val (from, to) = dashRange(g, env.today())
    val load = rememberLoad(env, "dashboards/volume?group=$g&by=$split&date_from=$from&date_to=$to")
    val rows = load.value?.data?.rows().orEmpty()
    val periods = rows.map { it.s("period") }.distinct().sorted()
    val totals = periods.map { p -> p to rows.filter { it.s("period") == p }.sumOf { it.s("count").toIntOrNull() ?: 0 } }
    val now = totals.lastOrNull()?.second ?: 0
    val before = totals.dropLast(1).lastOrNull()?.second ?: 0
    val word = listOf("today", "this week", "this month")[group]
    val last = periods.lastOrNull()
    val byKey = rows.filter { it.s("period") == last }.map { it.s("key") to (it.s("count").toIntOrNull() ?: 0) }.sortedByDescending { it.second }
    fun label(k: String) = when (split) {
        "type" -> env.labels.type(k); "city" -> env.labels.city(k); "expert" -> env.labels.person(k.toIntOrNull()).ifBlank { "Not assigned" }
        else -> mapOf("draft" to "Unassigned", "assigned" to "To start", "in_progress" to "On site", "submitted" to "Uploading", "completed" to "Done", "cancelled" to "Cancelled")[k] ?: k
    }.ifBlank { "—" }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        VayuTopBar("Dashboard", env.me.initials, bellCount = needs, onBell = onBell, onProfile = onProfile) {
            if (env.can("dashboards.export")) IconButton(onClick = {
                val f = File(File(ctx.cacheDir, "reports").apply { mkdirs() }, "vayu-$g-by-$split.csv")
                writeAtomically(f, ("period,${split},count\n" + rows.joinToString("\n") { r ->
                    listOf(periodLabel(r.s("period")), label(r.s("key")), r.s("count")).joinToString(",") { v -> "\"" + v.replace("\"", "\"\"").let { if (it.firstOrNull() in setOf('=', '+', '-', '@')) "'$it" else it } + "\"" }
                }).toByteArray())
                val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
                ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/csv").putExtra(Intent.EXTRA_STREAM, uri)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Share the numbers"))
            }) { Icon(Icons.Outlined.IosShare, contentDescription = "Share as a spreadsheet (CSV)", tint = Vayu.colors.ink) }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            OfflineNote(load.value)
            Spacer(Modifier.height(12.dp))
            Segmented(listOf("Day", "Week", "Month"), group, { group = it })
            Row(Modifier.padding(top = 18.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("$now", fontSize = 34.sp, fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
                Text("inspections $word", color = Vayu.colors.muted, modifier = Modifier.padding(bottom = 6.dp))
            }
            val diff = now - before
            Text(when { diff > 0 -> "↑ $diff more than before"; diff < 0 -> "↓ ${-diff} fewer than before"; else -> "Same as before" },
                color = if (diff >= 0) Vayu.colors.ok else Vayu.colors.warn, fontSize = 14.sp)
            val max = (totals.maxOfOrNull { it.second } ?: 0).coerceAtLeast(1)
            val bar = Vayu.colors.ink; val soft = Vayu.colors.line2
            Canvas(Modifier.padding(top = 18.dp).fillMaxWidth().height(160.dp)
                .semantics { contentDescription = "Inspections per $g: " + totals.joinToString { "${periodLabel(it.first)} ${it.second}" } }) {
                if (totals.isEmpty()) return@Canvas
                val w = size.width / totals.size
                totals.forEachIndexed { i, (_, n) ->
                    val h = size.height * n / max
                    drawRoundRect(if (i == totals.lastIndex) bar else soft, Offset(i * w + w * 0.15f, size.height - h), Size(w * 0.7f, h), CornerRadius(6f))
                }
            }
            Row(Modifier.fillMaxWidth().padding(top = 6.dp)) {
                Text(periods.firstOrNull()?.let(::periodLabel).orEmpty(), fontSize = 12.sp, color = Vayu.colors.muted, modifier = Modifier.weight(1f))
                Text(periods.lastOrNull()?.let(::periodLabel).orEmpty(), fontSize = 12.sp, color = Vayu.colors.muted)
            }
            Row(Modifier.padding(top = 22.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("${word.replaceFirstChar { it.uppercase() }} by", fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink, modifier = Modifier.weight(1f))
            }
            SingleChoice("Split by", SPLITS.map { Option(it.first, it.second, false, null) }, split, false, { if (it != null) split = it as String })
            val colors = listOf(Vayu.colors.ink, Vayu.colors.info, Vayu.colors.ok, Vayu.colors.warn, Vayu.colors.brand)
            byKey.forEachIndexed { i, (k, n) ->
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.size(10.dp).clip(CircleShape).background(colors[i % colors.size]))
                    Text(label(k), color = Vayu.colors.ink, modifier = Modifier.weight(1f))
                    Text("$n", fontWeight = FontWeight.Bold, color = Vayu.colors.ink)
                }
                HorizontalDivider(color = Vayu.colors.line)
            }
            if (load.value != null && byKey.isEmpty()) Text("Nothing in this period yet.", color = Vayu.colors.muted, modifier = Modifier.padding(vertical = 16.dp))
            Spacer(Modifier.height(24.dp))
        }
        bottomBar()
    }
}
