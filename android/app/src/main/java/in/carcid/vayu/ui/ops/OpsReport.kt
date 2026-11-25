package `in`.carcid.vayu.ui.ops



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
import androidx.compose.material3.Text
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
 * The PDF report on the booking screen. It updates by itself after any change (the card says
 * "Updating…" and checks again until it's done); Open · Share · Check link. Opening downloads it
 * through the server (logged); sharing the PDF or the check link is logged too.
 */
@Composable
fun ReportCard(env: OpsEnv, id: String, b: Bk) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val r = rememberLoad(env, "bookings/$id/report")
    var rep by remember(r.value) { mutableStateOf(r.value?.data as? JsonObject) }
    val online = r.value?.offline != true
    val updating = rep?.s("updating") == "true"
    val outOfDate = rep?.s("out_of_date") == "true"
    // the server says whether Regenerate can be pressed now, and why not
    val regen = rep?.o("regenerate")
    var sending by remember { mutableStateOf(false) }
    // while a new revision is being made, look again every few seconds until it's done
    LaunchedEffect(updating, id) {
        while (rep?.s("updating") == "true") {
            kotlinx.coroutines.delay(4000)
            val now = try { env.data.api.get("bookings/$id/report") as? JsonObject } catch (e: ApiError) { null } ?: continue
            rep = now
            if (now.s("updating") != "true") env.refresh()
        }
    }
    // one download per revision: kept on the phone until a newer one is made
    suspend fun file(): File? {
        if (rep?.s("url").isNullOrBlank()) return null
        val code = b.code.filter { it.isLetterOrDigit() || it == '-' }
        val dir = File(ctx.cacheDir, "reports").apply { mkdirs() }
        // kept only under a real revision number and its time; without them, always a fresh download
        val rev = rep?.s("revision")?.takeIf { it.isNotBlank() && it.all(Char::isDigit) }
        val made = rep?.s("generated_at").orEmpty().filter { it.isDigit() }
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
    // who passed it on, and how, goes on the booking's history first; no record, no share
    suspend fun logShared(how: String): Boolean = try {
        env.data.act("POST", "bookings/$id/report/shared", buildJsonObject { put("how", how) }); true
    } catch (e: ApiError) { env.say("Couldn't record the share. Check the signal and try again."); false }
    Column(Modifier.padding(top = 8.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Vayu.colors.soft).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val failed = rep?.s("status") == "failed"
        Text(when {
            b.conflict.isNotEmpty() -> "Waits for your choice above"
            rep == null -> if (b.stage == "completed") "Being made" else "Made when the booking is completed"
            updating -> "Updating…"
            failed -> "Couldn't be made · tried again by itself"
            rep!!.s("status") == "ready" -> (if (outOfDate) "Out of date" else "Ready") + (rep!!.s("generated_at").takeIf { it.isNotBlank() }?.let { " · made ${whenStamp(it, env.today()).replaceFirstChar { c -> c.lowercase() }}" } ?: "")
            else -> "Being made"
        }, fontWeight = FontWeight.SemiBold, color = Vayu.colors.ink)
        if (failed && rep?.s("error")?.isNotBlank() == true) Note(rep!!.s("error"), Vayu.colors.badTint)
        if (outOfDate && !updating) Note("Something it shows changed since it was made. Regenerate it when you're done.", Vayu.colors.warnTint)
        if (rep?.s("url")?.isNotBlank() == true) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CardButton("Open", Modifier.weight(1f), online) { scope.launch { file()?.let { ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uriOf(it), "application/pdf").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)) } ?: env.say("Couldn't download the report.") } }
            CardButton("Share", Modifier.weight(1f), online) { scope.launch {
                file()?.let {
                    if (!logShared("pdf")) return@launch
                    ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("application/pdf")
                        .putExtra(Intent.EXTRA_STREAM, uriOf(it)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Share the report"))
                } ?: env.say("Couldn't download the report.")
            } }
            if (rep!!.s("verify_url").isNotBlank()) CardButton("Check link", Modifier.weight(1f), online) { scope.launch {
                if (!logShared("check_link")) return@launch
                ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, rep!!.s("verify_url")), "Share the check link"))
            } }
        }
        // F-219: reports are made again only when Ops press Regenerate (one tap, one request)
        if (rep != null && env.can("submissions.edit")) {
            val allowed = regen?.s("allowed") == "true"
            CardButton(if (sending) "Regenerating…" else "Regenerate", Modifier.fillMaxWidth(), online && allowed && !sending) {
                sending = true
                scope.launch {
                    try {
                        env.data.act("POST", "bookings/$id/report/regenerate")
                        rep = (env.data.api.get("bookings/$id/report") as? JsonObject) ?: rep
                    } catch (e: ApiError) { env.say(e.message) } finally { sending = false }
                }
            }
            if (!allowed && regen?.s("reason")?.isNotBlank() == true) Text(regen.s("reason"), fontSize = 13.sp, color = Vayu.colors.muted)
        }
    }
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
