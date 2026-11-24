package `in`.carcid.vayu.ui.ops

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onLast
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.FakeServer
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.auth.MemoryTokenStore
import `in`.carcid.vayu.core.forms.Fixtures
import `in`.carcid.vayu.core.ops.OpsData
import `in`.carcid.vayu.ui.theme.ThemeMode
import `in`.carcid.vayu.ui.theme.VayuTheme
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.nio.file.Files
import java.time.LocalDate

private const val B4 = "00000000-0000-0000-0000-000000000004"
private const val B8 = "00000000-0000-0000-0000-000000000008"
private const val B14 = "00000000-0000-0000-0000-000000000014"
private const val TODAY = "2026-11-24"

private fun booking(id: String, code: String, name: String, time: String, stage: String, expert: Int?, conflict: String = "") = """
  {"id":"$id","booking_id":"$code","stage":"$stage","inspection_type":"pdi","assigned_expert":${expert ?: "null"},"row_version":3,
   "conflict":"$conflict","alerts":[],"answers":{"customer_name":"$name","customer_phone":"+919876500014","address":"$code demo street",
   "city":"delhi","car_make_model":"nexon","inspection_date":"$TODAY","inspection_time":"$time"}}"""

@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w390dp-h844dp-xxhdpi", sdk = [34])
class OpsFlowTest {
    @get:Rule val compose = createComposeRule()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))
    private val server = FakeServer()
    // a fixed clock: "Offline · as of 10:42" must read the same on every run
    private val data = OpsData(Api(server.url, MemoryTokenStore().apply { save("A", "R") }), Files.createTempDirectory("ops").toFile(),
        clock = { java.time.LocalDateTime.of(2026, 11, 24, 10, 42).atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli() })
    private val me = Me(5, "priya", "Priya Ops", "ops", false, "light",
        setOf("bookings.view", "bookings.assign", "bookings.edit", "bookings.create", "bookings.cancel", "bookings.reschedule",
            "bookings.force_release", "submissions.edit", "media.manage", "media.download", "ratings.override", "reports.view",
            "reports.regenerate", "dashboards.view", "dashboards.export"))

    private val day = listOf(
        booking(B4, "DEMO-4", "Rohit Sharma", "13:00", "draft", null),
        booking(B8, "DEMO-8", "Farhan Ali", "11:00", "in_progress", 3),
        booking(B14, "DEMO-14", "Manoj Pillai", "15:00", "submitted", 4, conflict = "TWO_EXPERTS"),
        booking("00000000-0000-0000-0000-000000000006", "DEMO-6", "Vikram Singh", "09:00", "completed", 4),
        booking("00000000-0000-0000-0000-000000000002", "DEMO-2", "Arjun Mehta", "15:30", "assigned", 3),
    )

    init {
        server.on("GET bookings", """{"count":${day.size},"results":[${day.joinToString(",")}]}""")
        server.on("GET users", """{"count":3,"results":[{"id":3,"username":"ravi","name":"Ravi Expert","role":"expert","is_active":true},
            {"id":4,"username":"meera","name":"Meera Expert","role":"expert","is_active":true},{"id":5,"username":"priya","name":"Priya Ops","role":"ops","is_active":true}]}""")
        server.on("GET master-lists/city/items", """[{"key":"delhi","label":"Delhi"}]""")
        server.on("GET master-lists/car_make_model/items", """[{"key":"nexon","label":"Tata Nexon"}]""")
        server.on("GET inspection-types", """[{"key":"pdi","label":"PDI","available":true}]""")
        server.on("GET problems/stuck-uploads", "[]")
        server.on("GET problems/reports", "[]")
        server.on("GET bookings/$B14", day[2])
        server.on("GET bookings/$B14/inspections", """[
            {"id":"aaaaaaaa-0000-0000-0000-000000000001","expert":4,"status":"submitted","submitted_at":"2026-11-24T10:40:00Z","created_at":"2026-11-24T09:00:00Z",
             "row_version":2,"form_version":7,"start_version":null,"end_version":null,"overrides":{},
             "scores":{"overall":{"word":"good","suggested_word":"good"},"ratings":{},"derived":{"seal":true}},
             "answers":{"inspection":{"chassis_no":"MA3","odometer":12400,"bonnet":"ok","door":"ok"},"start":{},"end":{}}},
            {"id":"aaaaaaaa-0000-0000-0000-000000000002","expert":3,"status":"submitted","submitted_at":"2026-11-24T10:05:00Z","created_at":"2026-11-24T09:05:00Z",
             "row_version":1,"form_version":7,"start_version":null,"end_version":null,"overrides":{},"scores":{},"answers":{"inspection":{"chassis_no":"MA3"}}}]""")
        server.on("GET bookings/$B14/media", "[]")
        server.on("GET bookings/$B14/report", """{"code":"NO_REPORT","detail":"No report has been generated yet."}""", 404)
        server.on("GET form-versions/7", Fixtures.INSPECTION)
        // the real server's shape: {"rows": [...]}
        server.on("GET dashboards/volume", """{"rows":[{"period":"2026-W46","key":"pdi","count":12},{"period":"2026-W47","key":"pdi","count":10},
            {"period":"2026-W48","key":"pdi","count":14},{"period":"2026-W48","key":"ev","count":4}]}""")
        server.on("POST bookings/$B4/assign", "{}")
    }

    @After fun stop() = server.stop()

    private fun show(theme: ThemeMode = ThemeMode.LIGHT) = compose.setContent {
        VayuTheme(theme) { OpsHome(me, data, { LocalDate.parse(TODAY) }, onProfile = {}) }
    }

    private fun waitFor(text: String) = compose.waitUntil(5_000) { compose.onAllNodes(hasText(text, substring = true)).fetchSemanticsNodes().isNotEmpty() }
    private fun shot(name: String) = compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/$name.png", roborazziOptions = options)

    @Test fun todayShowsTheDayUnassignedAndExperts() {
        show()
        waitFor("of 5 jobs done")
        compose.onNodeWithText("UNASSIGNED · 1").assertIsDisplayed()
        compose.onNodeWithText("Rohit Sharma").assertIsDisplayed()
        waitFor("Meera Expert")
        compose.onNode(hasText("Ravi Expert", substring = true)).performClick()          // expand: their jobs
        compose.onNodeWithText("Arjun Mehta").assertIsDisplayed()
        shot("ops_today")
    }

    @Test fun assigningFromTodaySendsTheExpert() {
        show()
        waitFor("Rohit Sharma")
        compose.onNodeWithText("Assign").performClick()
        waitFor("Assign an expert")
        compose.onAllNodes(hasText("Meera Expert")).onLast().performClick()      // the row in the sheet
        compose.onNodeWithText("Assign Meera").performClick()
        compose.waitUntil(5_000) { server.bodiesOf("POST bookings/$B4/assign").isNotEmpty() }
        assertEquals(4, Json.parseToJsonElement(server.bodiesOf("POST bookings/$B4/assign").single()).jsonObject["expert"]!!.jsonPrimitive.int)
    }

    @Test fun bookingsListsWhoNeedsAnExpertFirst() {
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("NEED AN EXPERT · 1")
        compose.onNodeWithText("SCHEDULED · 4").assertIsDisplayed()
        shot("ops_bookings")
    }

    @Test fun aConflictIsShownAndResolvedOnTheBooking() {
        server.on("POST bookings/$B14/resolve-conflict", "{}")
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai")
        compose.onNodeWithText("Manoj Pillai").performClick()
        waitFor("Two experts inspected this car")
        shot("ops_booking")
        compose.onNodeWithText("Waits for your choice above").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("Compare and choose").performClick()
        waitFor("Which inspection counts?")
        compose.onNode(hasText("· good", substring = true)).performClick()            // Meera's: 4 answers, rated good
        compose.onNodeWithText("Keep this one").performClick()
        compose.waitUntil(5_000) { server.bodiesOf("POST bookings/$B14/resolve-conflict").isNotEmpty() }
        assertTrue(server.bodiesOf("POST bookings/$B14/resolve-conflict").single().contains("aaaaaaaa-0000-0000-0000-000000000001"))
    }

    @Test fun anAnswerIsChangedWithItsRowVersion() {
        server.on("PATCH inspections/aaaaaaaa-0000-0000-0000-000000000001", "{}")
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai"); compose.onNodeWithText("Manoj Pillai").performClick()
        waitFor("Inspection"); compose.onNodeWithText("Inspection").performScrollTo().performClick()
        waitFor("Chassis number")
        shot("ops_answers")
        compose.onNodeWithText("Odometer").performClick()
        waitFor("Was 12,400")
        compose.onNodeWithText("Save").performClick()
        compose.waitUntil(5_000) { server.bodiesOf("PATCH inspections/aaaaaaaa-0000-0000-0000-000000000001").isNotEmpty() }
        val body = Json.parseToJsonElement(server.bodiesOf("PATCH inspections/aaaaaaaa-0000-0000-0000-000000000001").single()).jsonObject
        assertEquals(2, body["row_version"]!!.jsonPrimitive.int)
        assertEquals(12400, body["answers"]!!.jsonObject["inspection"]!!.jsonObject["odometer"]!!.jsonPrimitive.int)
    }

    @Test fun withoutSignalTheLastCopyShowsAndActionsLock() {
        show()
        waitFor("Rohit Sharma")
        server.stop()
        compose.onNode(androidx.compose.ui.test.hasContentDescription("Refresh", substring = true)).performClick()
        waitFor("Offline · as of")
        compose.onNodeWithText("Rohit Sharma").assertIsDisplayed()
        // the "No signal" message comes and goes; picture the screen once it has gone (same every run)
        compose.waitUntil(10_000) { compose.onAllNodes(hasText("No signal", substring = true)).fetchSemanticsNodes().isNotEmpty() }
        compose.waitUntil(10_000) { compose.onAllNodes(hasText("No signal", substring = true)).fetchSemanticsNodes().isEmpty() }
        shot("ops_today_offline")
    }

    @Test fun needsYouListsTheConflict() {
        server.on("GET bookings", """{"count":1,"results":[${day[2]}]}""")
        show()
        compose.waitUntil(5_000) { compose.onAllNodes(androidx.compose.ui.test.hasContentDescription("Notifications, ", substring = true)).fetchSemanticsNodes().isNotEmpty() }
        compose.onNode(androidx.compose.ui.test.hasContentDescription("Notifications, ", substring = true)).performClick()
        waitFor("Two experts inspected DEMO-14")
    }

    @Test fun theDashboardShowsThePeriodAndTheSplit() {
        show()
        compose.onNodeWithText("Dashboard").performClick()
        waitFor("8 more than before")
        compose.onNodeWithText("18").assertExists()
        compose.onNodeWithText("↑ 8 more than before").assertIsDisplayed()
        shot("ops_dashboard")
    }

    @Test fun aNewBookingIsCreatedFromTheBookingForm() {
        server.on("GET forms", """[{"id":1,"type":"booking","is_active":true,"published_version":{"id":2}}]""")
        server.on("GET form-versions/2", """{"id":2,"checks":[],"pages":[{"id":1,"title":"Page 1","visible":true,"gate":false,"sections":[{"id":1,"title":"Customer","visible":true,"fields":[
            {"key":"customer_name","label":"Customer name","type":"short_text","required":true,"visible":true,"config":{}},
            {"key":"city","label":"City","type":"master_list","required":true,"visible":true,"config":{"list":"city"}}]}]}]}""")
        server.on("POST bookings", """{"id":"$B4"}""")
        server.on("GET bookings/$B4", day[0])
        server.on("GET bookings/$B4/inspections", "[]")
        server.on("GET bookings/$B4/media", "[]")
        show()
        compose.onNodeWithText("Bookings").performClick()
        compose.onNodeWithContentDescription("New booking").performClick()
        waitFor("Customer name")
        compose.onNodeWithContentDescription("Customer name").performTextInput("Ananya Gupta")
        compose.onNodeWithText("Save").performClick()
        compose.waitUntil(5_000) { server.bodiesOf("POST bookings").isNotEmpty() }
        assertTrue(server.bodiesOf("POST bookings").single().contains("Ananya Gupta"))
    }
}
