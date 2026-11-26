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

    /** N-2: Today, a day's bookings and the users read every page, not the first 50. */
    @Test fun aWholeListReadsEveryPage() = runTest {
        val data = OpsData(Api(server.url, MemoryTokenStore().apply { save("A", "R") }), Files.createTempDirectory("ops").toFile())
        server.on("GET users", """{"count":3,"next":"http://x/api/v1/users?page=2","results":[{"id":1},{"id":2}]}""")
        server.onQuery("GET users", "page=2", """{"count":3,"next":null,"results":[{"id":3}]}""")
        val all = data.load(allPages("users")).data
        assertEquals(listOf(1, 2, 3), all.rows().map { it["id"].toString().toInt() })
        assertEquals(listOf("page_size=200", "page_size=200&page=2"), server.queries.toList())
        assertEquals(3, data.saved(allPages("users"))!!.data.rows().size)              // kept whole for offline
    }

    /** R-11: the report reply is decoded once, into a typed model, in the data layer. */
    @Test fun theReportReplyIsReadIntoATypedModel() {
        val r = Report.from(kotlinx.serialization.json.Json.parseToJsonElement("""{"revision":3,"status":"ready","updating":false,
            "out_of_date":true,"regenerate":{"allowed":false,"reason":"Choose which inspection counts first."},
            "generated_at":"2026-11-24T09:30:00+05:30","filename":"x.pdf","error":null,"verify_url":"https://v/x",
            "url":"/api/v1/bookings/b/report/download","preview_url":null,"something_new":1}"""))!!
        assertEquals(3, r.revision); assertEquals("ready", r.status); assertEquals(true, r.outOfDate)
        assertEquals(false, r.regenerate.allowed); assertEquals("Choose which inspection counts first.", r.regenerate.reason)
        assertEquals("", r.error); assertNotNull(r.url)
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

    @Test fun inspectionsAreReadIntoTypedModels() {
        val rows = kotlinx.serialization.json.Json.parseToJsonElement("""[
            {"id":"i1","expert":4,"status":"submitted","submitted_at":"2026-11-24T10:40:00Z","row_version":2,"form_version":7,
             "start_version":null,"end_version":9,"scores":{"overall":{"word":"good"}},"overrides":{},"answers":{"inspection":{"odometer":12400}}},
            "not an inspection"]""") as kotlinx.serialization.json.JsonArray
        val list = Inspection.list(rows.mapNotNull { it as? kotlinx.serialization.json.JsonObject })
        val i = list.single()
        assertEquals(4, i.expert); assertEquals(7, i.formVersion); assertNull(i.startVersion); assertEquals(9, i.endVersion)
        assertEquals(2, i.rowVersion); assertEquals("submitted", i.status)
    }

    @Test fun mediaRowsAreReadIntoTypedModels() {
        val rows = (kotlinx.serialization.json.Json.parseToJsonElement("""[{"id":"m1","field_key":"front","kind":"photo","status":"verified","size":123,"new":true}]""")
            as kotlinx.serialization.json.JsonArray).map { it as kotlinx.serialization.json.JsonObject }
        assertEquals(listOf(MediaItem("m1", "front", "photo", "verified")), MediaItem.list(rows))
    }

    @Test fun namesProblemsAndDashboardsAreReadIntoTypedModels() {
        fun rows(j: String) = (kotlinx.serialization.json.Json.parseToJsonElement(j) as kotlinx.serialization.json.JsonArray).map { it as kotlinx.serialization.json.JsonObject }
        val p = Person.list(rows("""[{"id":4,"username":"meera","name":"","role":"expert","is_active":true,"phone":null}]""")).single()
        assertEquals("meera", p.shown); assertEquals("", p.phone)
        assertEquals(listOf("pune" to "Pune"), ListItem.list(rows("""[{"key":"pune","label":"Pune","archived":false}]""")).map { it.key to it.label })
        assertEquals("out_of_date", ReportProblem.list(rows("""[{"booking":"b","booking_id":"D-1","status":"ready","error":"","problem":"out_of_date","out_of_date_since":"2026-11-24T10:00:00+05:30"}]""")).single().problem)
        assertEquals("front", StuckUpload.list(rows("""[{"id":"s","booking":"b","booking_id":"D-1","field_key":"front","status":"pending","expert":"Meera","created_at":"x"}]""")).single().fieldKey)
        val d = DashSummary.from(kotlinx.serialization.json.Json.parseToJsonElement("""{"period":{"bookings":12,"completion_rate":91.7,"on_time":null},"previous":{"bookings":10},
            "by_expert":[{"expert":4,"bookings":1,"on_time":92,"late":0}]}"""))!!
        assertEquals(12, d.period.bookings); assertEquals(91.7, d.period.completionRate!!, 0.0); assertNull(d.period.onTime); assertEquals(92, d.byExpert.single().onTime)
        assertEquals(listOf(VolumeRow("2026-W48", "pdi", 14)), VolumeRow.list(rows("""[{"period":"2026-W48","key":"pdi","count":14}]""")))
    }
}
