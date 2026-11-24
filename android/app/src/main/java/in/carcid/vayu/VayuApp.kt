package `in`.carcid.vayu

import android.app.Application
import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.auth.PrefsTokenStore
import `in`.carcid.vayu.core.auth.TokenStore
import `in`.carcid.vayu.core.draft.DraftStore
import `in`.carcid.vayu.core.draft.Outbox
import `in`.carcid.vayu.core.sync.JobStore
import java.io.File
import java.time.LocalDate
import java.util.concurrent.TimeUnit

/** What the screens and the background sender share: one sign-in, one API, each person's files. */
class Graph(val api: Api, val tokens: TokenStore, private val root: File,
            /** Ask for the outbox to run (WorkManager in the app, directly in tests). */
            val kick: () -> Unit,
            /** Where downloaded photos, reports and spreadsheets are kept for viewing. */
            private val cache: File? = null,
            /** An expert's jobs were saved fresh: set their reminders (WorkManager in the app). */
            val onJobs: (Int) -> Unit = {},
            /** Signed out: take this person's notices off the phone and drop their reminders. */
            val clearNotices: () -> Unit = {}) {
    /** The phone's own notices (reminders, photos not sending), shown in the bell with the server's. */
    val localNotes = `in`.carcid.vayu.core.alerts.LocalNotes(File(root, "notes.json"))

    /** A push arrived; the open app listens and refreshes at once. */
    val pushes = kotlinx.coroutines.flow.MutableSharedFlow<Unit>(extraBufferCapacity = 1)

    /** Tell the open app about a push; false when no screen is listening (the app is closed). */
    fun pushed(): Boolean = pushes.subscriptionCount.value > 0 && pushes.tryEmit(Unit)

    private val jobStores = HashMap<Int, JobStore>()
    private val draftStores = HashMap<Int, DraftStore>()

    @Synchronized fun jobs(userId: Int) = jobStores.getOrPut(userId) { JobStore(File(root, "jobs-$userId.json")) }
    @Synchronized fun drafts(userId: Int) = draftStores.getOrPut(userId) { DraftStore(File(root, "drafts-$userId")) }

    /** Ops' saved copies of what they last loaded (read-only offline). */
    fun ops(userId: Int) = `in`.carcid.vayu.core.ops.OpsData(api, File(root, "ops-$userId"))

    /**
     * Signed out (here, on another phone or by an Admin): nothing that person opened stays on the
     * phone, neither Ops' saved copies nor downloaded photos, reports and spreadsheets.
     */
    fun forgetCopies(userId: Int) {
        clearNotices()                     // the next person on this phone never sees them
        localNotes.clear()
        ops(userId).clear()
        cache?.listFiles()?.filter { it.name.startsWith("media-") || it.name == "reports" || it.name.endsWith(".up") }
            ?.forEach { it.deleteRecursively() }
    }

    /** A cleared store never writes again, so a later sign-in needs a fresh one. */
    @Synchronized fun forgetJobs(userId: Int) { jobStores.remove(userId)?.clear() ?: JobStore(File(root, "jobs-$userId.json")).clear() }

    fun outbox(userId: Int): Outbox = Outbox(api, drafts(userId), BuildConfig.VERSION_CODE) { d ->
        jobs(userId).filled(d.bookingId, d.versions, d.answers, LocalDate.now().toString())
    }

    /** Finished work the server has in full, for jobs that are done or gone, leaves the phone. */
    fun prune(userId: Int) {
        val jobs = jobs(userId).jobs().associateBy { it.id }
        val drafts = drafts(userId)
        drafts.all().filter { d -> d.submitSent && d.files.all { it.sent } && jobs[d.bookingId].let { it == null || it.stage == "completed" } }
            .forEach { drafts.discard(it.bookingId) }
    }

    fun signedInId(): Int? = tokens.me()?.get("id")?.toIntOrNull()?.takeIf { tokens.access() != null }
}

class VayuApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // crash reports, tagged with this build; nothing about people or their jobs is sent.
        // Started beside the first screen, not before it (it would add ~35 ms to every start).
        if (BuildConfig.SENTRY_DSN.isNotBlank()) Thread { io.sentry.android.core.SentryAndroid.init(this) { o ->
            o.dsn = BuildConfig.SENTRY_DSN
            o.release = "vayu@${BuildConfig.VERSION_NAME}+${BuildConfig.VERSION_CODE}"
            o.environment = if (BuildConfig.DEBUG) "debug" else "release"
            o.isSendDefaultPii = false
            o.isEnableAutoSessionTracking = false
            o.isEnableUserInteractionBreadcrumbs = false
            o.isEnableNetworkEventBreadcrumbs = false
            o.isEnableActivityLifecycleTracingAutoFinish = false
            o.tracesSampleRate = null
            o.maxBreadcrumbs = 0
            // only what broke and where in the code: no error text (it can name a booking or a
            // customer), no extras, no user, no request; so nothing personal is ever stored or sent
            o.beforeSend = io.sentry.SentryOptions.BeforeSendCallback { e, _ ->
                e.message = null; e.request = null; e.user = null; e.breadcrumbs = null
                e.extras?.keys?.toList()?.forEach { e.removeExtra(it) }
                e.exceptions?.forEach { it.value = null }
                e
            }
        }; android.util.Log.i("Vayu", "crash reports on: ${io.sentry.Sentry.isEnabled()}") }
            .apply { priority = Thread.MIN_PRIORITY }.start()
    }

    val graph: Graph by lazy {
        val tokens = PrefsTokenStore(this)
        Graph(Api(BuildConfig.API_URL, tokens), tokens, filesDir, { OutboxWorker.enqueue(this) }, cacheDir,
            onJobs = { Reminders.schedule(this, graph, it) },
            clearNotices = { androidx.core.app.NotificationManagerCompat.from(this).cancelAll(); Reminders.cancel(this) })
    }
}

/** Sends drafts and files whenever there is signal; WorkManager keeps it going across restarts. */
class OutboxWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as VayuApp).graph
        val user = graph.signedInId() ?: return Result.success()
        return try {
            val done = graph.outbox(user).run()
            alertStuck(applicationContext, graph, user)
            if (done) Result.success() else Result.retry()
        } catch (e: ApiError) {
            Result.success()                  // signed out by the server: the app takes it from here
        }
    }

    companion object {
        fun enqueue(context: Context) {
            val work = OneTimeWorkRequestBuilder<OutboxWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(androidx.work.BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork("outbox", ExistingWorkPolicy.APPEND_OR_REPLACE, work)
        }
    }
}
