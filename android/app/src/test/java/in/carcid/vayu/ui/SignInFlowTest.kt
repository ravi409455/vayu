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
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Before
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
    private val server = MockWebServer()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))

    @Before fun start() = server.start()
    @After fun stop() = server.shutdown()

    private fun json(code: Int, body: String) = MockResponse().setResponseCode(code).setBody(body)
    private fun me(role: String, mustChange: Boolean = false) =
        """{"id":3,"username":"ravi","name":"Ravi Expert","role":"$role","must_change_password":$mustChange,"theme":"light"}"""

    private fun launch() {
        val tokens = MemoryTokenStore()
        val vm = AppViewModel(Api(server.url("/api/v1/").toString(), tokens), tokens, "Test phone")
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
        server.enqueue(json(200, """{"access":"A","refresh":"R"}""")); server.enqueue(json(200, me("expert")))
        server.enqueue(json(200, """{"min_app_version":1}"""))
        launch(); signIn(); waitFor("My jobs")
    }

    @Test fun opsLandOnToday() {
        server.enqueue(json(200, """{"access":"A","refresh":"R"}""")); server.enqueue(json(200, me("ops")))
        server.enqueue(json(200, """{"min_app_version":1}"""))
        launch(); signIn(); waitFor("Today")
    }

    @Test fun anAdminIsSentToTheWeb() {
        server.enqueue(json(403, """{"code":"ADMIN_USE_WEB","detail":"Admins use the web."}"""))
        launch(); signIn(); waitFor("Admin tools live on the web")
        compose.onRoot().captureRoboImage("src/test/screenshots/admin_refused.png", roborazziOptions = options)
    }

    @Test fun aWrongPasswordIsExplained() {
        server.enqueue(json(401, """{"code":"INVALID_CREDENTIALS","detail":"Username or password is wrong."}"""))
        launch(); signIn(); waitFor("Username or password is wrong.")
    }

    @Test fun aFirstSignInAsksForANewPassword() {
        server.enqueue(json(200, """{"access":"A","refresh":"R"}""")); server.enqueue(json(200, me("expert", mustChange = true)))
        launch(); signIn(); waitFor("Choose your password")
        compose.onRoot().captureRoboImage("src/test/screenshots/change_password.png", roborazziOptions = options)
    }
}

private fun androidx.compose.ui.test.junit4.ComposeContentTestRule.onRoot() = onNode(androidx.compose.ui.test.isRoot())
