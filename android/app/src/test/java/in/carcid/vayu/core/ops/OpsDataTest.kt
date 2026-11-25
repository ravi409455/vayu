package `in`.carcid.vayu.core.ops

import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.FakeServer
import `in`.carcid.vayu.core.auth.MemoryTokenStore
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import java.nio.file.Files

/** F-095: every search and filter is its own saved copy; the oldest go once there are too many. */
class OpsDataTest {
    private val server = FakeServer()
    @After fun stop() = server.stop()

    @Test fun theSavedCopiesStopGrowingAndTheOldestGoFirst() = runTest {
        val dir = Files.createTempDirectory("ops").toFile()
        var now = 1_000L
        val data = OpsData(Api(server.url, MemoryTokenStore().apply { save("A", "R") }), dir, clock = { now }, keep = 3)
        (1..5).forEach { i ->
            server.on("GET bookings", """{"count":$i,"results":[]}""")
            data.load("bookings?search=$i"); now += 1_000
            Thread.sleep(20)                                  // file times tell the copies apart
        }
        assertEquals(3, dir.listFiles()!!.size)
        assertNull(data.saved("bookings?search=1"))
        assertNotNull(data.saved("bookings?search=5"))
    }

    /** R-11: the report reply is decoded once, into a typed model, in the data layer. */
    @Test fun theReportReplyIsReadIntoATypedModel() {
        val r = Report.from(kotlinx.serialization.json.Json.parseToJsonElement("""{"revision":3,"status":"ready","updating":false,
            "out_of_date":true,"regenerate":{"allowed":false,"reason":"Choose which inspection counts first."},
            "generated_at":"2026-11-24T09:30:00+05:30","filename":"x.pdf","error":null,"verify_url":"https://v/x",
            "url":"/api/v1/bookings/b/report/download","preview_url":null,"something_new":1}"""))!!
        assertEquals(3, r.revision); assertEquals("ready", r.status); assertEquals(true, r.outOfDate)
        assertEquals(false, r.regenerate.allowed); assertEquals("Choose which inspection counts first.", r.regenerate.reason)
        assertEquals("", r.error); assertEquals("https://v/x", r.verifyUrl); assertNotNull(r.url)
        assertNull(Report.from(kotlinx.serialization.json.Json.parseToJsonElement("""{"code":"NO_REPORT"}""")).takeIf { it?.status?.isNotEmpty() == true })
    }

    /** R-11: a booking is decoded once; numbers, flags and the Admin's own form answers keep their types. */
    @Test fun aBookingIsReadIntoATypedModel() {
        val b = Booking.from(kotlinx.serialization.json.Json.parseToJsonElement("""{"id":"b1","booking_id":"DEMO-6","stage":"completed",
            "inspection_type":"pdi","assigned_expert":4,"row_version":3,"conflict":null,"cancel_reason":"","unverified_time":true,
            "alerts":[{"code":"TYPE_CHANGE_REJECTED","detail":"The expert started EV"}],
            "answers":{"customer_name":"Vikram Singh","inspection_date":"2026-11-24"},
            "timing":{"late_minutes":40,"duration_minutes":null,"late":true,"quick":false,"min_minutes":30,"grace_minutes":15,
                      "late_reviewed_by":"Priya Ops","late_reviewed_at":null,"quick_reviewed_by":null,"quick_reviewed_at":null},
            "something_new":[1,2]}"""))!!
        assertEquals("DEMO-6", b.bookingId); assertEquals(4, b.assignedExpert); assertEquals(3, b.rowVersion); assertEquals("", b.conflict)
        assertEquals(true, b.unverifiedTime); assertEquals("TYPE_CHANGE_REJECTED", b.alerts.single().code)
        assertEquals(40, b.timing!!.lateMinutes); assertEquals("Priya Ops", b.timing!!.lateReviewedBy)
        assertEquals("Vikram Singh", (b.answers["customer_name"] as kotlinx.serialization.json.JsonPrimitive).content)
    }
}
