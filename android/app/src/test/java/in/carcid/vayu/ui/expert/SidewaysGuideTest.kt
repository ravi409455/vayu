package `in`.carcid.vayu.ui.expert

import android.view.Surface
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** The camera's "Turn your phone sideways" hint (approved 2026-11-27): report photo boxes are 4:3 landscape. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w390dp-h844dp-xxhdpi", sdk = [34])
class SidewaysGuideTest {
    @get:Rule val compose = createComposeRule()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))

    @Test fun uprightShowsTheHintWithTheFieldName() {
        compose.mainClock.autoAdvance = false
        compose.setContent { Box(Modifier.fillMaxSize().background(Color(0xFF3A3A3A))) { SidewaysGuide("Front left view", hint = true, framed = false) } }
        compose.mainClock.advanceTimeBy(1000)
        compose.onNodeWithText("Turn your phone sideways").assertExists()
        compose.onNodeWithText("Front left view").assertExists()
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/camera_turn_sideways.png", roborazziOptions = options)
    }

    @Test fun sidewaysFramesThePhotoAndDropsTheHint() {
        compose.setContent { Box(Modifier.fillMaxSize().background(Color(0xFF3A3A3A))) { SidewaysGuide("Front left view", hint = false, framed = true) } }
        compose.onNodeWithText("Turn your phone sideways").assertDoesNotExist()
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/camera_sideways_framed.png", roborazziOptions = options)
    }

    /** A slanted phone keeps its last state, so the hint doesn't flicker. */
    @Test fun sidewaysHasAMargin() {
        assertEquals(true, sidewaysAt(90, false)); assertEquals(true, sidewaysAt(270, false))
        assertEquals(false, sidewaysAt(0, true)); assertEquals(false, sidewaysAt(180, true))
        assertEquals(true, sidewaysAt(45, true)); assertEquals(false, sidewaysAt(45, false))
    }

    /** A sideways shot is saved upright: the camera turns with the phone. */
    @Test fun theCameraTurnsWithThePhone() {
        assertEquals(Surface.ROTATION_0, rotationAt(10))
        assertEquals(Surface.ROTATION_270, rotationAt(90))
        assertEquals(Surface.ROTATION_180, rotationAt(180))
        assertEquals(Surface.ROTATION_90, rotationAt(270))
    }
}
