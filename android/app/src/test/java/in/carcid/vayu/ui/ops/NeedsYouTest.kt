package `in`.carcid.vayu.ui.ops

import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import `in`.carcid.vayu.ui.components.Tone
import `in`.carcid.vayu.ui.theme.ThemeMode
import `in`.carcid.vayu.ui.theme.VayuTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.util.TimeZone

/** Needs you, Problems: each row is the title, its category and its time, grouped by day (owner). */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w390dp-h844dp-xxhdpi", sdk = [34])
class NeedsYouTest {
    @get:Rule val compose = createComposeRule()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))
    private val today = LocalDate.of(2026, 11, 26)
    private val env = OpsEnv(`in`.carcid.vayu.core.api.Me(id = 1, username = "ops", name = "Priya Ops", role = "ops", mustChangePassword = false, theme = "light"),
        `in`.carcid.vayu.core.ops.OpsData(`in`.carcid.vayu.core.api.Api("http://localhost/", `in`.carcid.vayu.core.auth.MemoryTokenStore()), java.io.File("build/tmp-ops")),
        Labels(), { today }, 0, {}, {})

    private val before: TimeZone = TimeZone.getDefault()
    @org.junit.Before fun india() = TimeZone.setDefault(TimeZone.getTimeZone("Asia/Kolkata"))
    @org.junit.After fun back() = TimeZone.setDefault(before)
    private fun at(day: Int, hh: Int, mm: Int) = LocalDate.of(2026, 11, day).atTime(hh, mm).atZone(ZoneId.of("Asia/Kolkata")).toInstant()

    private val problems = listOf(
        Need("s8", "b8", Tone.BAD, "Photos stuck: DEMO-8", "Stuck uploads", at(25, 18, 2)),
        Need("c14", "b14", Tone.BAD, "Two experts inspected DEMO-14", "Conflicts", at(26, 10, 40)),
        Need("l7", "b7", Tone.WARN, "DEMO-7: started 28 min late", "Started late", at(24, 15, 58)),
        Need("p10", "b10", Tone.BAD, "Report failed for DEMO-10", "Reports", at(26, 9, 15)),
        Need("x", "b2", Tone.WARN, "No report for DEMO-2", "Reports", null),
    )

    @Test fun problemsAreGroupedByDayNewestFirstWithTitleCategoryAndTime() {
        compose.setContent { VayuTheme(ThemeMode.LIGHT) { NeedsYouScreen(env, problems, onBack = {}, onOpen = {}) } }
        for (t in listOf("TODAY", "YESTERDAY", "24 NOV", "EARLIER", "Stuck uploads", "Conflicts"))
            compose.onNodeWithText(t).assertExists()
        for (t in listOf("10:40\u00a0am", "9:15\u00a0am", "6:02\u00a0pm", "3:58\u00a0pm"))      // time12 keeps "am" with the time
            compose.onNodeWithText(t).assertExists()
        assertEquals(2, compose.onAllNodesWithText("Reports").fetchSemanticsNodes().size)
        // newest first: today's 10:40 before 9:15, then yesterday, then 24 Nov, then the one with no time
        val order = listOf("Two experts inspected DEMO-14", "Report failed for DEMO-10", "Photos stuck: DEMO-8", "DEMO-7: started 28 min late", "No report for DEMO-2")
        val tops = order.map { compose.onNodeWithText(it).fetchSemanticsNode().positionInRoot.y }
        assertEquals(tops.sorted(), tops)
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/needs_you_problems.png", roborazziOptions = options)
    }

    @Test fun serverTimesAndBookedTimesAreRead() {
        assertEquals(Instant.parse("2026-11-26T04:35:00Z"), instantOf("2026-11-26T10:05:00+05:30"))
        assertEquals(Instant.parse("2026-11-26T04:35:00Z"), instantOf("2026-11-26T04:35:00Z"))
        assertNull(instantOf("")); assertNull(instantOf(null)); assertNull(instantOf("soon"))
    }
}
