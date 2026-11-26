package `in`.carcid.vayu

import `in`.carcid.vayu.core.api.FakeServer
import `in`.carcid.vayu.core.api.testGraph
import `in`.carcid.vayu.core.auth.MemoryTokenStore
import `in`.carcid.vayu.core.draft.BOOKING
import `in`.carcid.vayu.core.draft.Draft
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GraphTest {
    private val server = FakeServer()
    private val graph = testGraph(server, MemoryTokenStore().apply { save("A", "R") })

    @After fun stop() = server.stop()

    @Test fun aNewPersonSigningInRemovesWhatAnEarlierOneLeftUnlessItIsUnsent() {
        // N-8: person 3's session ended by itself; person 4 signs in on the same phone
        val root = java.nio.file.Files.createTempDirectory("vayu").toFile()
        val graph = testGraph(server, MemoryTokenStore().apply { save("A", "R") }, root)
        java.io.File(root, "ops-3").apply { mkdirs(); resolve("a.json").writeText("{}") }
        graph.jobs(3).apply(`in`.carcid.vayu.core.sync.payload(`in`.carcid.vayu.core.sync.job(BOOKING)), 0)
        graph.drafts(5).save(Draft(BOOKING, "DEMO-2", "Arjun", mapOf("inspection" to 7), "pdi"))   // 5 has unsent work
        graph.jobs(5).apply(`in`.carcid.vayu.core.sync.payload(`in`.carcid.vayu.core.sync.job(BOOKING)), 0)
        graph.forgetOthers(4)
        assertTrue(!java.io.File(root, "ops-3").exists())
        assertTrue(graph.jobs(3).jobs().isEmpty())
        assertEquals(1, graph.jobs(5).jobs().size)                              // kept for their unsent draft
        assertEquals(1, graph.drafts(5).all().size)
    }

    @Test fun afterSendingTheServerHearsWhatIsLeft() = runBlocking {
        server.on("POST devices/heartbeat", """{"min_app_version":1}""")
        graph.drafts(3).save(Draft(BOOKING, "DEMO-2", "Arjun", mapOf("inspection" to 7), "pdi"))   // not submitted yet
        graph.send(3)
        val beat = server.bodiesOf("POST devices/heartbeat").single()
        assertTrue(beat.contains("\"drafts\":1")); assertTrue(beat.contains("\"files\":0"))
    }

    /** A draft the server said it already had may differ from the server's copy: tidying never deletes it (sign-out does). */
    @Test fun aDraftTheServerAlreadyHadIsNotTidiedAway() {
        graph.jobs(3).apply(`in`.carcid.vayu.core.sync.payload(`in`.carcid.vayu.core.sync.job(BOOKING, stage = "completed")), 0)
        graph.drafts(3).save(Draft(BOOKING, "DEMO-2", "Arjun", mapOf("inspection" to 7), "pdi", submitSent = true,
            problem = "Already submitted; Ops can edit it.", problemCode = "ALREADY_SUBMITTED"))
        val sent = java.time.Instant.parse("2026-11-24T10:00:00Z")
        graph.drafts(3).update(BOOKING) { it.copy(submittedAt = "2026-11-24T15:30:00+05:30") }
        graph.prune(3, now = sent.plus(java.time.Duration.ofDays(6)))
        assertTrue("kept a while: it may differ from the server's copy", graph.drafts(3).get(BOOKING) != null)
        graph.prune(3, now = sent.plus(java.time.Duration.ofDays(8)))
        assertEquals("but not for ever", null, graph.drafts(3).get(BOOKING))
    }

    /** N-10: work sent offline long after its submit gets its 7 days from when the server said so. */
    @Test fun theWeekCountsFromTheRefusalNotFromTheSubmit() {
        graph.jobs(3).apply(`in`.carcid.vayu.core.sync.payload(`in`.carcid.vayu.core.sync.job(BOOKING, stage = "completed")), 0)
        val refused = java.time.Instant.parse("2026-11-24T10:00:00Z")
        graph.drafts(3).save(Draft(BOOKING, "DEMO-2", "Arjun", mapOf("inspection" to 7), "pdi", submitSent = true,
            submittedAt = "2026-11-10T15:30:00+05:30", problemCode = "ALREADY_SUBMITTED", problemAt = refused.toString()))
        graph.prune(3, now = refused.plus(java.time.Duration.ofDays(1)))
        assertTrue(graph.drafts(3).get(BOOKING) != null)
    }

    @Test fun formsOfDraftsAreKeptWhenTheServerSignsThePersonOut() {
        graph.jobs(3).apply(`in`.carcid.vayu.core.sync.payload(`in`.carcid.vayu.core.sync.job(BOOKING),
            forms = """{"7":{"pages":[]}}"""), 0)
        graph.drafts(3).save(Draft(BOOKING, "DEMO-2", "Arjun", mapOf("inspection" to 7), "pdi"))
        graph.forgetJobs(3)
        assertEquals(setOf(7), graph.jobs(3).haveVersions())
        assertTrue(graph.jobs(3).jobs().isEmpty())
    }

    @Test fun theSyncAsksForTheFormsOfDrafts() {
        server.on("GET sync/jobs", `in`.carcid.vayu.core.sync.payload("").toString())
        graph.drafts(3).save(Draft(BOOKING, "DEMO-2", "Arjun", mapOf("start" to 1, "inspection" to 7), "pdi"))
        val m = `in`.carcid.vayu.ui.expert.JobsModel(graph.api, graph::jobs, kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.Unconfined),
            System::currentTimeMillis, {}, {}, pinned = graph::pinned)
        m.open(3, offline = false)
        val start = System.currentTimeMillis()
        while (server.queries.none { it.contains("drafts=") } && System.currentTimeMillis() - start < 5_000) Thread.sleep(20)
        assertTrue(server.queries.any { it.contains("drafts=1,7") })
    }
}
