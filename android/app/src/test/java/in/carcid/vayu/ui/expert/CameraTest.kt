package `in`.carcid.vayu.ui.expert

import android.Manifest
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import `in`.carcid.vayu.core.forms.Field
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import java.nio.file.Files
import java.time.Instant

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class CameraTest {
    @get:Rule val compose = createComposeRule()
    private val app = ApplicationProvider.getApplicationContext<android.app.Application>()
    private fun field(type: String) = Field("f", "Engine running video", type, "", false, null, null, true, "edit", emptyMap())
    private fun show(type: String) = compose.setContent {
        CameraScreen(field(type), 0, "DEMO-8", "Ravi Expert", { Instant.parse("2026-11-24T05:00:00Z") }, true,
            Files.createTempDirectory("cam").toFile(), { _, _ -> }, {})
    }

    /** H-23: after "Don't allow" Android stops asking; the way back is Settings, one tap away. */
    @Test fun aDeniedCameraOffersSettings() {
        show("photo")
        compose.onNodeWithText("Allow camera in Settings").performClick()
        assertEquals(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, shadowOf(app).nextStartedActivity.action)
    }

    /** F-182: a video without the microphone has no sound; say so before it is recorded. */
    @Test fun aVideoWithoutTheMicrophoneSaysItHasNoSound() {
        shadowOf(app).grantPermissions(Manifest.permission.CAMERA)
        show("video")
        compose.onNodeWithText("No sound: the microphone isn't allowed.").assertExists()
    }

    /** F-088: recorded videos are 720p at about 2.5 Mbps on every phone, not the phone's own (often much higher) rate. */
    @Test fun videosAre720pAtAbout2Point5Mbps() {
        assertEquals(2_500_000, videoRecorder().targetVideoEncodingBitRate)
    }
}
