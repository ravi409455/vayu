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
            val kick: () -> Unit) {
    private val jobStores = HashMap<Int, JobStore>()
    private val draftStores = HashMap<Int, DraftStore>()

    @Synchronized fun jobs(userId: Int) = jobStores.getOrPut(userId) { JobStore(File(root, "jobs-$userId.json")) }
    @Synchronized fun drafts(userId: Int) = draftStores.getOrPut(userId) { DraftStore(File(root, "drafts-$userId")) }

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
    val graph: Graph by lazy {
        val tokens = PrefsTokenStore(this)
        Graph(Api(BuildConfig.API_URL, tokens), tokens, filesDir) { OutboxWorker.enqueue(this) }
    }
}

/** Sends drafts and files whenever there is signal; WorkManager keeps it going across restarts. */
class OutboxWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as VayuApp).graph
        val user = graph.signedInId() ?: return Result.success()
        return try {
            if (graph.outbox(user).run()) Result.success() else Result.retry()
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
