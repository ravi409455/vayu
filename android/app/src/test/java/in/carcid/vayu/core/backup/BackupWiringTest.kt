package `in`.carcid.vayu.core.backup

import `in`.carcid.vayu.Graph
import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.FakeServer
import `in`.carcid.vayu.core.auth.MemoryTokenStore
import `in`.carcid.vayu.core.draft.BOOKING
import `in`.carcid.vayu.core.draft.Draft
import `in`.carcid.vayu.core.draft.JOB_CLOSED
import `in`.carcid.vayu.core.draft.LocalFile
import `in`.carcid.vayu.ui.expert.InspectionModel
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** The backup copies as the app uses them: made when a file is kept, gone when it is removed or the lead discarded. */
class BackupWiringTest {
    private val day = 24 * 60 * 60 * 1000L
    private var now = 1_000 * day
    private val server = FakeServer()
    private val root = Files.createTempDirectory("vayu").toFile()
    private val docs = Files.createTempDirectory("docs").toFile().resolve("Vayu")
    private val backup = BackupCopies(docs, root.resolve("backup-index.json"), { now }, { true })
    private val graph = Graph(Api(server.url, MemoryTokenStore()), MemoryTokenStore(), root, {}, backup = backup)

    @After fun stop() = server.stop()

    private fun model(): InspectionModel {
        graph.drafts(3).save(Draft(BOOKING, "TST-1014", "Arjun", mapOf("inspection" to 7), "pdi"))
        return InspectionModel(graph.drafts(3), graph.jobs(3), BOOKING, { java.time.Instant.ofEpochMilli(now) }, {}, backup = backup)
    }

    private fun shot(text: String) = File.createTempFile("shot", ".tmp", root).apply { writeText(text) }

    @Test fun aKeptPhotoGetsACopyNamedByItsPageAndField() = runBlocking {
        val m = model()
        m.addFile("inspection", "front", "photo", shot("front"), "image/jpeg", "camera", "Front left 1", single = false, page = "Exterior")
        assertEquals("front", docs.resolve("TST-1014/Exterior - Front left 1.jpg").readText())
    }

    @Test fun removingAPhotoOrDiscardingTheLeadRemovesItsCopies() = runBlocking {
        val m = model()
        m.addFile("inspection", "front", "photo", shot("1"), "image/jpeg", "camera", "Front 1", single = false, page = "Exterior")
        m.addFile("inspection", "front", "photo", shot("2"), "image/jpeg", "camera", "Front 2", single = false, page = "Exterior")
        m.removeFile("inspection", "front", m.draft.files.first().id)
        assertFalse(docs.resolve("TST-1014/Exterior - Front 1.jpg").exists())
        assertTrue(docs.resolve("TST-1014/Exterior - Front 2.jpg").exists())
        m.discard()
        assertFalse(docs.resolve("TST-1014").exists())
    }

    @Test fun replacingASignatureRemovesTheOldCopy() = runBlocking {
        val m = model()
        m.addFile("wrapup", "sign", "signature", shot("old"), "image/png", "camera", "Signature", single = true, page = "Wrap-up")
        m.addFile("wrapup", "sign", "signature", shot("new"), "image/png", "camera", "Signature", single = true, page = "Wrap-up")
        assertEquals(listOf("Wrap-up - Signature.png"), docs.resolve("TST-1014").list()!!.toList())
        assertEquals("new", docs.resolve("TST-1014/Wrap-up - Signature.png").readText())
    }

    private fun file(id: String, verified: Boolean = false, refused: Boolean = false) =
        LocalFile(id, "inspection", "front", "photo", "", "image/jpeg", "camera", 1, "", "Front", verified = verified, refused = refused)

    private fun copyFor(id: String, booking: String = BOOKING) =
        backup.copy(BackupCopies.Copy(booking, "TST-1014", id, "Exterior", "Front $id", "image/jpeg"), shot(id))

    @Test fun theCleanUpReadsEveryDraftOnThePhone() {
        val closed = "00000000-0000-0000-0000-000000000009"
        graph.drafts(3).save(Draft(BOOKING, "TST-1014", "Arjun", emptyMap(), "pdi", submitSent = true,
            files = listOf(file("sent", verified = true), file("waiting"), file("refused", refused = true))))
        graph.drafts(5).save(Draft(closed, "TST-1015", "Neha", emptyMap(), "pdi", problemCode = JOB_CLOSED,
            files = listOf(file("closed"))))                                  // another person, signed out
        listOf("sent", "waiting", "refused").forEach { copyFor(it) }
        copyFor("closed", closed)
        graph.cleanBackups()                                                   // the phone learns the states now
        now += 2 * day
        graph.cleanBackups()
        val left = docs.resolve("TST-1014").list()!!.sorted()
        assertEquals(listOf("Exterior - Front waiting.jpg"), left)            // only what the server still needs
    }

    @Test fun nothingWhoseDraftIsGoneIsDeletedWhileADraftCantBeRead() {
        copyFor("x")                                                          // its draft is not on the phone
        File(root, "drafts-3").apply { mkdirs() }.resolve("$BOOKING.json").writeText("{not json")
        graph.cleanBackups()
        assertTrue(docs.resolve("TST-1014/Exterior - Front x.jpg").exists())
    }
}
