package `in`.carcid.vayu.ui.expert

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.onLast
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.auth.MemoryTokenStore
import `in`.carcid.vayu.core.sync.Job
import `in`.carcid.vayu.core.sync.JobStore
import `in`.carcid.vayu.core.sync.job
import `in`.carcid.vayu.core.sync.payload
import `in`.carcid.vayu.ui.AppViewModel
import `in`.carcid.vayu.ui.components.Tone
import `in`.carcid.vayu.ui.theme.ThemeMode
import `in`.carcid.vayu.ui.theme.VayuTheme
import `in`.carcid.vayu.core.api.FakeServer
import `in`.carcid.vayu.core.api.testGraph
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.nio.file.Files
import java.time.LocalDate

@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w390dp-h844dp-xxhdpi", sdk = [34])
class MyJobsTest {
    @get:Rule val compose = createComposeRule()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))
    private val today = LocalDate.parse("2026-11-24")
    private val me = Me(3, "ravi", "Ravi Arora", "expert", false, "light")

    private fun j(id: String, name: String, time: String, stage: String = "assigned", date: String = "2026-11-24") =
        Job(id, "DEMO-$id", stage, name, "+919876500000", "DEMO-$id demo street", "Pune", "Tata Nexon", "PDI",
            date, time, assignedToMe = true, myDraft = null, versions = mapOf("inspection" to 7))

    private val jobs = listOf(
        j("8", "Farhan Ali", "11:00", "in_progress"), j("2", "Arjun Mehta", "15:30"),
        j("15", "Neha Bhat", "17:00"), j("10", "Imran Qureshi", "09:30", "submitted"),
        j("21", "Kavya Rao", "10:00", date = "2026-11-26"), j("4", "Dev Malhotra", "12:00", "completed", "2026-11-22"),
    ).sortedWith(compareBy({ it.date }, { it.time }))

    private fun show(state: JobsState, theme: ThemeMode = ThemeMode.LIGHT) = compose.setContent {
        VayuTheme(theme) { ExpertHome(me, state, today, {}, {}) }
    }

    @Test fun myJobsMatchesTheDesign() {
        show(JobsState(jobs, ready = jobs.map { it.id }.toSet()))
        compose.onNodeWithText("Today · 4").assertIsDisplayed()
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/my_jobs.png", roborazziOptions = options)
    }

    @Test fun myJobsInDark() {
        show(JobsState(jobs), ThemeMode.DARK)
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/my_jobs_dark.png", roborazziOptions = options)
    }

    @Test fun tabsSplitTodayUpcomingAndDone() {
        show(JobsState(jobs))
        compose.onNodeWithText("Upcoming").performClick()
        compose.onNodeWithText("Kavya Rao").assertIsDisplayed()
        assertEquals(0, compose.onAllNodes(hasText("Arjun Mehta")).fetchSemanticsNodes().size)
        compose.onNodeWithText("Completed").performClick()
        compose.onNodeWithText("Dev Malhotra").assertIsDisplayed()
    }

    @Test fun searchFindsByBookingIdOrCustomer() {
        show(JobsState(jobs))
        compose.onNodeWithContentDescription("Booking ID or customer").performTextInput("demo-15")
        compose.onNodeWithText("Neha Bhat").assertIsDisplayed()
        assertEquals(0, compose.onAllNodes(hasText("Farhan Ali")).fetchSemanticsNodes().size)
    }

    @Test fun aJobMovedAwayShowsOnlyWhileThePhoneHoldsWorkForIt() {
        val moved = j("42", "Zoya Merchant", "20:45").copy(assignedToMe = false)
        val draft = `in`.carcid.vayu.core.draft.Draft("42", "DEMO-42", "Zoya Merchant", emptyMap(), "tour")
        val held = androidx.compose.runtime.mutableStateOf(false)
        compose.setContent { VayuTheme(ThemeMode.LIGHT) {
            ExpertHome(me, JobsState(jobs + moved), today, {}, {}, ExpertExtras(drafts = if (held.value) mapOf("42" to draft) else emptyMap()))
        } }
        assertEquals(0, compose.onAllNodes(hasText("Zoya Merchant")).fetchSemanticsNodes().size)
        held.value = true
        compose.onNodeWithText("Zoya Merchant").assertIsDisplayed()
        compose.onNodeWithText("Submit anyway").assertIsDisplayed()
        compose.onNodeWithText("Discard draft").assertIsDisplayed()
    }

    @Test fun discardingADraftFromTheListOrTheLeadAsksFirst() {
        val moved = j("42", "Zoya Merchant", "20:45").copy(assignedToMe = false)
        val draft = `in`.carcid.vayu.core.draft.Draft("42", "DEMO-42", "Zoya Merchant", emptyMap(), "tour")
        val gone = mutableListOf<String>()
        compose.setContent { VayuTheme(ThemeMode.LIGHT) {
            ExpertHome(me, JobsState(jobs + moved), today, {}, {}, ExpertExtras(drafts = mapOf("42" to draft), onDiscard = { gone += it }))
        } }
        compose.onNodeWithText("Discard draft").performClick()
        compose.onNodeWithText("Discard DEMO-42?").assertIsDisplayed()
        compose.onNodeWithText("Keep it").performClick()
        assertEquals(emptyList<String>(), gone)
        compose.onNodeWithText("Zoya Merchant").performClick()              // the lead page asks too
        compose.onNodeWithText("Discard draft").performClick()
        assertEquals(emptyList<String>(), gone)
        compose.onAllNodes(hasText("Discard draft")).onLast().performClick()  // the dialog's button
        assertEquals(listOf("42"), gone)
    }

    @Test fun aCancelledLeadSaysSoAndWhy() {
        val gone = j("42", "Zoya Merchant", "20:45", stage = "cancelled").copy(cancelReason = "Customer cancelled")
        val draft = `in`.carcid.vayu.core.draft.Draft("42", "DEMO-42", "Zoya Merchant", emptyMap(), "tour")
        compose.setContent { VayuTheme(ThemeMode.LIGHT) {
            JobDetailScreen(gone, ready = true, today = today, onBack = {}, onStart = {}, draft = draft)
        } }
        compose.onNodeWithText("Cancelled").assertIsDisplayed()
        compose.onNodeWithText("Ops cancelled this lead: Customer cancelled.").assertIsDisplayed()
        assertEquals(0, compose.onAllNodes(hasText("Ready to work without signal")).fetchSemanticsNodes().size)
    }

    @Test fun theSubmittedScreenSaysFilesKeepSendingOnlyWhileSomeAreLeft() {
        fun f(sent: Boolean) = `in`.carcid.vayu.core.draft.LocalFile("p", "inspection", "door", "photo", "p", "image/jpeg", "camera", 1, "x", "Door", sent = sent)
        val left = androidx.compose.runtime.mutableStateOf(true)
        compose.setContent { VayuTheme(ThemeMode.LIGHT) {
            SubmittedScreen(`in`.carcid.vayu.core.draft.Draft("42", "DEMO-42", "Zoya Merchant", emptyMap(), "tour",
                files = listOf(f(true), f(!left.value)), submitSent = true), onClose = {})
        } }
        compose.onNodeWithText("They keep sending in the background, even with the app closed.").assertIsDisplayed()
        left.value = false
        compose.onNodeWithText("All files sent").assertIsDisplayed()
        assertEquals(0, compose.onAllNodes(hasText("They keep sending", substring = true)).fetchSemanticsNodes().size)
    }

    @Test fun aFieldOpensTheCameraTheFormBuilderChose() {
        fun f(cfg: Map<String, Any?>) = `in`.carcid.vayu.core.forms.Field("p", "P", "photo", "", false, null, null, true, "edit", cfg)
        assertEquals(true, firstCameraIsBack(f(emptyMap())))                 // Back by default
        assertEquals(false, firstCameraIsBack(f(mapOf("camera" to "front"))))
        assertEquals(true, firstCameraIsBack(f(mapOf("camera" to "back"))))
        val oldSelfie = `in`.carcid.vayu.core.forms.Field("selfie", "Selfie at the car", "photo", "", true, null, null, true, "edit", emptyMap())
        assertEquals(false, firstCameraIsBack(oldSelfie))                    // saved before the setting: Front
    }

    @Test fun offlineShowsTheStripWithTheSavedTime() {
        show(JobsState(jobs, offline = true, syncedAt = "10:42"))
        compose.onNodeWithText("Offline · as of 10:42").assertIsDisplayed()
    }

    @Test fun jobDetailsMatchTheDesign() {
        show(JobsState(jobs, ready = setOf("2")))
        compose.onNodeWithText("Arjun Mehta").performClick()
        compose.onNodeWithText("DEMO-2").assertIsDisplayed()
        compose.onNodeWithText("Today, 3:30\u00A0pm").assertIsDisplayed()
        compose.onNodeWithText("Ready to work without signal").assertIsDisplayed()
        compose.onNodeWithText("Start inspection").assertIsDisplayed()
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/job_detail.png", roborazziOptions = options)
        compose.onNodeWithContentDescription("Back to My leads").performClick()
        compose.onNodeWithText("Today · 4").assertIsDisplayed()
    }

    @Test fun aScanOffersTheLongestRunsFirst() {
        assertEquals(listOf("MA3YPKCSKTJ273129", "MA3YPK"), scanCandidates(listOf("VIN: MA3YPKCSKTJ273129", "MA3YPK")).take(2))
        assertEquals(emptyList<String>(), scanCandidates(listOf("AB 12", "--")))
    }

    @Test fun aThemeChosenWithoutSignalIsKeptAndSentLater() {
        val server = FakeServer()
        val tokens = MemoryTokenStore()
        server.on("POST auth/login", """{"access":"A","refresh":"R"}""")
        server.on("GET auth/me", """{"id":3,"username":"ravi","name":"Ravi","role":"expert","must_change_password":false,"theme":"light"}""")
        server.on("POST devices/heartbeat", """{"min_app_version":1}""")
        server.on("GET sync/jobs", payload(job("2")).toString())
        val vm = AppViewModel(testGraph(server, tokens), "Test phone")
        // the app's logic alone (no screen): run the main thread until [done] or 5 s
        fun until(done: () -> Boolean) {
            val end = System.currentTimeMillis() + 5_000
            while (!done() && System.currentTimeMillis() < end) { org.robolectric.shadows.ShadowLooper.idleMainLooper(); Thread.sleep(20) }
            assertTrue("timed out; requests: ${server.requests.map { it.first }} me=${tokens.me()}", done())
        }
        until { vm.screen.value is `in`.carcid.vayu.ui.Screen.SignIn }
        vm.signIn("ravi", "pw")
        until { vm.screen.value is `in`.carcid.vayu.ui.Screen.Home && vm.jobs.state.value.jobs.isNotEmpty() && !vm.jobs.state.value.syncing }
        server.on("PATCH auth/me/profile", """{"detail":"down"}""", 503)                 // no signal
        vm.openProfile(); vm.setTheme("dark")
        until { server.bodiesOf("PATCH auth/me/profile").isNotEmpty() }
        assertEquals("dark", (vm.screen.value as `in`.carcid.vayu.ui.Screen.Profile).me.theme)   // the look changed at once
        assertEquals("true", tokens.me()!!["theme_pending"])
        server.on("PATCH auth/me/profile", """{"id":3,"username":"ravi","name":"Ravi","role":"expert","theme":"dark"}""")
        vm.closeProfile(); vm.jobs.sync()                                                  // signal back: sent with the next sync
        until { tokens.me()!!["theme_pending"] == "false" }
        assertTrue(server.bodiesOf("PATCH auth/me/profile").last().contains("dark"))
        server.stop()
    }

    @Test fun phoneStorageIsUnderAppSettingsInTheProfile() {
        var freed = 0
        compose.setContent {
            VayuTheme(ThemeMode.LIGHT) {
                `in`.carcid.vayu.ui.ProfileScreen(`in`.carcid.vayu.ui.Screen.Profile(me), {}, {}, {},
                    storage = { StorageInfo(18L shl 30, 300L shl 20, 2) { freed++; 300L shl 20 } })
            }
        }
        compose.onNodeWithText("App settings").performClick()
        compose.onNodeWithText("Phone storage").performClick()
        compose.onNodeWithText("Removes 300 MB of photos already sent.").assertIsDisplayed()
        compose.onNodeWithText("Free up").performClick()
        compose.onAllNodes(hasText("Free up"))[1].performClick()                        // confirm in the dialog
        assertEquals(1, freed)
        compose.onNodeWithText("Nothing to remove right now.").assertIsDisplayed()
    }

    @Test fun labelsAndTabs() {
        assertEquals("+91 98765 00000", phoneLabel("+919876500000")); assertEquals("0201234", phoneLabel("0201234"))
        assertEquals("3:30\u00A0pm", time12("15:30")); assertEquals("12:05\u00A0pm", time12("12:05")); assertEquals("12:00\u00A0am", time12("00:00"))
        assertEquals("Tomorrow", dayLabel("2026-11-25", today)); assertEquals("Mon 30 Nov", dayLabel("2026-11-30", today))
        assertEquals(JobTab.TODAY, tabOf(j("1", "x", "09:00", date = "2026-11-20"), today))     // overdue
        assertEquals("Reassigned" to Tone.BAD, statusOf(j("1", "x", "09:00").copy(assignedToMe = false)))
    }

    @Test fun signingInDownloadsJobsAndTheyStayWhenSignalDrops() = signInThen(revoke = false)

    @Test fun aPhoneSignedOutByTheServerForgetsItsJobs() = signInThen(revoke = true)

    private fun signInThen(revoke: Boolean) {
        val server = FakeServer()
        val dir = Files.createTempDirectory("vayu").toFile()
        val file = File(dir, "jobs-3.json")
        server.on("POST auth/login", """{"access":"A","refresh":"R"}""")
        server.on("GET auth/me", """{"id":3,"username":"ravi","name":"Ravi","role":"expert","must_change_password":false,"theme":"light"}""")
        server.on("POST devices/heartbeat", """{"min_app_version":1}""")
        server.on("GET sync/jobs", payload(job("2"), forms = """{"7":{"pages":[]}}""").toString())
        val vm = AppViewModel(testGraph(server, root = dir), "Test phone")
        compose.setContent { `in`.carcid.vayu.AppRoot(vm) }
        compose.onNodeWithContentDescription("Username").performTextInput("ravi")
        compose.onNodeWithContentDescription("Password").performTextInput("pw")
        compose.onNode(hasText("Sign in") and androidx.compose.ui.test.hasClickAction()).performClick()
        compose.waitUntil(5_000) { compose.onAllNodes(hasText("Arjun Mehta")).fetchSemanticsNodes().isNotEmpty() }
        if (revoke) {
            server.on("GET sync/jobs", """{"code":"DEVICE_REVOKED","detail":"Signed out."}""", 401)
            compose.onNode(androidx.compose.ui.test.hasContentDescription("Refresh", substring = true)).performClick()
            compose.waitUntil(5_000) { compose.onAllNodes(hasText("Welcome back", substring = true)).fetchSemanticsNodes().isNotEmpty() }
            assertEquals(false, file.exists())                          // nothing of theirs stays on the phone
        } else {
            server.on("GET sync/jobs", """{"detail":"Server error"}""", 502)   // server down: same as no signal
            compose.onNode(androidx.compose.ui.test.hasContentDescription("Refresh", substring = true)).performClick()
            compose.waitUntil(5_000) { compose.onAllNodes(hasText("Offline", substring = true)).fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithText("Arjun Mehta").assertIsDisplayed()
        }
        server.stop()
    }

    @Test fun reopeningWithTheServerDownStillShowsTheSavedJobs() {
        val server = FakeServer()
        val dir = Files.createTempDirectory("vayu").toFile()
        JobStore(File(dir, "jobs-3.json")).apply(payload(job("2")), 0)
        val tokens = MemoryTokenStore().apply {
            save("A", "R")
            saveMe(mapOf("id" to "3", "username" to "ravi", "name" to "Ravi", "role" to "expert", "theme" to "light", "must_change" to "false"))
        }
        server.on("GET auth/me", """{"detail":"Bad gateway"}""", 502)
        val vm = AppViewModel(testGraph(server, tokens, dir), "Test phone")
        compose.setContent { `in`.carcid.vayu.AppRoot(vm) }
        compose.waitUntil(5_000) { compose.onAllNodes(hasText("Arjun Mehta")).fetchSemanticsNodes().isNotEmpty() }
        server.stop()
    }

    @Test fun aDraftOfALeadThatLeftTheListIsInUploadsToSendOrDiscard() {
        val gone = "00000000-0000-0000-0000-000000000009"
        val d = `in`.carcid.vayu.core.draft.Draft(gone, "DEMO-9", "Ravi Kumar", mapOf("inspection" to 7), "pdi",
            startedAt = "2026-11-22T10:00:00+05:30", startSent = true)
        var sent: String? = null
        compose.setContent {
            VayuTheme(ThemeMode.LIGHT) {
                ExpertHome(me, JobsState(jobs), today, {}, {}, ExpertExtras(drafts = mapOf(gone to d), listed = jobs.map { it.id }.toSet(),
                    onSend = { sent = it }))
            }
        }
        compose.onNodeWithText("Uploads").performClick()
        compose.onNodeWithText("1 lead not sent yet · 0 files").assertIsDisplayed()       // what sign-out waits for
        compose.onNodeWithText("Ravi Kumar · No longer on your list · send or discard it").performClick()
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/uploads_left_the_list.png", roborazziOptions = options)
        compose.onNodeWithText("Send").performClick()
        compose.onNode(hasText("Send") and androidx.compose.ui.test.hasClickAction() and androidx.compose.ui.test.hasAnyAncestor(androidx.compose.ui.test.isDialog())).performClick()
        assertEquals(gone, sent)
    }

    @Test fun aRefusedFileSaysWhyAndCanBeRemoved() {
        val f = `in`.carcid.vayu.core.draft.LocalFile("f1", "inspection", "walk_video", "video", "", "video/webm", "gallery", 9, "",
            "Walk-around video 1", error = "video/webm is not allowed for a video.", refused = true)
        val d = `in`.carcid.vayu.core.draft.Draft(jobs[0].id, jobs[0].bookingId, jobs[0].customer, mapOf("inspection" to 7), "pdi",
            submittedAt = "2026-11-24T16:00:00+05:30", submitSent = true, files = listOf(f))
        var removed: String? = null
        compose.setContent {
            VayuTheme(ThemeMode.LIGHT) {
                ExpertHome(me, JobsState(jobs), today, {}, {}, ExpertExtras(drafts = mapOf(d.bookingId to d), listed = jobs.map { it.id }.toSet(),
                    onRemoveFile = { _, x -> removed = x.id }))
            }
        }
        compose.onNodeWithText("Uploads").performClick()
        compose.onNodeWithText("${d.customer} · 1 need you").performClick()
        compose.onNodeWithText("video/webm is not allowed for a video.").assertIsDisplayed()
        compose.onNodeWithText("Remove").performClick()
        assertEquals("f1", removed)
    }
}
