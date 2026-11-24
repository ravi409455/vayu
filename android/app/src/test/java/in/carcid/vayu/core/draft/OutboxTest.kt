package `in`.carcid.vayu.core.draft

import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.FakeServer
import `in`.carcid.vayu.core.auth.MemoryTokenStore
import `in`.carcid.vayu.core.forms.Fixtures
import `in`.carcid.vayu.core.sync.JobStore
import `in`.carcid.vayu.core.sync.job
import `in`.carcid.vayu.core.sync.payload
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

const val BOOKING = "00000000-0000-0000-0000-000000000002"

class OutboxTest {
    private val server = FakeServer()
    private val root = Files.createTempDirectory("vayu").toFile()
    private val drafts = DraftStore(File(root, "drafts"))
    private val jobs = JobStore(File(root, "jobs.json")).apply {
        apply(payload(job(BOOKING, start = 1, end = 9, code = "DEMO-2"), forms = Fixtures.FORMS), 0)
    }
    private val outbox = Outbox(Api(server.url, MemoryTokenStore().apply { save("A", "R") }), drafts, 5) { d ->
        jobs.filled(d.bookingId, d.versions, d.answers, "2026-11-24")
    }

    @After fun stop() = server.stop()

    /** A started, submitted draft with one door photo (10 bytes, sent in 2 parts of 5). */
    private fun ready(): LocalFile {
        val photo = File(drafts.filesDir, "p.jpg").apply { writeBytes(ByteArray(10) { it.toByte() }) }
        val f = LocalFile("11111111-1111-1111-1111-111111111111", "inspection", "door_photos", "photo", photo.path,
            "image/jpeg", "camera", 10, "ab".repeat(32), "Door photos 1")
        drafts.save(Draft(BOOKING, "DEMO-2", "Arjun", mapOf("start" to 1, "inspection" to 7, "end" to 9), "pdi",
            answers = mapOf("start" to mapOf("travel" to "car"),
                "inspection" to mapOf("chassis_no" to "MA3", "odometer" to 12450.0, "bonnet" to "ok", "door" to "minor", "door_photos" to listOf(f.id)),
                "end" to mapOf("taking_payment" to false)),
            startedAt = "2026-11-24T15:28:00+05:30", submittedAt = "2026-11-24T16:10:00+05:30", files = listOf(f)))
        server.on("POST media/initiate", """{"id":"0000bbbb-0000-0000-0000-000000000001","status":"pending","part_size":5,
            "parts":[{"part_number":1,"url":"${server.raw("/s3/p1")}"},{"part_number":2,"url":"${server.raw("/s3/p2")}"}]}""")
        server.on("GET media/0000bbbb-0000-0000-0000-000000000001", """{"uploaded_parts":[]}""")
        server.on("PUT /s3/p1", "", headers = mapOf("ETag" to "e1"))
        server.on("PUT /s3/p2", "", headers = mapOf("ETag" to "e2"))
        server.on("POST media/0000bbbb-0000-0000-0000-000000000001/complete", """{"status":"uploaded"}""")
        server.on("POST bookings/$BOOKING/start", """{}""")
        server.on("POST bookings/$BOOKING/submit", """{}""")
        return f
    }

    @Test fun everythingIsSentInOrderWithServerFileIds() = runBlocking {
        ready()
        assertTrue(outbox.run())
        val d = drafts.get(BOOKING)!!
        assertTrue(d.startSent && d.submitSent)
        assertTrue(d.files.single().sent)
        assertEquals("0000bbbb-0000-0000-0000-000000000001", d.files.single().serverId)
        val order = server.requests.map { it.first }
        assertTrue(order.indexOf("POST media/initiate") < order.indexOf("POST bookings/$BOOKING/start"))
        assertTrue(order.indexOf("POST bookings/$BOOKING/submit") < order.indexOf("PUT /s3/p1"))   // answers never wait for bytes
        val start = Json.parseToJsonElement(server.bodiesOf("POST bookings/$BOOKING/start").single()).jsonObject
        assertEquals("car", start["start_answers"]!!.jsonObject["travel"]!!.jsonPrimitive.content)
        val answers = Json.parseToJsonElement(server.bodiesOf("POST bookings/$BOOKING/submit").single()).jsonObject["answers"]!!.jsonObject
        val insp = answers["inspection"]!!.jsonObject
        assertEquals("0000bbbb-0000-0000-0000-000000000001", insp["door_photos"]!!.jsonArray.single().jsonPrimitive.content)   // the server's id, not the phone's
        assertEquals("12450", insp["odometer"].toString())                                       // whole numbers stay whole
        val complete = Json.parseToJsonElement(server.bodiesOf("POST media/0000bbbb-0000-0000-0000-000000000001/complete").single()).jsonObject
        assertEquals(2, complete["parts"]!!.jsonArray.size)
    }

    @Test fun runningAgainSendsNothingTwice() = runBlocking {
        ready()
        outbox.run()
        val before = server.requests.size
        assertTrue(outbox.run())
        assertEquals(before, server.requests.size)
    }

    @Test fun withoutSignalItAsksToTryLater() = runBlocking {
        ready()
        server.stop()
        assertFalse(outbox.run())
        assertFalse(drafts.get(BOOKING)!!.startSent)
    }

    @Test fun aJobTakenAwayStillSendsTheSubmitForOps() = runBlocking {
        ready()
        server.on("POST bookings/$BOOKING/start", """{"code":"NOT_ASSIGNED","detail":"This job is no longer assigned to you."}""", 409)
        outbox.run()
        val d = drafts.get(BOOKING)!!
        assertFalse(d.startSent)
        assertTrue(d.submitSent)
        assertEquals(null, d.problemCode)                    // the submit went through and cleared it
    }

    @Test fun aJobClosedOnTheServerSaysSoAndStopsTrying() = runBlocking {
        ready()
        server.on("POST media/initiate", """{"code":"NOT_FOUND","detail":"Booking not found."}""", 404)
        outbox.run()
        val d = drafts.get(BOOKING)!!
        assertEquals(JOB_CLOSED, d.problemCode)
        assertEquals(CLOSED_TEXT, d.problem)
        assertTrue(d.unsent)                                   // still blocks sign-out until discarded
        val tries = server.requests.size
        outbox.run()
        assertEquals(tries, server.requests.size)              // no more calls for a closed job
    }

    @Test fun aRefusedStartOnAClosedJobIsTheSame() = runBlocking {
        ready()
        server.on("POST bookings/$BOOKING/start", """{"code":"BOOKING_CLOSED","detail":"closed"}""", 409)
        outbox.run()
        assertEquals(JOB_CLOSED, drafts.get(BOOKING)!!.problemCode)
    }

    @Test fun aRefusedSubmitIsKeptAndExplained() = runBlocking {
        ready()
        server.on("POST bookings/$BOOKING/submit", """{"code":"INVALID_ANSWERS","detail":"Some answers are invalid.","errors":{"odometer":"OUT_OF_RANGE"}}""", 400)
        outbox.run()
        val d = drafts.get(BOOKING)!!
        assertFalse(d.submitSent)
        assertEquals("INVALID_ANSWERS", d.problemCode)
        assertNotNull(d.problem)
        assertEquals(null, d.submittedAt)                                  // unlocked: the expert can fix it
        assertEquals(mapOf("odometer" to "OUT_OF_RANGE"), d.fieldErrors)    // and sees which answer
        val sent = server.bodiesOf("POST bookings/$BOOKING/submit").size
        outbox.run()
        assertEquals(sent, server.bodiesOf("POST bookings/$BOOKING/submit").size)   // no re-sending a refused submit
        assertEquals(emptyMap<String, String>(), drafts.get(BOOKING)!!.withAnswer("inspection", "odometer", 1.0).fieldErrors)
    }

    @Test fun aFileThatArrivesDamagedIsSentAgainLater() = runBlocking {
        ready()
        server.on("POST media/0000bbbb-0000-0000-0000-000000000001/complete", """{"status":"failed"}""")
        outbox.run()
        val f = drafts.get(BOOKING)!!.files.single()
        assertFalse(f.sent)
        assertNotNull(f.error)
    }

    @Test fun theDraftSurvivesARestartAndCountsWhatIsUnsent() {
        ready()
        val again = DraftStore(File(root, "drafts"))
        val d = again.get(BOOKING)!!
        assertEquals(12450.0, d.answer("inspection", "odometer"))
        assertEquals(1 to 1, again.unsentCounts())
        assertEquals(0L, again.clearSentCopies())             // an unsent file is never cleared
        assertTrue(File(d.files.single().path).exists())
        again.discard(BOOKING)
        assertFalse(File(d.files.single().path).exists())
        assertEquals(null, again.get(BOOKING))
    }

    @Test fun aSentFileRemovedOnThePhoneIsTakenBackOnTheServer() = runBlocking {
        val f = ready()
        outbox.run()
        server.on("DELETE media/0000bbbb-0000-0000-0000-000000000001", "", 204)
        drafts.update(BOOKING) { it.copy(submittedAt = null) }                              // still editing
        val model = `in`.carcid.vayu.ui.expert.InspectionModel(drafts, jobs, BOOKING, { java.time.Instant.now() }, {})
        model.removeFile("inspection", "door_photos", f.id)
        assertEquals(listOf("0000bbbb-0000-0000-0000-000000000001"), drafts.get(BOOKING)!!.discards)
        outbox.run()
        assertEquals(1, server.bodiesOf("DELETE media/0000bbbb-0000-0000-0000-000000000001").size)
        assertTrue(drafts.get(BOOKING)!!.discards.isEmpty())
    }

    @Test fun filesFromBeforeArePickedUpWhenTheServerSaysTheFieldIsFull() = runBlocking {
        ready()
        server.on("POST media/initiate", """{"code":"TOO_MANY","detail":"'door_photos' takes at most 1."}""", 409)
        server.on("GET bookings/$BOOKING/media", """[{"id":"0000aaaa-0000-0000-0000-000000000001","field_key":"door_photos","kind":"photo","status":"verified"},
            {"id":"0000aaaa-0000-0000-0000-000000000002","field_key":"door_photos","kind":"photo","status":"pending"}]""")
        server.on("DELETE media/0000aaaa-0000-0000-0000-000000000002", "", 204)
        outbox.run()
        val d = drafts.get(BOOKING)!!
        val old = d.files.single { it.serverId == "0000aaaa-0000-0000-0000-000000000001" }
        assertTrue(old.sent)                                                               // the finished one is back in the answers
        assertTrue((d.answer("inspection", "door_photos") as List<*>).contains(old.id))
        assertEquals(1, server.bodiesOf("DELETE media/0000aaaa-0000-0000-0000-000000000002").size)                         // the half-sent one stops counting
    }
}
