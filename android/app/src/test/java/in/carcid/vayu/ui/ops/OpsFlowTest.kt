package `in`.carcid.vayu.ui.ops

import androidx.compose.foundation.background
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onLast
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.printToString
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
            "dashboards.view", "dashboards.export", "bookings.review_timing"))

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
             "scores":{"overall":{"word":"good","suggested_word":"good"},"ratings":{},"derived":{"seal":true},
               "key_checks":{"fuel":{"auto":"Petrol · Manual","value":"Petrol · Manual","edited":false},
                             "accident":{"auto":"None seen","value":"Front bumper repainted","edited":true}}},
             "answers":{"inspection":{"chassis_no":"MA3","odometer":12400,"bonnet":"ok","door":"ok"},"start":{},"end":{}}},
            {"id":"aaaaaaaa-0000-0000-0000-000000000002","expert":3,"status":"submitted","submitted_at":"2026-11-24T10:05:00Z","created_at":"2026-11-24T09:05:00Z",
             "row_version":1,"form_version":7,"start_version":null,"end_version":null,"overrides":{},"scores":{},"answers":{"inspection":{"chassis_no":"MA3"}}}]""")
        server.on("GET bookings/$B14/media", "[]")
        server.on("GET bookings/$B14/report", """{"code":"NO_REPORT","detail":"No report has been generated yet."}""", 404)
        server.on("GET form-versions/7", Fixtures.INSPECTION.replaceFirst("{\"id\":7,",
            "{\"id\":7,\"key_checks\":[{\"key\":\"fuel\",\"label\":\"Fuel and gearbox\",\"type\":\"linked\"},{\"key\":\"accident\",\"label\":\"Accident history\",\"type\":\"text\"}],"))
        // the real server's shape: {"rows": [...]}
        server.on("GET dashboards/volume", """{"rows":[{"period":"2026-W46","key":"pdi","count":12},{"period":"2026-W47","key":"pdi","count":10},
            {"period":"2026-W48","key":"pdi","count":14},{"period":"2026-W48","key":"ev","count":4}]}""")
        server.on("POST bookings/$B4/assign", "{}")
    }

    @After fun stop() = server.stop()

    private fun show(theme: ThemeMode = ThemeMode.LIGHT, user: Me = me) = compose.setContent {
        VayuTheme(theme) { OpsHome(user, data, { LocalDate.parse(TODAY) }, onProfile = {}) }
    }

    // 15 s: the first test in a cold test JVM loads much slower than the rest
    private fun waitFor(text: String) = compose.waitUntil(15_000) { compose.onAllNodes(hasText(text, substring = true)).fetchSemanticsNodes().isNotEmpty() }
    private fun shot(name: String) { settled(); compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/$name.png", roborazziOptions = options) }

    /**
     * The screen as it stays. Each part of an Ops screen loads on its own (produceState on IO threads,
     * which waitForIdle doesn't wait for), so a picture taken too early catches a part still loading:
     * wait until no request has reached the server and nothing on screen has changed for half a second.
     */
    private fun settled() {
        var last = ""; var since = System.currentTimeMillis()
        compose.waitUntil(10_000) {
            val now = server.requests.size.toString() + compose.onNode(isRoot()).printToString(Int.MAX_VALUE)
            if (now != last) { last = now; since = System.currentTimeMillis() }
            System.currentTimeMillis() - since >= 500
        }
    }

    @Test fun todayShowsTheDayUnassignedAndExperts() {
        show()
        waitFor("of 5 completed")
        compose.onNodeWithText("UNASSIGNED · 1").assertIsDisplayed()
        compose.onNodeWithText("Rohit Sharma").assertIsDisplayed()
        waitFor("Meera Expert")
        compose.onNode(hasText("Ravi Expert", substring = true)).performClick()          // expand: their jobs
        compose.onNodeWithText("Arjun Mehta").assertIsDisplayed()
        compose.onNodeWithText("3:30\u00A0pm").assertIsDisplayed()                       // the same 12-hour times as "Next at"
        shot("ops_today")
    }

    @Test fun backOnBookingsOrDashboardGoesToTodayFirst() {
        show()
        waitFor("of 5 completed")
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai")
        androidx.test.espresso.Espresso.pressBack()
        waitFor("of 5 completed")
        compose.onNodeWithText("UNASSIGNED · 1").assertIsDisplayed()
    }

    @Test fun theOpenBookingComesBackAfterAndroidClosedTheApp() {
        val restore = androidx.compose.ui.test.junit4.StateRestorationTester(compose)
        restore.setContent { VayuTheme(ThemeMode.LIGHT) { OpsHome(me, data, { LocalDate.parse(TODAY) }, onProfile = {}) } }
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai"); compose.onNodeWithText("Manoj Pillai").performClick()
        waitFor("2 Key Checks")
        restore.emulateSavedInstanceStateRestore()
        waitFor("2 Key Checks")                          // still on DEMO-14, not back on Today
    }

    /** F-223: signing an expert's phone out is offered only to someone whose role has the permission (off for Ops by default). */
    @Test fun signingAPhoneOutFollowsThePermission() {
        val allowed = androidx.compose.runtime.mutableStateOf(false)
        compose.setContent { VayuTheme(ThemeMode.LIGHT) {
            OpsHome(if (allowed.value) me.copy(permissions = me.permissions + "users.sign_out_devices") else me, data, { LocalDate.parse(TODAY) }, onProfile = {})
        } }
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai"); compose.onNodeWithText("Manoj Pillai").performClick()
        waitFor("2 Key Checks")
        compose.onNodeWithContentDescription("More actions").performClick()
        compose.onNodeWithText("Sign out the expert's phone").assertDoesNotExist()
        androidx.test.espresso.Espresso.pressBack()
        allowed.value = true
        compose.onNodeWithContentDescription("More actions").performClick()
        compose.onNodeWithText("Sign out the expert's phone").assertExists()
    }

    private val B6 = "00000000-0000-0000-0000-000000000006"
    private fun report(outOfDate: Boolean, allowed: Boolean, reason: String? = null) =
        """{"revision":2,"status":"ready","updating":false,"out_of_date":$outOfDate,
            "regenerate":{"allowed":$allowed,"reason":${reason?.let { "\"$it\"" } ?: "null"}},
            "generated_at":"2026-11-24T09:30:00+05:30","error":"","verify_url":"https://verify.example/x","url":"/api/v1/bookings/$B6/report/download"}"""
    private fun showReport() = compose.setContent { VayuTheme(ThemeMode.LIGHT) {
        val env = OpsEnv(me.copy(permissions = me.permissions + "submissions.edit"), data, Labels(), { LocalDate.parse(TODAY) }, 0, {}, {})
        // the app's background, not the test window's default (it changed with the library upgrade)
        androidx.compose.foundation.layout.Column(androidx.compose.ui.Modifier.background(`in`.carcid.vayu.ui.theme.Vayu.colors.bg).padding(20.dp)) {
            ReportCard(env, B6, Bk(Json.parseToJsonElement(day[3]).jsonObject))
        }
    } }

    /** Ops pass on the PDF only: the check link is printed in it, so the card has no button for it; one row of buttons. */
    @Test fun theReportCardHasOpenShareAndRegenerateInOneRow() {
        server.on("GET bookings/$B6/report", report(outOfDate = false, allowed = true))
        showReport()
        waitFor("Ready")
        compose.onNodeWithText("Open").assertExists()
        compose.onNodeWithText("Share").assertExists()
        compose.onNodeWithText("Check link").assertDoesNotExist()
        // the three buttons share one row, to save space
        val tops = listOf("Open", "Share", "Regenerate").map { compose.onNodeWithText(it).fetchSemanticsNode().boundsInRoot.top }
        assertEquals(1, tops.distinct().size)
    }

    /** F-219: a report out of date says so, and one tap on Regenerate sends one request, then shows the new state. */
    @Test fun anOutOfDateReportIsRegeneratedWithOneTap() {
        server.on("GET bookings/$B6/report", report(outOfDate = true, allowed = true))
        server.on("POST bookings/$B6/report/regenerate", "", 202)
        showReport()
        waitFor("Out of date")
        shot("ops_report_out_of_date")
        server.on("GET bookings/$B6/report", report(outOfDate = false, allowed = false, reason = "The report is being made.").replace("\"updating\":false", "\"updating\":true"))
        compose.onNodeWithText("Regenerate").performClick()
        compose.onAllNodes(hasText("Regenerat", substring = true)).onLast().performClick()   // a second tap while sending does nothing
        compose.waitUntil(5_000) { server.bodiesOf("POST bookings/$B6/report/regenerate").isNotEmpty() }
        waitFor("Updating…")
        assertEquals(1, server.bodiesOf("POST bookings/$B6/report/regenerate").size)
    }

    @Test fun regenerateSaysWhyWhenItCantBePressed() {
        server.on("GET bookings/$B6/report", report(outOfDate = true, allowed = false, reason = "Choose which inspection counts first."))
        showReport()
        waitFor("Choose which inspection counts first.")
        compose.onNodeWithText("Regenerate").assertIsNotEnabled()
    }

    @Test fun needsYouListsAReportOutOfDate() {
        server.on("GET problems/reports", """[{"booking":"$B6","booking_id":"DEMO-6","status":"ready","error":"","problem":"out_of_date","out_of_date_since":"${TODAY}T10:05:00+05:30","at":"${TODAY}T10:05:00+05:30"},
            {"booking":"$B14","booking_id":"DEMO-14","status":"failed","error":"Renderer crashed","problem":"failed","out_of_date_since":null,"at":"${TODAY}T09:15:00+05:30"}]""")
        server.on("GET bookings", """{"count":0,"results":[]}""")                     // nothing else needs Ops
        show()
        compose.waitUntil(5_000) { compose.onAllNodes(androidx.compose.ui.test.hasContentDescription("Notifications, ", substring = true)).fetchSemanticsNodes().isNotEmpty() }
        compose.onNode(androidx.compose.ui.test.hasContentDescription("Notifications, ", substring = true)).performClick()
        waitFor("Report out of date for DEMO-6")
        waitFor("TODAY")                                                          // grouped by the day it went wrong
        // when it went wrong, on this machine's clock (CI runs on UTC)
        fun clock(iso: String) = `in`.carcid.vayu.ui.clockOf(java.time.OffsetDateTime.parse(iso).atZoneSameInstant(java.time.ZoneId.systemDefault()))
        waitFor(clock("${TODAY}T10:05:00+05:30"))
        waitFor("Report failed for DEMO-14")                                      // a failed row stays a failure
        waitFor(clock("${TODAY}T09:15:00+05:30"))
    }

    /** F-222: a booking whose phone time wasn't checked says so, and Needs you lists this week's ones. */
    @Test fun anUnverifiedTimeIsShownOnTheBookingAndInNeedsYou() {
        val marked = day[2].replace("\"alerts\":[]", "\"alerts\":[],\"unverified_time\":true")
        server.on("GET bookings", """{"count":1,"results":[$marked]}""")
        server.on("GET bookings/$B14", marked)
        show()
        compose.waitUntil(15_000) { server.queries.any { "problem=unverified_time" in it && "date_from=2026-11-18" in it && "date_to=$TODAY" in it } }
        compose.waitUntil(15_000) { compose.onAllNodes(androidx.compose.ui.test.hasContentDescription("Notifications, ", substring = true)).fetchSemanticsNodes().isNotEmpty() }
        compose.onNode(androidx.compose.ui.test.hasContentDescription("Notifications, ", substring = true)).performClick()
        waitFor("DEMO-14: time not verified")
        compose.onNodeWithText("DEMO-14: time not verified").performClick()
        waitFor("Time not verified")
    }

    /** Today's filters are one line: a Status chip that opens the day's statuses with their counts; several can be ticked, like Experts. */
    @Test fun todayStatusChipNarrowsTheDayToSeveralStatuses() {
        show()
        waitFor("of 5 completed")
        compose.onNodeWithContentDescription("Status: any").performClick()
        compose.onNodeWithText("Unassigned · 1").assertExists()                       // each status says how many today
        compose.onNodeWithText("In progress · 1").performClick()
        compose.onNodeWithText("Done · 1 chosen").performClick()
        compose.waitUntil(5_000) { compose.onAllNodes(hasText("Rohit Sharma")).fetchSemanticsNodes().isEmpty() }   // unassigned hidden
        waitFor("Ravi Expert")                       // the list reloads after the chip: wait for the row
        compose.onNode(hasText("Ravi Expert", substring = true)).performClick()
        waitFor("Farhan Ali")                                                           // in progress
        assertTrue(compose.onAllNodes(hasText("Arjun Mehta")).fetchSemanticsNodes().isEmpty())   // assigned: not listed
        assertTrue(compose.onAllNodes(hasText("Meera Expert")).fetchSemanticsNodes().isEmpty())  // nothing in progress
        shot("ops_today_in_progress")
        compose.onNodeWithContentDescription("Status: In progress").performClick()
        compose.onNodeWithText("Unassigned · 1").performClick()                        // a second status on top
        compose.onNodeWithText("Done · 2 chosen").performClick()
        waitFor("Rohit Sharma")                                                         // unassigned is back
        waitFor("Farhan Ali")                                                           // in progress still there
        assertTrue(compose.onAllNodes(hasText("Arjun Mehta")).fetchSemanticsNodes().isEmpty())   // assigned: still not listed
        compose.onNodeWithContentDescription("Status: 2 chosen").performClick()
        compose.onNodeWithText("Any status").performClick()
        waitFor("Meera Expert")                                                         // everything again
    }

    /** A list the server refuses says why, instead of "Loading…" for ever (seen on the phone with a stale server). */
    @Test fun aRefusedBookingsListSaysWhy() {
        server.on("GET bookings", """{"expert":"Use a user id."}""", 400)     // refused from the start: no earlier copy to show
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Use a user id.")
        assertEquals(0, compose.onAllNodes(hasText("Loading…")).fetchSemanticsNodes().size)
    }

    @Test fun todayExpertsChipKeepsOnlyTheChosenExperts() {
        show()
        waitFor("of 5 completed")
        compose.onNodeWithContentDescription("Experts: any").performClick()
        compose.onAllNodes(hasText("Ravi Expert")).onLast().performClick()             // the row in the sheet, over the list
        compose.onNodeWithText("Done · 1 chosen").performClick()
        compose.waitUntil(5_000) { compose.onAllNodes(hasText("Meera Expert")).fetchSemanticsNodes().isEmpty() }
        assertTrue(compose.onAllNodes(hasText("Rohit Sharma")).fetchSemanticsNodes().isEmpty())   // nobody's yet: not this expert's
        compose.onNodeWithContentDescription("Experts: 1 chosen").assertIsDisplayed()
        compose.onNode(hasText("Ravi Expert", substring = true)).assertExists()
        // the two chips together can leave nothing: the screen says so and one tap shows the whole day again
        compose.onNodeWithContentDescription("Status: any").performClick()
        compose.onNodeWithText("Completed · 1").performClick()
        compose.onNodeWithText("Done · 1 chosen").performClick()
        waitFor("No bookings today match these filters.")
        compose.onNodeWithText("Show all").performClick()
        waitFor("Meera Expert")
    }

    @Test fun quickFiltersAndTheFilterViewAreOneChoice() {
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Showing 5 · Today")
        assertTrue(server.queries.any { it.startsWith("date_from=$TODAY&date_to=$TODAY&order=schedule") })   // today by default
        // Status takes several, like Experts: tick two, Done
        compose.onNodeWithContentDescription("Status: any").performClick()
        compose.onAllNodes(hasText("Assigned")).onLast().performClick()               // the sheet, over the list
        compose.onAllNodes(hasText("In progress")).onLast().performClick()
        compose.onNodeWithText("Done · 2 chosen").performClick()
        waitFor("Today · 2 statuses")
        compose.waitUntil(5_000) { server.queries.any { "stage=assigned,in_progress" in it } }
        compose.onNodeWithContentDescription("Status: 2 chosen").performClick()
        compose.onAllNodes(hasText("In progress")).onLast().performClick()            // untick: one status reads as its word
        compose.onNodeWithText("Done · 1 chosen").performClick()
        waitFor("Today · Assigned")
        compose.waitUntil(5_000) { server.queries.any { "stage=assigned&" in "$it&" } }
        compose.onNodeWithContentDescription("Experts: any").performClick()
        compose.onNodeWithText("Ravi Expert").performClick()
        compose.onNodeWithText("Meera Expert").performClick()
        compose.onNodeWithText("Done · 2 chosen").performClick()
        // what the person sees first, then the request: under Robolectric with Compose 1.11 the list
        // behind a closed sheet redraws only once the screen is read (on a phone the request leaves in
        // 0.2-0.4 s, checked 15 times on the OnePlus)
        waitFor("Today · Assigned · 2 experts")
        compose.waitUntil(5_000) { server.queries.any { "stage=assigned" in it && "expert=3,4" in it } }
        compose.onNodeWithContentDescription("All filters, 2 on").assertIsDisplayed()
        shot("ops_bookings_quick")
        // the Filter view starts from the same choices
        compose.onNodeWithContentDescription("All filters, 2 on").performClick()
        compose.onAllNodes(androidx.compose.ui.test.hasContentDescription("Status: Assigned")).onLast().assertIsDisplayed()   // the sheet's box
        compose.onNodeWithContentDescription("Experts: Ravi Expert, Meera Expert").assertIsDisplayed()
        compose.onNodeWithContentDescription("Inspection type: any").assertIsDisplayed()
        com.github.takahirom.roborazzi.captureScreenRoboImage("src/test/screenshots/ops_filter_view.png", roborazziOptions = options)   // the sheet over the list
        compose.onNodeWithText("Upcoming").performClick()
        compose.onNodeWithContentDescription("Remove Status").performClick()
        compose.onNodeWithText("Show bookings").performClick()
        waitFor("Upcoming · 2 experts")                                            // what the person sees first
        compose.waitUntil(5_000) { server.queries.any { it.startsWith("date_from=2026-11-25&order=schedule") && "expert=3,4" in it && "stage" !in it } }
        compose.onNodeWithContentDescription("Status: any").assertIsDisplayed()       // and back in the quick row
        compose.onNodeWithText("Clear").performClick()
        waitFor("Showing 5 · Today")
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

    @Test fun bookingsListsUnassignedFirst() {
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("UNASSIGNED · 1")
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
        // the same picture every run: wait for the forms (not "Loading…")
        compose.waitUntil(5_000) { compose.onAllNodes(hasText("Loading…")).fetchSemanticsNodes().isEmpty() }
        shot("ops_booking")
        compose.onNodeWithText("Waits for your choice above").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("Compare and choose").performClick()
        waitFor("Which inspection counts?")
        compose.onNode(hasText("· good", substring = true)).performClick()            // Meera's: 4 answers, rated good
        compose.onNodeWithText("Keep this one").performClick()
        compose.waitUntil(5_000) { server.bodiesOf("POST bookings/$B14/resolve-conflict").isNotEmpty() }
        assertTrue(server.bodiesOf("POST bookings/$B14/resolve-conflict").single().contains("aaaaaaaa-0000-0000-0000-000000000001"))
    }

    /** Payment is ordinary wrap-up answers (REQUIREMENTS 5.2): the booking screen has no payment section of its own. */
    @Test fun theBookingScreenHasNoPaymentSection() {
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai"); compose.onNodeWithText("Manoj Pillai").performClick()
        waitFor("Inspection Data"); waitFor("2 Key Checks")
        compose.onNodeWithText("PAYMENT").assertDoesNotExist()
        compose.onNodeWithText("Not answered yet").assertDoesNotExist()
    }

    @Test fun anAnswerIsChangedWithItsRowVersion() {
        server.on("PATCH inspections/aaaaaaaa-0000-0000-0000-000000000001", "{}")
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai"); compose.onNodeWithText("Manoj Pillai").performClick()
        waitFor("Inspection Data"); compose.onNodeWithText("Inspection Data").performScrollTo().performClick()
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

    /** The page list names every page of Check-in, Inspection and Wrap-up, numbered across all three; a page in another tab opens that tab. */
    @Test fun thePageListCoversCheckInInspectionAndWrapUp() {
        server.on("GET bookings/$B14/inspections", """[{"id":"aaaaaaaa-0000-0000-0000-000000000001","expert":4,"status":"submitted",
            "submitted_at":"2026-11-24T10:40:00Z","created_at":"2026-11-24T09:00:00Z","row_version":2,"form_version":7,"start_version":1,"end_version":9,
            "overrides":{},"scores":{},"answers":{"start":{"travel":"bike"},"inspection":{"chassis_no":"MA3","odometer":12400,"bonnet":"ok","door":"minor"},"end":{}}}]""")
        server.on("GET form-versions/1", Fixtures.START)
        server.on("GET form-versions/9", Fixtures.END)
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai"); compose.onNodeWithText("Manoj Pillai").performClick()
        waitFor("Inspection Data"); compose.onNodeWithText("Inspection Data").performScrollTo().performClick()
        waitFor("Chassis number")
        compose.onNodeWithText("page 2 of 4").assertExists()          // Vehicle: the second page of the whole inspection
        compose.onNodeWithText("Only problems · 1").assertExists()
        compose.onNodeWithContentDescription("Jump to a page").performClick()
        waitFor("Pages")
        listOf("1. Check-in", "2. Vehicle", "3. Exterior", "4. Wrap-up").forEach { compose.onNodeWithText(it).assertExists() }
        compose.onNodeWithText("Not filled yet").assertExists()      // only Wrap-up has no answers
        compose.onNodeWithText("4. Wrap-up").performClick()
        waitFor("Taking payment?")
        compose.onNodeWithText("page 4 of 4").assertExists()
        // "Only problems" is one switch for the whole inspection: the count stays on a tab with no problems
        compose.onNodeWithText("Only problems · 1").assertExists()
    }

    @Test fun keyChecksAreTypedOverAndResetOnReview() {
        server.on("PATCH inspections/aaaaaaaa-0000-0000-0000-000000000001/overrides", "{}")
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai"); compose.onNodeWithText("Manoj Pillai").performClick()
        waitFor("2 Key Checks"); compose.onNode(hasText("2 Key Checks", substring = true)).performScrollTo().performClick()
        waitFor("Accident history")
        compose.onNodeWithText("Edited").assertIsDisplayed()
        compose.onNodeWithText("Automatic: None seen · ").assertIsDisplayed()
        shot("ops_review")
        compose.onNodeWithText("Reset to automatic").performClick()
        compose.onNodeWithContentDescription("Fuel and gearbox").performTextInput("Diesel · ")
        compose.onNodeWithText("Save").performClick()
        compose.waitUntil(5_000) { server.bodiesOf("PATCH inspections/aaaaaaaa-0000-0000-0000-000000000001/overrides").isNotEmpty() }
        val body = Json.parseToJsonElement(server.bodiesOf("PATCH inspections/aaaaaaaa-0000-0000-0000-000000000001/overrides").single()).jsonObject
        assertEquals(2, body["row_version"]!!.jsonPrimitive.int)
        val kc = body["key_checks"]!!.jsonObject
        assertEquals("Diesel · Petrol · Manual", kc["fuel"]!!.jsonPrimitive.content)
        assertTrue(kc["accident"] is kotlinx.serialization.json.JsonNull)
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

    @Test fun aLateStartIsListedAndMarkedReviewed() {
        val late = day[1].trimEnd().removeSuffix("}") + ""","timing":{"late_minutes":40,"duration_minutes":null,"late":true,"quick":false,"min_minutes":30,
            "grace_minutes":15,"late_reviewed_by":null,"late_reviewed_at":null,"quick_reviewed_by":null,"quick_reviewed_at":null}}"""
        server.on("GET bookings", """{"count":1,"results":[$late]}""")
        server.on("GET bookings/$B8", late)
        server.on("POST bookings/$B8/timing-review", late)
        show(user = me.copy(permissions = me.permissions + "bookings.review_timing"))
        compose.waitUntil(5_000) { compose.onAllNodes(androidx.compose.ui.test.hasContentDescription("Notifications, ", substring = true)).fetchSemanticsNodes().isNotEmpty() }
        compose.onNode(androidx.compose.ui.test.hasContentDescription("Notifications, ", substring = true)).performClick()
        waitFor("DEMO-8: started 40 min late")
        compose.onNodeWithText("Started late").assertIsDisplayed()               // its category under the title
        compose.onNodeWithText("11:40", substring = true).assertIsDisplayed()     // booked 11:00, started 40 min late
        compose.onNodeWithText("DEMO-8: started 40 min late").performClick()
        waitFor("Limit: start within 15 min of the booked time.")
        shot("ops_booking_late")
        compose.onNodeWithText("Mark reviewed").performClick()
        compose.waitUntil(5_000) { server.bodiesOf("POST bookings/$B8/timing-review").isNotEmpty() }
        assertEquals("late", Json.parseToJsonElement(server.bodiesOf("POST bookings/$B8/timing-review").single()).jsonObject["flag"]!!.jsonPrimitive.content)
    }

    @Test fun aReviewedFlagIsCalmAndTheOtherStaysOpen() {
        val both = day[1].trimEnd().removeSuffix("}") + ""","timing":{"late_minutes":40,"duration_minutes":25,"late":true,"quick":true,"min_minutes":45,
            "grace_minutes":15,"late_reviewed_by":"priya","late_reviewed_at":"2026-11-24T10:44:00+05:30","quick_reviewed_by":null,"quick_reviewed_at":null}}"""
        server.on("GET bookings", """{"count":1,"results":[$both]}""")
        server.on("GET bookings/$B8", both)
        show(user = me.copy(permissions = me.permissions + "bookings.review_timing"))
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Farhan Ali"); compose.onNodeWithText("Farhan Ali").performClick()
        waitFor("Limit: take at least 45 min.")
        compose.onNode(hasText("Started 40 min late · Reviewed by Priya Ops", substring = true)).assertIsDisplayed()
        compose.onAllNodes(hasText("Took 25 min (min 45)")).fetchSemanticsNodes().let { assertEquals(2, it.size) }   // header tag + box
        shot("ops_booking_timing_reviewed")
    }

    @Test fun theDashboardShowsThePeriodAndTheSplit() {
        server.on("GET dashboards/summary", """{"date_from":"2026-11-18","date_to":"2026-11-24",
            "period":{"bookings":30,"completed":18,"cancelled":2,"completion_rate":64.3,"avg_minutes":42,"on_time":81,"late":3,"late_pct":19,"quick":1,"quick_pct":6},
            "previous":{"bookings":5,"completed":6,"cancelled":2,"completion_rate":58.0,"avg_minutes":45,"on_time":85,"late":1,"late_pct":5,"quick":0,"quick_pct":0},
            "by_expert":[{"expert":3,"bookings":6,"completed":4,"cancelled":0,"completion_rate":66.7,"avg_minutes":40,"on_time":50,"late":2,"late_pct":50,"quick":1,"quick_pct":25}]}""")
        show()
        compose.onNodeWithText("Dashboard").performClick()
        waitFor("Started late")
        compose.onNodeWithText("↑ 25").assertIsDisplayed()          // 30 bookings against 5
        compose.onNodeWithText("2 late").assertExists()
        shot("ops_dashboard")
        // a tile opens the bookings behind its number
        compose.onNodeWithText("Started late").performClick()
        waitFor("Showing")
    }

    /** F-202: photo tiles share the full width (no empty quarter on the right). */
    @Test fun photoTilesFillTheWidth() {
        server.on("GET form-versions/7", """{"id":7,"checks":[],"pages":[{"id":1,"title":"Photos","visible":true,"gate":false,"sections":[{"id":1,"title":"Outside","visible":true,
            "fields":[{"key":"front","label":"Front","type":"photo","visible":true,"config":{"max_count":8}}]}]}]}""")
        server.on("GET bookings/$B14/media", (1..8).joinToString(",", "[", "]") {
            """{"id":"bbbbbbbb-0000-0000-0000-00000000000$it","field_key":"front","kind":"photo","status":"verified"}""" })
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai"); compose.onNodeWithText("Manoj Pillai").performClick()
        waitFor("Photos and videos"); compose.onNodeWithText("Photos and videos").performScrollTo().performClick()
        waitFor("8 photos")
        compose.waitUntil(5_000) { compose.onAllNodes(androidx.compose.ui.test.hasContentDescription("photo front")).fetchSemanticsNodes().size == 8 }
        val tiles = compose.onAllNodes(androidx.compose.ui.test.hasContentDescription("photo front")).fetchSemanticsNodes().map { it.boundsInRoot }
        val width = compose.onNode(isRoot()).fetchSemanticsNode().boundsInRoot.width
        val gap = width - tiles.maxOf { it.right } - tiles.minOf { it.left }       // right margin minus left margin
        assertTrue("tiles leave ${gap}px empty on the right: $tiles in $width", kotlin.math.abs(gap) < 4f)
    }

    @Test fun aSubmittedPhotoCanBeReplacedOrAddedToButNotDeleted() {
        // one photo question (up to 2) with one photo the expert sent
        server.on("GET form-versions/7", """{"id":7,"checks":[],"pages":[{"id":1,"title":"Photos","visible":true,"gate":false,"sections":[{"id":1,"title":"Outside","visible":true,
            "fields":[{"key":"front","label":"Front","type":"photo","visible":true,"config":{"max_count":2}}]}]}]}""")
        server.on("GET bookings/$B14/media", """[{"id":"bbbbbbbb-0000-0000-0000-000000000001","field_key":"front","kind":"photo","status":"verified"}]""")
        show()
        compose.onNodeWithText("Bookings").performClick()
        waitFor("Manoj Pillai"); compose.onNodeWithText("Manoj Pillai").performClick()
        waitFor("Photos and videos"); compose.onNodeWithText("Photos and videos").performScrollTo().performClick()
        waitFor("+ Front")
        compose.onNode(androidx.compose.ui.test.hasContentDescription("photo front")).performClick()
        waitFor("Replace")
        compose.onNodeWithText("Add").assertExists()
        assertTrue(compose.onAllNodes(hasText("Delete")).fetchSemanticsNodes().isEmpty())
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
        waitFor("Showing 5")                                                    // New booking works once the list is in (online)
        compose.onNodeWithContentDescription("New booking").performClick()
        waitFor("Customer name")
        compose.onNodeWithContentDescription("Customer name").performTextInput("Ananya Gupta")
        compose.onNodeWithText("Save").performClick()
        compose.waitUntil(15_000) { server.bodiesOf("POST bookings").isNotEmpty() }   // slow under a full run
        assertTrue(server.bodiesOf("POST bookings").single().contains("Ananya Gupta"))
    }

    @Test fun bookingsFilterByAnAnswerSuchAsAPaymentNotYetVerified() {
        server.on("GET bookings/answer-fields", """[{"field":"end.payment_verified","label":"Payment verified?","type":"single_choice","form":"Wrap-up",
            "options":[{"value":"verified","label":"Verified"},{"value":"mismatch","label":"Mismatch"}]}]""")
        show(user = me.copy(permissions = me.permissions + "submissions.view"))
        compose.onNodeWithText("Bookings").performClick()
        compose.onNodeWithContentDescription("All filters").performClick()
        waitFor("Any type")
        assertEquals(0, compose.onAllNodes(hasText("Answer")).fetchSemanticsNodes().size)   // only once a type is picked
        compose.onNodeWithContentDescription("Inspection type: any").performClick()
        compose.onNodeWithText("PDI").performClick()
        waitFor("Any question")                                                   // that type's questions, no form name in front
        compose.waitUntil(5_000) { server.queries.contains("type=pdi") }
        compose.onNodeWithContentDescription("Answer: any").performScrollTo().performClick()
        compose.onNodeWithText("Payment verified?").performClick()
        compose.onNodeWithText("Not filled").performClick()                       // its answers open straight after
        compose.onNodeWithText("Show bookings").performClick()
        waitFor("Payment verified?: Not filled")
        compose.waitUntil(5_000) { server.queries.any { "type=pdi" in it && "answer=end.payment_verified&value=__none__" in it } }   // the label shows before the request lands
        compose.onNodeWithContentDescription("All filters, 2 on").assertExists()   // type, and the answer with its value
    }

    @Test fun theAnswerFilterIsNotOfferedWithoutSeeingAnswers() {
        show()
        compose.onNodeWithText("Bookings").performClick()
        compose.onNodeWithContentDescription("All filters").performClick()
        compose.onNodeWithContentDescription("Inspection type: any").performClick()
        compose.onNodeWithText("PDI").performClick()
        waitFor("Any city")
        assertEquals(0, compose.onAllNodes(hasText("Answer")).fetchSemanticsNodes().size)
        assertTrue(server.requests.none { it.first == "GET bookings/answer-fields" })
    }
}
