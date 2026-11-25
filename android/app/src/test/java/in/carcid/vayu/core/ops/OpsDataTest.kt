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
}
