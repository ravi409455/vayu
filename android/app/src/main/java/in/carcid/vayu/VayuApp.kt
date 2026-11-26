package `in`.carcid.vayu

import `in`.carcid.vayu.core.draft.Draft
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
            val clearNotices: () -> Unit = {},
            /** Writes drafts to storage (a thread of its own in the app; at once in tests). */
            private val writer: java.util.concurrent.Executor = java.util.concurrent.Executor { it.run() },
            /** A draft file that can't be read (a crash report in the app). */
            private val onDamaged: (File, Throwable) -> Unit = { _, _ -> },
            /** Send this phone's push token (WorkManager in the app, so it is retried). */
            val sendPushToken: () -> Unit = {}) {
    /** One person's own phone notices (reminders, photos not sending), shown in their bell. */
    fun localNotes(userId: Int) = `in`.carcid.vayu.core.alerts.LocalNotes(File(root, "notes-$userId.json"))

    /** A push arrived; the open app listens and refreshes at once. */
    val pushes = kotlinx.coroutines.flow.MutableSharedFlow<Unit>(extraBufferCapacity = 1)

    /** Tell the open app about a push; false when no screen is listening (the app is closed). */
    fun pushed(): Boolean = pushes.subscriptionCount.value > 0 && pushes.tryEmit(Unit)

    private val jobStores = HashMap<Int, JobStore>()
    private val draftStores = HashMap<Int, DraftStore>()

    @Synchronized fun jobs(userId: Int) = jobStores.getOrPut(userId) { JobStore(File(root, "jobs-$userId.json")) }
    @Synchronized fun drafts(userId: Int) = draftStores.getOrPut(userId) { DraftStore(File(root, "drafts-$userId"), writer, onDamaged) }

    /** Form versions this person's drafts are pinned to (their forms must stay on the phone). */
    fun pinned(userId: Int): Set<Int> = drafts(userId).all().flatMap { it.versions.values.filterNotNull() }.toSet()

    /** At app start: files no draft refers to (shots never confirmed, leftovers), for every person on this phone. */
    fun sweep() {
        root.listFiles { f -> f.isDirectory && f.name.startsWith("drafts-") }.orEmpty()
            .mapNotNull { it.name.removePrefix("drafts-").toIntOrNull() }.forEach { drafts(it).sweep() }
    }

    /** Ops' saved copies of what they last loaded (read-only offline). */
    fun ops(userId: Int) = `in`.carcid.vayu.core.ops.OpsData(api, File(root, "ops-$userId"))

    /**
     * Signed out (here, on another phone or by an Admin): nothing that person opened stays on the
     * phone, neither Ops' saved copies nor downloaded photos, reports and spreadsheets.
     */
    fun forgetCopies(userId: Int) {
        clearNotices()                     // the next person on this phone never sees them
        root.listFiles()?.filter { it.name.startsWith("notes-") }?.forEach { it.delete() }
        ops(userId).clear()
        clearDownloads()
    }

    private fun clearDownloads() {
        cache?.listFiles()?.filter { it.name.startsWith("media-") || it.name == "reports" || it.name.endsWith(".up") }
            ?.forEach { it.deleteRecursively() }
    }

    /**
     * At sign-in: what an earlier person left when their session ended by itself (or the app was
     * killed mid sign-out) goes, unless they still have work to send (N-8): their saved Ops copies
     * and downloads always, their lead list and sent drafts when nothing of theirs is unsent.
     */
    @Synchronized fun forgetOthers(userId: Int) {
        val others = root.listFiles().orEmpty()
            .mapNotNull { Regex("^(?:jobs|ops|drafts)-(\\d+)").find(it.name)?.groupValues?.get(1)?.toIntOrNull() }.toSet() - userId
        for (id in others) {
            File(root, "ops-$id").deleteRecursively()
            val store = drafts(id)
            if (store.all().none { it.unsent } && store.unreadable().isEmpty()) { forgetDrafts(id, all = false); forgetJobs(id) }
        }
        if (others.isNotEmpty()) clearDownloads()
    }

    /**
     * This person's drafts leave the phone (customer answers, stamped photos). [all]: everything (sign-out
     * already checked nothing is unsent); otherwise only fully sent ones (signed out by the server: the
     * rest stays for their next sign-in).
     */
    @Synchronized fun forgetDrafts(userId: Int, all: Boolean) {
        val store = drafts(userId)
        store.all().filter { all || !it.unsent }.forEach { store.discard(it.bookingId) }
        if (all) { draftStores.remove(userId); File(root, "drafts-$userId").deleteRecursively() }
    }

    /** A cleared store never writes again, so a later sign-in needs a fresh one. */
    @Synchronized fun forgetJobs(userId: Int) {
        val keep = pinned(userId)
        jobStores.remove(userId)?.clear(keep) ?: JobStore(File(root, "jobs-$userId.json")).clear(keep)
    }

    fun outbox(userId: Int): Outbox = Outbox(api, drafts(userId), BuildConfig.VERSION_CODE) { d ->
        jobs(userId).filled(d.bookingId, d.versions, d.answers, LocalDate.now().toString(), d.bookingAnswers)
    }

    /**
     * Send what this person's drafts hold, then tell the server what is still on the phone (it
     * refuses a sign-in on another phone while work is here). False: try again later.
     */
    suspend fun send(userId: Int): Boolean {
        val done = outbox(userId).run()
        val (drafts, files) = drafts(userId).unsentCounts()
        try { api.heartbeat(drafts, files) } catch (e: ApiError) { if (e.code == "DEVICE_REVOKED") throw e }
        return done
    }

    /** Finished work the server has in full, for jobs that are done or gone, leaves the phone. */
    fun prune(userId: Int, now: java.time.Instant = java.time.Instant.now()) {
        val jobs = jobs(userId).jobs().associateBy { it.id }
        val drafts = drafts(userId)
        // a copy the server said it already had may differ from it: kept 7 days after the server said so
        // (work sent offline long after its submit gets its 7 days too), then tidied like the rest
        // (sign-out removes it at once)
        fun keptAWhile(d: Draft) = d.problemCode == `in`.carcid.vayu.core.draft.ALREADY_SUBMITTED &&
            (d.problemAt ?: d.submittedAt)?.let { runCatching { java.time.OffsetDateTime.parse(it).toInstant() }.getOrNull() }
                ?.let { java.time.Duration.between(it, now) < java.time.Duration.ofDays(7) } != false
        drafts.all().filter { d -> d.submitSent && d.files.all { it.verified } && jobs[d.bookingId].let { it == null || it.stage == "completed" } &&
            !keptAWhile(d) }
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
            // the same labels as the server and the web: production, staging (and debug)
            o.environment = if (BuildConfig.BUILD_TYPE == "release") "production" else BuildConfig.BUILD_TYPE
            privateCrashReports(o)
        }; android.util.Log.i("Vayu", "crash reports on: ${io.sentry.Sentry.isEnabled()}") }
            .apply { priority = Thread.MIN_PRIORITY }.start()
        // shots never confirmed before the app died, and other files no draft refers to
        Thread { runCatching { graph.sweep() } }.apply { priority = Thread.MIN_PRIORITY }.start()
    }

    val graph: Graph by lazy {
        val tokens = PrefsTokenStore(this, onPlain = { io.sentry.Sentry.captureException(it) })
        Graph(Api(BuildConfig.API_URL, tokens), tokens, filesDir, { OutboxWorker.enqueue(this) }, cacheDir,
            onJobs = { Reminders.schedule(this, graph, it) },
            clearNotices = { forgetLeftovers(this) },
            writer = java.util.concurrent.Executors.newSingleThreadExecutor(),
            // only that it happened and where in the code (beforeSend drops the text)
            onDamaged = { _, e -> io.sentry.Sentry.captureException(e) },
            sendPushToken = { PushTokenWorker.enqueue(this) })
    }
}

/** Sends drafts and files whenever there is signal; WorkManager keeps it going across restarts. */
class OutboxWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as VayuApp).graph
        val user = graph.signedInId() ?: return Result.success()
        return try {
            val done = graph.send(user)
            alertStuck(applicationContext, graph, user)
            when {
                done -> Result.success()
                // the files are there and the server checks them in seconds: ask again soon, not after
                // the growing pause earlier failed sends built up (F-5: 16 minutes of "checking")
                graph.drafts(user).all().filter { it.unsent }.all { it.onlyChecking } -> {
                    enqueue(applicationContext, delaySeconds = 20); Result.success()
                }
                else -> Result.retry()
            }
        } catch (e: kotlin.coroutines.cancellation.CancellationException) {
            throw e
        } catch (e: ApiError) {
            Result.success()                  // signed out by the server: the app takes it from here
        } catch (e: Exception) {
            Result.retry()                    // anything else: keep trying (backoff), never give up for good
        }
    }

    companion object {
        fun enqueue(context: Context, delaySeconds: Long = 0) {
            val work = OneTimeWorkRequestBuilder<OutboxWorker>()
                .setInitialDelay(delaySeconds, TimeUnit.SECONDS)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(androidx.work.BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            val wm = WorkManager.getInstance(context)
            // a run in progress finishes, then this one follows; one only waiting (in backoff) is
            // replaced, so new work never waits hours behind it
            val running = runCatching { wm.getWorkInfosForUniqueWork("outbox").get() }.getOrNull().orEmpty()
                .any { it.state == androidx.work.WorkInfo.State.RUNNING }
            wm.enqueueUniqueWork("outbox", if (running) ExistingWorkPolicy.APPEND_OR_REPLACE else ExistingWorkPolicy.REPLACE, work)
        }
    }
}

/**
 * Crash reports say only what broke and where in the code: no error text (it can name a booking or a
 * customer), no extras, user, request, breadcrumbs, screenshots, view tree, logs or traces. Every
 * option is set here explicitly, so a new Sentry version's defaults can't turn one back on.
 */
fun privateCrashReports(o: io.sentry.android.core.SentryAndroidOptions) {
    o.isSendDefaultPii = false
    o.isEnableAutoSessionTracking = false
    o.isEnableUserInteractionBreadcrumbs = false
    o.isEnableNetworkEventBreadcrumbs = false
    o.isEnableActivityLifecycleTracingAutoFinish = false
    o.isAttachScreenshot = false
    o.isAttachViewHierarchy = false
    o.logs.isEnabled = false
    o.tracesSampleRate = null
    o.maxBreadcrumbs = 0
    o.beforeBreadcrumb = io.sentry.SentryOptions.BeforeBreadcrumbCallback { _, _ -> null }
    o.beforeSend = io.sentry.SentryOptions.BeforeSendCallback { e, _ -> scrubbed(e) }
}

/** The event with its text, request, user, breadcrumbs and extras removed. */
fun scrubbed(e: io.sentry.SentryEvent): io.sentry.SentryEvent {
    e.message = null; e.request = null; e.user = null; e.breadcrumbs = null
    e.extras?.keys?.toList()?.forEach { e.removeExtra(it) }
    e.exceptions?.forEach { it.value = null }
    return e
}
