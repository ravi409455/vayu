package `in`.carcid.vayu.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import `in`.carcid.vayu.AppRoot
import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.auth.MemoryTokenStore
import org.junit.After
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Sign-in end to end against a fake server: experts land on My jobs, Ops on Today, Admins are turned away. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w390dp-h844dp-xxhdpi", sdk = [34])
class SignInFlowTest {
    @get:Rule val compose = createComposeRule()
    private val server = `in`.carcid.vayu.core.api.FakeServer()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))

    @After fun stop() = server.stop()

    private fun signedIn(role: String, mustChange: Boolean = false) {
        server.on("POST auth/login", """{"access":"A","refresh":"R"}""")
        server.on("GET auth/me", me(role, mustChange))
        server.on("POST devices/heartbeat", """{"min_app_version":1}""")
        server.on("GET sync/jobs", """{"server_time":"2026-11-24T05:00:00Z","jobs":[]}""")
    }
    private fun me(role: String, mustChange: Boolean = false) =
        """{"id":3,"username":"ravi","name":"Ravi Expert","role":"$role","must_change_password":$mustChange,"theme":"light"}"""

    private fun launch() {
        val vm = AppViewModel(`in`.carcid.vayu.core.api.testGraph(server), "Test phone")
        compose.setContent { AppRoot(vm) }
    }

    private fun signIn() {
        compose.onNodeWithContentDescription("Username").performTextInput("ravi")
        compose.onNodeWithContentDescription("Password").performTextInput("Vayu-local-1")
        compose.onNode(androidx.compose.ui.test.hasText("Sign in") and androidx.compose.ui.test.hasClickAction()).performClick()
    }

    private fun waitFor(text: String) = compose.waitUntil(5_000) {
        compose.onAllNodes(androidx.compose.ui.test.hasText(text)).fetchSemanticsNodes().isNotEmpty()
    }

    @Test fun theSignInScreenMatchesTheDesign() {
        launch()
        compose.onNodeWithText("Welcome back. Your jobs are waiting.").assertIsDisplayed()
        compose.onRoot().captureRoboImage("src/test/screenshots/sign_in.png", roborazziOptions = options)
    }

    @Test fun anExpertLandsOnMyJobs() {
        signedIn("expert")
        launch(); signIn(); waitFor("My jobs")
    }

    @Test fun opsLandOnToday() {
        signedIn("ops")
        launch(); signIn(); waitFor("Today")
    }

    @Test fun anAdminIsSentToTheWeb() {
        server.on("POST auth/login", """{"code":"ADMIN_USE_WEB","detail":"Admins use the web."}""", 403)
        launch(); signIn(); waitFor("Admin tools live on the web")
        compose.onRoot().captureRoboImage("src/test/screenshots/admin_refused.png", roborazziOptions = options)
    }

    @Test fun aWrongPasswordIsExplained() {
        server.on("POST auth/login", """{"code":"INVALID_CREDENTIALS","detail":"Username or password is wrong."}""", 401)
        launch(); signIn(); waitFor("Username or password is wrong.")
    }

    @Test fun aFirstSignInAsksForANewPassword() {
        signedIn("expert", mustChange = true)
        launch(); signIn(); waitFor("Choose your password")
        compose.onRoot().captureRoboImage("src/test/screenshots/change_password.png", roborazziOptions = options)
    }
}

private fun androidx.compose.ui.test.junit4.ComposeContentTestRule.onRoot() = onNode(androidx.compose.ui.test.isRoot())
