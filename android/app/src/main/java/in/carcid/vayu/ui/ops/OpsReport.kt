package `in`.carcid.vayu.ui.ops



import `in`.carcid.vayu.core.ops.Report
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.border
import `in`.carcid.vayu.ui.expert.whenStamp
import androidx.compose.runtime.LaunchedEffect
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.foundation.layout.height
import kotlinx.coroutines.delay
import kotlin.math.exp
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.ops.a
import `in`.carcid.vayu.core.ops.o
import `in`.carcid.vayu.core.s
import `in`.carcid.vayu.core.writeAtomically
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.File

/**
 * The PDF report on the booking screen. A change only marks it out of date; Ops press Regenerate
 * (the card says "Updating…" and checks again until it's done); Open · Share · Regenerate in one row. Opening downloads it through the
 * server (logged); sharing the PDF is logged too. The check link is printed in the PDF, so there
 * is no button for it here.
 */
@Composable
fun ReportCard(env: OpsEnv, id: String, b: Bk) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val r = rememberLoad(env, "bookings/$id/report")
    var rep by remember(r.value) { mutableStateOf(Report.from(r.value?.data)) }
    val online = r.value?.offline != true
    val updating = rep?.updating == true
    val outOfDate = rep?.outOfDate == true
    // the server says whether Regenerate can be pressed now, and why not
    val regen = rep?.regenerate
    var sending by remember { mutableStateOf(false) }
    // while a new revision is being made, look again every few seconds until it's done
    LaunchedEffect(updating, id) {
        while (rep?.updating == true) {
            kotlinx.coroutines.delay(4000)
            val now = try { Report.from(env.data.api.get("bookings/$id/report")) } catch (e: ApiError) { null } ?: continue
            rep = now
            if (!now.updating) env.refresh()
        }
    }
    // one download per revision: kept on the phone until a newer one is made
    suspend fun file(): File? {
        if (rep?.url.isNullOrBlank()) return null
        val code = b.code.filter { it.isLetterOrDigit() || it == '-' }
        val dir = File(ctx.cacheDir, "reports").apply { mkdirs() }
        // kept only under a real revision number and its time; without them, always a fresh download
        val rev = rep?.revision?.toString()
        val made = rep?.generatedAt.orEmpty().filter { it.isDigit() }
        // our own name, never the server's (no path tricks in the cache folder)
        val f = File(dir, if (rev != null && made.isNotEmpty()) "report-$code-$rev-$made.pdf" else "report-$code-latest.pdf")
        if (rev != null && made.isNotEmpty() && f.exists()) return f
        return withContext(Dispatchers.IO) {
            try {
                dir.listFiles { x -> x.name.startsWith("report-$code-") }?.forEach { it.delete() }
                writeAtomically(f, env.data.api.reportPdf(id)); f
            } catch (e: ApiError) { null }
        }
    }
    fun uriOf(f: File) = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
    // who passed the PDF on goes on the booking's history first; no record, no share
    suspend fun logShared(): Boolean = try {
        env.data.act("POST", "bookings/$id/report/shared", buildJsonObject { put("how", "pdf") }); true
    } catch (e: ApiError) { env.say("Couldn't record the share. Check the signal and try again."); false }
    Column(Modifier.padding(top = 8.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Vayu.colors.soft).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val failed = rep?.status == "failed"
        // a PDF is passed on only once the booking is Completed (every file in, or Ops finished it)
        val done = b.stage == "completed"
        // completed with no report at all (its first render was lost or had no layout): Ops make it (H-5)
        val missing = rep == null && r.error != null && b.stage == "completed" && b.conflict.isEmpty()
        Text(when {
            b.conflict.isNotEmpty() -> "Waits for your choice above"
            missing -> "Not made yet"
            b.stage != "completed" -> "No report yet"
            rep == null -> "Making the PDF…"
            updating || sending -> "Updating the PDF…"
            failed -> "Couldn't be made · tried again by itself"
            rep!!.status == "ready" -> (if (outOfDate) "Out of date" else "Ready") + (rep!!.generatedAt?.takeIf { it.isNotBlank() }?.let { " · made ${whenStamp(it, env.today()).replaceFirstChar { c -> c.lowercase() }}" } ?: "")
            else -> "Making the PDF…"
        }, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
        // a PDF is on its way (about 7 s): an estimated bar above the buttons
        val making = sending || updating || (done && b.conflict.isEmpty() && !missing && !failed && rep?.status != "ready")
        if (making) PdfProgress()
        if (failed && rep?.error?.isNotBlank() == true) Note(reportError(rep!!.error), Vayu.colors.badTint)
        if (missing) Note("The booking is completed but its PDF was not made. Make it now.", Vayu.colors.warnTint)
        if (outOfDate && !updating && done) Note("Something it shows changed since it was made. Regenerate it when you're done.", Vayu.colors.warnTint)
        // one row, to save space: Open · Share · Regenerate (each only when it applies)
        val hasFile = rep?.url?.isNotBlank() == true
        val canRegenerate = (rep != null || missing) && env.can("submissions.edit")
        val allowed = regen?.allowed == true || missing
        if (hasFile || canRegenerate) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (hasFile) CardButton("Open", Modifier.weight(1f), online && done) { scope.launch { file()?.let { ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uriOf(it), "application/pdf").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)) } ?: env.say("Couldn't download the report.") } }
            if (hasFile) CardButton("Share", Modifier.weight(1f), online && done) { scope.launch {
                file()?.let {
                    if (!logShared()) return@launch
                    ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("application/pdf")
                        .putExtra(Intent.EXTRA_STREAM, uriOf(it)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Share the report"))
                } ?: env.say("Couldn't download the report.")
            } }
            // F-219: reports are made again only when Ops press Regenerate (one tap, one request)
            if (canRegenerate) CardButton(if (sending || updating) "Making" else if (missing) "Make the PDF" else "Regenerate", Modifier.weight(1f), online && allowed && !sending && !updating) {
                sending = true
                env.actions.send("POST", "bookings/$id/report/regenerate", refused = { e -> env.say(e.message); sending = false }) {
                    scope.launch { try { rep = Report.from(env.data.api.get("bookings/$id/report")) ?: rep } catch (e: ApiError) { } finally { sending = false } }
                }
            }
        }
        if (done && canRegenerate && !allowed && regen?.reason?.isNotBlank() == true) Text(regen.reason, fontSize = 13.sp, color = Vayu.colors.muted)
    }
}

/** The PDF is being made and the server can't say how far along: the bar fills to 90% over the
 *  usual 7 s, then creeps on until the PDF arrives (web: PdfProgress). */
// ponytail: a fixed 7 s guess; measure real render times if they drift far from it
@Composable
private fun PdfProgress(seconds: Int = 7) {
    var elapsed by remember { mutableStateOf(0f) }
    LaunchedEffect(Unit) {
        val start = System.currentTimeMillis()
        while (true) { elapsed = (System.currentTimeMillis() - start) / 1000f; delay(250) }
    }
    val p = if (elapsed <= seconds) 0.9f * elapsed / seconds else 0.9f + 0.09f * (1f - exp(-(elapsed - seconds) / seconds))
    LinearProgressIndicator(progress = { p }, modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
        color = Vayu.colors.info, trackColor = Vayu.colors.line2, drawStopIndicator = {})
    Text(if (elapsed > seconds) "Taking longer than usual" else "Usually about $seconds seconds", fontSize = 13.sp, color = Vayu.colors.muted)
}

/** A button on a grey card: white with a border, one line. */
@Composable
private fun CardButton(text: String, modifier: Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    Box(modifier.heightIn(min = 48.dp).clip(RoundedCornerShape(12.dp)).background(Vayu.colors.bg)
        .border(1.dp, Vayu.colors.line2, RoundedCornerShape(12.dp)).clickable(enabled = enabled, role = Role.Button, onClick = onClick)
        .padding(horizontal = 6.dp), contentAlignment = Alignment.Center) {
        Text(text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
            color = if (enabled) Vayu.colors.ink else Vayu.colors.muted)
    }
}

@Composable
private fun Note(text: String, bg: Color) = Text(text, fontSize = 13.sp, color = Vayu.colors.ink2,
    modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(bg).padding(12.dp))

/** Why the last render failed, in words (the server sends a code). */
fun reportError(code: String): String = when (code) {
    "render_failed" -> "The PDF could not be made."
    "timeout" -> "Making it took too long."
    "storage_failed" -> "It could not be saved."
    else -> "It could not be made."
}
