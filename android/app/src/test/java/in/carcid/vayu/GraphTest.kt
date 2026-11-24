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

    @Test fun afterSendingTheServerHearsWhatIsLeft() = runBlocking {
        server.on("POST devices/heartbeat", """{"min_app_version":1}""")
        graph.drafts(3).save(Draft(BOOKING, "DEMO-2", "Arjun", mapOf("inspection" to 7), "pdi"))   // not submitted yet
        graph.send(3)
        val beat = server.bodiesOf("POST devices/heartbeat").single()
        assertTrue(beat.contains("\"drafts\":1")); assertTrue(beat.contains("\"files\":0"))
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
