package `in`.carcid.vayu.ui

import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import `in`.carcid.vayu.core.api.Me
import `in`.carcid.vayu.core.update.AppUpdate
import `in`.carcid.vayu.ui.expert.NotificationsScreen
import `in`.carcid.vayu.ui.theme.ThemeMode
import `in`.carcid.vayu.ui.theme.VayuTheme
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.time.LocalDate

/** The bell (expert), Ops' notification switches and the update screen, as the prototype drew them. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w390dp-h844dp-xxhdpi", sdk = [34])
class BellScreensTest {
    @get:Rule val compose = createComposeRule()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))
    private val today = LocalDate.of(2026, 11, 24)

    private val bell = parseNotes(Json.parseToJsonElement("""{"unread":2,"results":[
        {"id":3,"kind":"assigned","title":"New job: DEMO-2","body":"Arjun Mehta · 2026-11-24 15:30","booking":"b2","created_at":"2026-11-24T09:18:00+05:30","read":false},
        {"id":2,"kind":"rescheduled","title":"DEMO-7 moved","body":"2026-12-02 10:30 → 2026-12-04 16:30","booking":"b7","created_at":"2026-11-24T09:12:00+05:30","read":false},
        {"id":1,"kind":"cancelled","title":"DEMO-13 cancelled","body":"Lata Joshi · customer cancelled","booking":null,"created_at":"2026-11-23T18:05:00+05:30","read":true}
    ]}""").jsonObject)

    @Test fun expertBellListsByDayAndOpensAJob() {
        var opened: Note? = null
        var readAll = false
        compose.setContent { VayuTheme(ThemeMode.LIGHT) { NotificationsScreen(bell, today, {}, { readAll = true }, { opened = it }) } }
        compose.onNodeWithText("TODAY").assertExists()
        compose.onNodeWithText("YESTERDAY").assertExists()
        compose.onNodeWithText("New job: DEMO-2").performClick()
        assertEquals("b2", opened?.booking)
        compose.onNodeWithText("Mark all read").performClick()
        assertEquals(true, readAll)
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/bell_expert.png", roborazziOptions = options)
    }

    @Test fun opsSwitchesProblemsAlwaysOn() {
        val changes = mutableListOf<Pair<String, Boolean>>()
        val me = Me(5, "priya", "Priya Ops", "ops", false, "light", muted = setOf("new_bookings"))
        compose.setContent { VayuTheme(ThemeMode.LIGHT) {
            ProfileScreen(Screen.Profile(me), {}, {}, {}, onNotify = { k, on -> changes += k to on }, version = "0.1.0")
        } }
        compose.onNodeWithText("Always on").assertExists()
        compose.onNodeWithText("New bookings").assertIsOff()
        compose.onNodeWithText("Submitted and completed").assertIsOn().performClick()
        assertEquals(listOf("submitted" to false), changes)
        compose.onNodeWithText("Vayu 0.1.0 · up to date").assertExists()
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/profile_ops_notifications.png", roborazziOptions = options)
    }

    @Test fun updateScreenSaysWhatsNew() {
        var later = false
        compose.setContent { VayuTheme(ThemeMode.LIGHT) {
            UpdateScreen(AppUpdate(5, "1.1.0", 24 * 1_048_576L, "ab", listOf("Faster photo uploads on slow networks", "Scan registration numbers too"),
                "http://x", required = true)) { later = true }
        } }
        compose.onNodeWithText("Version 1.1.0 · 24 MB. You need it to start new jobs. A job you already started can be finished on this version.").assertExists()
        compose.onNodeWithText("Download update").assertExists()
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/update_available.png", roborazziOptions = options)
        compose.onNodeWithText("Later").performClick()
        assertEquals(true, later)
        assertEquals("1 MB", mb(1000)); assertEquals("0 MB", mb(0))
    }
}
