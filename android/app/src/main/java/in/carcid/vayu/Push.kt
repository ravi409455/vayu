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

    /** Show one notice; tapping it opens the app on [booking]. Silent if notices aren't allowed. */
    fun show(ctx: Context, tag: String, title: String, body: String, booking: String?, problem: Boolean = false) {
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED &&
            android.os.Build.VERSION.SDK_INT >= 33) return
        channels(ctx)
        val open = Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .apply { if (!booking.isNullOrBlank()) putExtra(EXTRA_BOOKING, booking) }
        val n = NotificationCompat.Builder(ctx, if (problem) PROBLEMS else JOBS)
            .setSmallIcon(R.drawable.ic_notice)
            .setContentTitle(title).setContentText(body).setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            // the lock screen says a notice came, not whose car or where (customer name and address)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(NotificationCompat.Builder(ctx, if (problem) PROBLEMS else JOBS).setSmallIcon(R.drawable.ic_notice)
                .setContentTitle("Vayu").setContentText("New notice. Unlock to see it.").build())
            .setContentIntent(PendingIntent.getActivity(ctx, tag.hashCode(), open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(tag, 0, n) }
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
        Notices.show(this, "push-$id", note.title, note.body, note.booking, problem = note.kind == "problem")
        // the app is open: it refreshes now; closed: an expert's jobs are fetched so they're there offline
        if (!graph.pushed()) SyncWorker.enqueue(this)
    }
}

/** Fetch an expert's jobs in the background (after a push), then set their reminders. */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as VayuApp).graph
        val user = graph.signedInId() ?: return Result.success()
        if (graph.tokens.me()?.get("role") != "expert") return Result.success()
        return try {
            val store = graph.jobs(user)
            val keep = graph.pinned(user)
            store.apply(graph.api.syncJobs(store.haveVersions(), store.since(), keep), System.currentTimeMillis(),
                keep = keep, elapsed = android.os.SystemClock.elapsedRealtime())
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

/** "In 1 hour: DEMO-8 at 11:00", 60 min before each job not started yet. */
object Reminders {
    private const val TAG = "remind"

    /** Set from the saved jobs: every earlier reminder is replaced (moved, cancelled, reassigned jobs). */
    fun schedule(ctx: Context, graph: Graph, user: Int) {
        val wm = WorkManager.getInstance(ctx)
        wm.cancelAllWorkByTag(TAG)
        reminders(graph.jobs(user).jobs(), Instant.now()).forEach { r ->
            wm.enqueueUniqueWork("remind-${r.jobId}", ExistingWorkPolicy.REPLACE, OneTimeWorkRequestBuilder<ReminderWorker>()
                .addTag(TAG)
                .setInitialDelay(Duration.between(Instant.now(), r.at).toMillis().coerceAtLeast(0), TimeUnit.MILLISECONDS)
                .setInputData(workDataOf("job" to r.jobId, "user" to user, "title" to r.title, "body" to r.body)).build())
        }
    }

    fun cancel(ctx: Context) { WorkManager.getInstance(ctx).cancelAllWorkByTag(TAG) }
}

class ReminderWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val job = inputData.getString("job") ?: return Result.success()
        val graph = (applicationContext as VayuApp).graph
        val owner = inputData.getInt("user", -1)
        if (graph.signedInId() != owner) return Result.success()   // only the person it was set for
        val title = inputData.getString("title").orEmpty(); val body = inputData.getString("body").orEmpty()
        graph.localNotes(owner).add("reminder", title, body, job)
        graph.pushed()                                       // an open bell shows it at once
        Notices.show(applicationContext, "remind-$job", title, body, job)
        return Result.success()
    }
}

/** After each send attempt: tell the expert once per job when its photos have been stuck for 2 hours. */
fun alertStuck(ctx: Context, graph: Graph, user: Int) {
    val prefs = ctx.getSharedPreferences("vayu.stuck", Context.MODE_PRIVATE)
    val told = prefs.getStringSet("told", emptySet()).orEmpty()
    val now = stuck(graph.drafts(user).all(), Instant.now()) { p -> File(p).takeIf { it.exists() }?.let { Instant.ofEpochMilli(it.lastModified()) } }
    now.filter { it.first !in told }.forEach { (id, code) ->
        val title = "Photos for $code haven't sent for 2 hours"; val body = "Open the app on Wi-Fi to send them."
        graph.localNotes(user).add("problem", title, body, id)
        graph.pushed()
        Notices.show(ctx, "stuck-$id", title, body, id, problem = true)
    }
    prefs.edit().putStringSet("told", now.map { it.first }.toSet()).apply()   // sent ones can be told about again later
}
