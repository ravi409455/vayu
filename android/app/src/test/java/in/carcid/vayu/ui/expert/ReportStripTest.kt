package `in`.carcid.vayu.ui.expert

import android.view.Surface
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createComposeRule
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** The camera shows the band the report prints (approved 2026-11-27): report photo boxes are 4:3 landscape. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w390dp-h844dp-xxhdpi", sdk = [34])
class ReportStripTest {
    @get:Rule val compose = createComposeRule()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))

    /** Upright: the band the report prints is bright, above and below are dimmed. */
    @Test fun uprightShowsTheReportBand() {
        compose.setContent { Box(Modifier.fillMaxSize().background(Color(0xFF8A8A8A))) { ReportStrip(0) } }
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/camera_report_band.png", roborazziOptions = options)
    }

    /** Sideways: the whole photo is the report's shape, only a thin frame; the name and stamp read the right way up. */
    @Test fun sidewaysFramesTheWholePhoto() {
        compose.setContent { Box(Modifier.fillMaxSize().background(Color(0xFF8A8A8A))) { ReportStrip(-90, "Front left view", "0 of 1 taken", "TST-1014 · Test Expert · 27 Nov 2026 13:07\n27.907475, 78.112752") } }
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/camera_sideways_framed.png", roborazziOptions = options)
    }

    /** A slanted phone keeps its last state, so the hint doesn't flicker. */
    @Test fun sidewaysHasAMargin() {
        assertEquals(true, sidewaysAt(90, false)); assertEquals(true, sidewaysAt(270, false))
        assertEquals(false, sidewaysAt(0, true)); assertEquals(false, sidewaysAt(180, true))
        assertEquals(true, sidewaysAt(45, true)); assertEquals(false, sidewaysAt(45, false))
    }

    /** A jumpy reading (phone pointed down) doesn't flicker the hint: a new state must hold half a second. */
    @Test fun aJumpyTurnDoesNotFlicker() {
        val f = TurnFilter()
        assertEquals(false, f.feed(true, 0)); assertEquals(false, f.feed(false, 200)); assertEquals(false, f.feed(true, 300))
        assertEquals(false, f.feed(true, 700)); assertEquals(true, f.feed(true, 800)); assertEquals(true, f.feed(false, 900))
    }

    /** A sideways shot is saved upright: the camera turns with the phone. */
    @Test fun theCameraTurnsWithThePhone() {
        assertEquals(Surface.ROTATION_0, rotationAt(10))
        assertEquals(Surface.ROTATION_270, rotationAt(90))
        assertEquals(Surface.ROTATION_180, rotationAt(180))
        assertEquals(Surface.ROTATION_90, rotationAt(270))
    }
}
