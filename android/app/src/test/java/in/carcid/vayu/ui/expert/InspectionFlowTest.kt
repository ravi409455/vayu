package `in`.carcid.vayu.ui.expert

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import `in`.carcid.vayu.core.draft.BOOKING
import `in`.carcid.vayu.core.draft.DraftStore
import `in`.carcid.vayu.core.forms.Fixtures
import `in`.carcid.vayu.core.sync.JobStore
import `in`.carcid.vayu.core.sync.job
import `in`.carcid.vayu.core.sync.payload
import `in`.carcid.vayu.ui.theme.ThemeMode
import `in`.carcid.vayu.ui.theme.VayuTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.nio.file.Files
import java.time.Instant

@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w390dp-h844dp-xxhdpi", sdk = [34])
class InspectionFlowTest {
    @get:Rule val compose = createComposeRule()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))
    private val root = Files.createTempDirectory("vayu").toFile()
    private val drafts = DraftStore(File(root, "drafts"))
    private val jobs = JobStore(File(root, "jobs.json")).apply {
        apply(payload(job(BOOKING, start = 1, end = 9, code = "DEMO-2"), forms = Fixtures.FORMS), 0)
    }
    private val now = Instant.parse("2026-11-24T09:58:00Z")
    private var kicks = 0
    private val model = InspectionModel(drafts, jobs, BOOKING, { now }, { kicks++ })

    private fun show(theme: ThemeMode = ThemeMode.LIGHT) {
        InspectionModel.begin(drafts, jobs.jobs().single(), verified = true)
        compose.setContent {
            VayuTheme(theme) {
                InspectionScreen(InspectionEnv(model, drafts, "Ravi Expert", true, { now }, jobs::list, jobs.types(), { null }), onClose = {})
            }
        }
    }

    private fun shot(name: String) = compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/$name.png", roborazziOptions = options)

    @Test fun theCheckInStartsTheJobOnlyWhenComplete() {
        show()
        compose.onNodeWithText("Not started yet", substring = true).assertDoesNotExist()   // everyone knows; no banner
        shot("check_in")
        assertNull(model.draft.startedAt)
        compose.onNodeWithText("Car").performClick()
        compose.waitForIdle()
        assertNotNull(model.draft.startedAt)                       // complete: stamped and queued for sending
        assertTrue(kicks > 0)
        assertTrue(model.draft.answer("start", "checkin_time") is String)   // automatic time recorded
    }

    @Test fun aGatePageHoldsTheExpertUntilItIsDone() {
        show()
        compose.onNodeWithText("Car").performClick()
        compose.onNodeWithText("Next · Vehicle").performClick()
        compose.onNodeWithText("Next · Exterior").performClick()
        compose.onNode(hasText("Finish this page first", substring = true)).assertIsDisplayed()
        compose.onNodeWithContentDescription("Chassis number").performTextInput("MA3YPKCSKTJ273129")
        compose.onNodeWithContentDescription("Odometer").performTextInput("12450")
        assertEquals(12450.0, model.draft.answer("inspection", "odometer"))   // saved as it is typed
        compose.waitForIdle()
        compose.onNode(hasText("Finish this page first", substring = true)).assertDoesNotExist()  // done: message gone
        compose.onNodeWithText("Next · Exterior").performClick()
        compose.onNodeWithText("Bonnet").assertIsDisplayed()
    }

    @Test fun aDefectOpensItsFollowUpAndTheLayoutsFollowTheRule() {
        show()
        model.set("start", "travel", "car")
        model.set("inspection", "chassis_no", "MA3YPKCSKTJ273129"); model.set("inspection", "odometer", 12450.0)
        model.go(2, model.steps(model.filled()!!)[2])
        compose.waitForIdle()
        compose.onNodeWithText("Bonnet").assertIsDisplayed()
        compose.onNodeWithText("Door photos").assertDoesNotExist()
        compose.onAllNodes(hasText("Minor"))[1].performClick()                     // front left door: Minor
        compose.onNodeWithText("Door photos").assertIsDisplayed()
        compose.onNodeWithText("Original paint").assertIsDisplayed()                // 7 options: stacked rows
        compose.onNodeWithText("Choose…").performScrollTo().assertIsDisplayed()     // 10 options: a list
        compose.onNodeWithText("Front bumper").performScrollTo().performClick()     // multi: chips
        assertEquals(listOf("fb"), model.draft.answer("inspection", "scratches"))
        compose.onNodeWithText("Bonnet").performScrollTo()
        shot("wizard_page")
    }

    @Test fun thePageListShowsTicksAndWhatIsNeeded() {
        show()
        model.set("start", "travel", "car")
        compose.onNodeWithContentDescription("Page 1 of 5, open the page list").performClick()
        compose.onNodeWithText("Pages").assertIsDisplayed()
        compose.onNodeWithText("Discard draft…").assertIsDisplayed()
        // the sheet is its own window: capture the whole screen
        @OptIn(com.github.takahirom.roborazzi.ExperimentalRoborazziApi::class)
        com.github.takahirom.roborazzi.captureScreenRoboImage("src/test/screenshots/page_list.png", roborazziOptions = options)
    }

    @Test fun lockedPagesSayWhyAtTheTopAndShowALock() {
        show()
        model.set("start", "travel", "car")
        compose.onNodeWithContentDescription("Page 1 of 5, open the page list").performClick()
        val why = compose.onNodeWithText("Finish Vehicle to open the other pages.").assertIsDisplayed().fetchSemanticsNode().boundsInRoot
        val exterior = compose.onNodeWithText("Exterior").fetchSemanticsNode().boundsInRoot
        assertTrue("the reason comes before the locked pages", why.top < exterior.top)
        assertTrue(compose.onAllNodesWithContentDescription("locked").fetchSemanticsNodes().isNotEmpty())
    }

    @Test fun reviewListsWhatIsMissingThenSubmitLocksTheAnswers() {
        show()
        model.set("start", "travel", "car")
        val steps = model.steps(model.filled()!!)
        model.go(steps.lastIndex, steps.last())
        compose.waitForIdle()
        compose.onNodeWithText("answers still needed").assertIsDisplayed()
        compose.onNodeWithText("Chassis number").assertIsDisplayed()
        shot("review")
        // fill the rest, open every page, submit
        mapOf("chassis_no" to "MA3", "odometer" to 1.0, "bonnet" to "ok", "door" to "ok").forEach { (k, v) -> model.set("inspection", k, v) }
        model.set("end", "taking_payment", false)
        steps.forEachIndexed { i, s -> model.go(i, s) }
        compose.waitForIdle()
        compose.onNodeWithText("Everything needed is filled in.").assertIsDisplayed()
        compose.onNodeWithText("Submit inspection").performClick()
        compose.onNodeWithText("Submitted").assertIsDisplayed()
        assertTrue(model.draft.locked)
        model.set("end", "taking_payment", true)
        assertEquals(false, model.draft.answer("end", "taking_payment"))           // locked: no more changes
        shot("submitted")
    }

    @Test fun theWizardInDark() {
        show(ThemeMode.DARK)
        model.set("start", "travel", "car")
        shot("check_in_dark")
    }

    @Test fun aDraftPrunedWhileItsScreenIsOpenClosesTheScreen() {
        InspectionModel.begin(drafts, jobs.jobs().single(), verified = true)
        drafts.update(BOOKING) { it.copy(submittedAt = "2026-11-24T16:00:00+05:30") }
        var closed = false
        compose.setContent {
            VayuTheme(ThemeMode.LIGHT) {
                InspectionScreen(InspectionEnv(model, drafts, "Ravi Expert", true, { now }, jobs::list, jobs.types(), { null }), onClose = { closed = true })
            }
        }
        compose.waitForIdle()
        drafts.discard(BOOKING)                                    // the finished work left the phone after a sync
        compose.waitForIdle()
        assertTrue(closed)
    }
}
