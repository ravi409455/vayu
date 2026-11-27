package `in`.carcid.vayu

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import `in`.carcid.vayu.core.alerts.reminders
import `in`.carcid.vayu.core.alerts.stuck
import `in`.carcid.vayu.core.api.ApiError
import kotlinx.coroutines.async
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.File
import java.time.Duration
import java.time.Instant
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume

/** Notices on the phone: pushes from the server, job reminders, photos that won't send. */
object Notices {
    private const val JOBS = "jobs"
    private const val PROBLEMS = "problems"
    const val EXTRA_BOOKING = "booking"

    private fun channels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        // the name is the signed-in person's word (Settings shows it); the id never changes
        val ops = (ctx.applicationContext as? VayuApp)?.graph?.tokens?.me()?.get("role") == "ops"
        nm.createNotificationChannel(NotificationChannel(JOBS, if (ops) "Bookings and updates" else "Leads and updates", NotificationManager.IMPORTANCE_DEFAULT))
        nm.createNotificationChannel(NotificationChannel(PROBLEMS, "Problems", NotificationManager.IMPORTANCE_HIGH))
    }

    private const val FLAGS = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT

    /**
     * Show one notice; tapping it opens the app on [booking]. Silent if notices aren't allowed.
     * CarCID red with a car (problems: red with a warning sign). [body]'s first line shows folded,
     * all of it opened. [lead]: the expert's own lead, for Directions / Call / Open buttons.
     */
    fun show(ctx: Context, tag: String, title: String, body: String, booking: String?, problem: Boolean = false,
             lead: `in`.carcid.vayu.core.sync.Job? = null) {
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED &&
            android.os.Build.VERSION.SDK_INT >= 33) return
        channels(ctx)
        val channel = if (problem) PROBLEMS else JOBS
        val icon = if (problem) R.drawable.ic_notice_alert else R.drawable.ic_notice_car
        val color = ContextCompat.getColor(ctx, if (problem) R.color.notice_problem else R.color.brand)
        val open = PendingIntent.getActivity(ctx, tag.hashCode(), Intent(ctx, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .apply { if (!booking.isNullOrBlank()) putExtra(EXTRA_BOOKING, booking) }, FLAGS)
        val n = NotificationCompat.Builder(ctx, channel)
            .setSmallIcon(icon).setColor(color)
            .setContentTitle(title).setContentText(body.substringBefore('\n'))
            .apply { if (body.isNotBlank()) setStyle(NotificationCompat.BigTextStyle().bigText(body)) }
            .setCategory(if (problem) NotificationCompat.CATEGORY_ERROR else NotificationCompat.CATEGORY_EVENT)
            .setAutoCancel(true)
            // the lock screen shows the title, never the body: titles say what and when, never a
            // customer's name or address (the server words them so)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(NotificationCompat.Builder(ctx, channel).setSmallIcon(icon).setColor(color)
                .setContentTitle(lockTitle(title)).setContentText("Unlock to see the details.").build())
            .setContentIntent(open)
        if (lead != null) leadButtons(ctx, tag, lead).forEach { (label, intent) -> n.addAction(0, label, intent) }
        if (lead != null || (problem && !booking.isNullOrBlank())) n.addAction(0, if (problem) "Open booking" else "Open", open)
        runCatching { NotificationManagerCompat.from(ctx).notify(tag, 0, n.build()) }
    }

    /**
     * The title as the lock screen shows it: what and when, without the booking ID (F-075).
     * ponytail: titles end " · <ID>" and an ID has no spaces, a time always does ("Wed 14 Oct, 3:30 pm").
     */
    fun lockTitle(title: String): String {
        val last = title.substringAfterLast(" · ", "")
        return if (last.isNotEmpty() && last.none { it.isWhitespace() }) title.substringBeforeLast(" · ") else title
    }

    /** Directions and Call, as the lead page has them (digits only: a "*#06#" code never reaches the dialer). */
    internal fun leadButtons(ctx: Context, tag: String, j: `in`.carcid.vayu.core.sync.Job): List<Pair<String, PendingIntent>> {
        val place = listOf(j.address, j.city).filter { it.isNotBlank() }.joinToString(", ")
        val digits = j.phone.filter { it in '0'..'9' }
        fun view(key: String, intent: Intent) = PendingIntent.getActivity(ctx, "$tag-$key".hashCode(), intent, FLAGS)
        return listOfNotNull(
            if (place.isEmpty()) null else "Directions" to view("map", Intent(Intent.ACTION_VIEW,
                android.net.Uri.parse("https://www.google.com/maps/search/?api=1&query=" + java.net.URLEncoder.encode(place, "UTF-8")))),
            if (digits.isEmpty()) null else "Call" to view("call", Intent(Intent.ACTION_DIAL,
                android.net.Uri.parse("tel:" + (if (j.phone.trimStart().startsWith("+")) "+" else "") + digits))),
        )
    }

    /** This phone's push token (null without Google Play services or signal). */
    suspend fun token(): String? = suspendCancellableCoroutine { c ->
        runCatching {
            FirebaseMessaging.getInstance().token.addOnCompleteListener { t -> if (c.isActive) c.resume(if (t.isSuccessful) t.result else null) }
        }.onFailure { if (c.isActive) c.resume(null) }
    }
}

/** Pushes from the server. Each one is shown, and what it is about is fetched (a sync). */
class VayuMessaging : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        val graph = (application as VayuApp).graph
        if (graph.signedInId() == null) return             // sent at the next sign-in instead
        graph.sendPushToken()
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val graph = (application as VayuApp).graph
        if (graph.signedInId() == null) return
        // a push carries only the notice's id; its words are read with this phone's own sign-in,
        // so a push meant for someone else finds nothing and shows nothing
        val id = message.data["id"]?.toLongOrNull() ?: return
        val note = runCatching { kotlinx.coroutines.runBlocking { `in`.carcid.vayu.ui.parseNotes(graph.api.notifications()) } }
            .getOrNull()?.notes?.firstOrNull { it.id == id } ?: return
        val lead = if (note.kind == "assigned") runCatching { kotlinx.coroutines.runBlocking { leadFor(graph, note.booking) } }.getOrNull() else null
        Notices.show(this, "push-$id", note.title, note.body, note.booking, problem = note.kind == "problem", lead = lead)
        // the app is open: it refreshes now; closed: an expert's jobs are fetched so they're there offline
        if (!graph.pushed()) SyncWorker.enqueue(this)
    }
}

/** Download an expert's leads into the phone's store (as the app's own sync does). */
suspend fun syncJobs(graph: Graph, user: Int) {
    val store = graph.jobs(user)
    val keep = graph.pinned(user)
    store.apply(graph.api.syncJobs(store.haveVersions(), store.since(), keep), System.currentTimeMillis(),
        keep = keep, elapsed = android.os.SystemClock.elapsedRealtime())
}

/** How long a new-lead notice waits for the lead's details (its Directions / Call buttons). */
const val LEAD_WAIT_MS = 3_000L

/**
 * The signed-in expert's lead [booking], for a new-lead notice's buttons: from the phone's store, or
 * fetched once if the push came before the lead (null for Ops, offline, or a lead that isn't theirs).
 * The fetch waits at most [LEAD_WAIT_MS] (owner, 2026-11-27): on weak signal the notice still shows, without buttons.
 */
suspend fun leadFor(graph: Graph, booking: String?): `in`.carcid.vayu.core.sync.Job? {
    val user = graph.signedInId() ?: return null
    if (booking == null || graph.tokens.me()?.get("role") != "expert") return null
    fun find() = graph.jobs(user).jobs().firstOrNull { it.id == booking && it.assignedToMe }
    if (find() != null) return find()
    // the download can't be cut off midway (a blocking call), so the notice stops *waiting* after
    // 3 s while the download finishes on its own (it fills My leads either way)
    val download = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).async { syncJobs(graph, user) }
    return try { kotlinx.coroutines.withTimeoutOrNull(LEAD_WAIT_MS) { download.await(); find() } } catch (_: ApiError) { null }
}

/** Fetch an expert's jobs in the background (after a push), then set their reminders. */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as VayuApp).graph
        val user = graph.signedInId() ?: return Result.success()
        if (graph.tokens.me()?.get("role") != "expert") return Result.success()
        return try {
            syncJobs(graph, user)
            Reminders.schedule(applicationContext, graph, user)
            Result.success()
        } catch (e: ApiError) {
            if (e.code == ApiError.NETWORK) Result.retry() else Result.success()
        }
    }

    companion object {
        fun enqueue(ctx: Context) = WorkManager.getInstance(ctx).enqueueUniqueWork("sync", ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<SyncWorker>().setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build())
    }
}

/** Send this phone's push token to the server, retried until it gets there (offline at sign-in, server down). */
class PushTokenWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as VayuApp).graph
        if (graph.signedInId() == null) return Result.success()
        // no token yet (Play services starting): a few more tries; none at all on phones without them
        val token = Notices.token() ?: return if (runAttemptCount < 5) Result.retry() else Result.success()
        return try {
            graph.api.pushToken(token); Result.success()
        } catch (e: ApiError) {
            if (`in`.carcid.vayu.core.draft.transient(e) && e.code != "DEVICE_REVOKED") Result.retry() else Result.success()
        }
    }

    companion object {
        fun enqueue(ctx: Context) = WorkManager.getInstance(ctx).enqueueUniqueWork("push-token", ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<PushTokenWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(androidx.work.BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS).build())
    }
}

/**
 * "In 1 hour: DEMO-8 at 11:00", 60 min before each job not started yet. An alarm that may fire in
 * deep sleep (a delayed WorkManager job waits for the phone's next maintenance window: F-8).
 */
object Reminders {
    private const val TAG = "remind"
    private const val PREFS = "vayu.reminders"

    internal fun pending(ctx: Context, jobId: String, extras: Intent.() -> Unit = {}): PendingIntent =
        PendingIntent.getBroadcast(ctx, 0, Intent(ctx, ReminderReceiver::class.java)
            .setData(android.net.Uri.parse("vayu-remind:$jobId")).apply(extras),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    /** Set from the saved jobs: every earlier reminder is replaced (moved, cancelled, reassigned jobs). */
    fun schedule(ctx: Context, graph: Graph, user: Int) {
        cancel(ctx)
        val am = ctx.getSystemService(android.app.AlarmManager::class.java)
        val set = reminders(graph.jobs(user).jobs(), Instant.now()).map { r ->
            am.setAndAllowWhileIdle(android.app.AlarmManager.RTC_WAKEUP, r.at.toEpochMilli(), pending(ctx, r.jobId) {
                putExtra("job", r.jobId); putExtra("user", user); putExtra("title", r.title); putExtra("body", r.body)
            })
            r.jobId
        }
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putStringSet("set", set.toSet()).apply()
    }

    fun cancel(ctx: Context) {
        WorkManager.getInstance(ctx).cancelAllWorkByTag(TAG)          // set by older builds
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val am = ctx.getSystemService(android.app.AlarmManager::class.java)
        prefs.getStringSet("set", emptySet()).orEmpty().forEach { am.cancel(pending(ctx, it)) }
        prefs.edit().clear().apply()
    }
}

/**
 * Signed out: nothing of that person's stays (F-077). Notices off the screen, reminders cancelled and
 * their rows (customer, address) pruned from WorkManager, stuck-photo marks forgotten.
 */
fun forgetLeftovers(ctx: Context) {
    androidx.core.app.NotificationManagerCompat.from(ctx).cancelAll()
    Reminders.cancel(ctx)
    WorkManager.getInstance(ctx).pruneWork()
    ctx.getSharedPreferences("vayu.stuck", Context.MODE_PRIVATE).edit().clear().apply()
}

class ReminderReceiver : android.content.BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val job = intent.getStringExtra("job") ?: return
        val graph = (context.applicationContext as VayuApp).graph
        val owner = intent.getIntExtra("user", -1)
        if (graph.signedInId() != owner) return                  // only the person it was set for
        val title = intent.getStringExtra("title").orEmpty(); val body = intent.getStringExtra("body").orEmpty()
        graph.localNotes(owner).add("reminder", title, body, job)
        graph.pushed()                                       // an open bell shows it at once
        Notices.show(context, "remind-$job", title, body, job, lead = graph.jobs(owner).jobs().firstOrNull { it.id == job })
    }
}

/** After each send attempt: tell the expert once per job when its photos have been stuck for 2 hours. */
fun alertStuck(ctx: Context, graph: Graph, user: Int) {
    val prefs = ctx.getSharedPreferences("vayu.stuck", Context.MODE_PRIVATE)
    val told = prefs.getStringSet("told", emptySet()).orEmpty()
    val now = stuck(graph.drafts(user).all(), Instant.now()) { p -> File(p).takeIf { it.exists() }?.let { Instant.ofEpochMilli(it.lastModified()) } }
    now.filter { it.first !in told }.forEach { (id, code) ->
        val title = "Photos not sending · $code"; val body = "Stuck for 2 hours. Open the app on Wi-Fi to send them."
        graph.localNotes(user).add("problem", title, body, id)
        graph.pushed()
        Notices.show(ctx, "stuck-$id", title, body, id, problem = true)
    }
    prefs.edit().putStringSet("told", now.map { it.first }.toSet()).apply()   // sent ones can be told about again later
}
