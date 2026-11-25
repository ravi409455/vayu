package `in`.carcid.vayu.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.performImeAction
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

    private var pushTokens = 0
    private val tokens = MemoryTokenStore()

    private val root = java.nio.file.Files.createTempDirectory("vayu").toFile()
    private lateinit var graph: `in`.carcid.vayu.Graph

    private fun launch() {
        graph = `in`.carcid.vayu.Graph(Api(server.url, tokens), tokens, root, {},
            sendPushToken = { pushTokens++ })
        val vm = AppViewModel(graph, "Test phone")
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
        compose.onNodeWithText("Welcome back. Your work is waiting.").assertIsDisplayed()
        compose.onRoot().captureRoboImage("src/test/screenshots/sign_in.png", roborazziOptions = options)
    }

    @Test fun theKeyboardGoesFromUsernameToPasswordAndSignsIn() {
        signedIn("expert")
        launch()
        compose.onNodeWithContentDescription("Username").performTextInput("ravi")
        compose.onNodeWithContentDescription("Username").performImeAction()               // Next, not Done
        compose.onNodeWithContentDescription("Password").assertIsFocused().performTextInput("Vayu-local-1")
        compose.onNodeWithContentDescription("Password").performImeAction()               // Done signs in
        waitFor("My leads")
    }

    /** F-073: everything is sent (sign-out checks), so this person's drafts, answers and photos leave the phone. */
    @Test fun signingOutTakesThePersonsDraftsOffThePhone() {
        signedIn("expert")
        server.on("POST auth/logout", "", 204)
        launch(); signIn(); waitFor("My leads")
        val sent = `in`.carcid.vayu.core.draft.Draft("00000000-0000-0000-0000-000000000001", "DEMO-1", "Farhan Ali", emptyMap(), "pdi", submitSent = true)
        graph.drafts(3).save(sent)
        java.io.File(root, "drafts-3/files").apply { mkdirs() }.resolve("old.jpg").writeText("stamped photo")
        compose.onNodeWithContentDescription("Profile").performClick()
        compose.onNodeWithText("Sign out").performClick()
        waitFor("Sign in")
        compose.waitUntil(5_000) { !java.io.File(root, "drafts-3").exists() }
    }

    /** F-077: signed out without signal, the server's sign-in for this phone is ended at the next sign-in. */
    @Test fun aSignOutWithoutSignalIsFinishedAtTheNextSignIn() {
        signedIn("expert")
        server.on("POST auth/logout", "", 503)                    // the server can't be reached
        launch(); signIn(); waitFor("My leads")
        compose.onNodeWithContentDescription("Profile").performClick()
        compose.onNodeWithText("Sign out").performClick()
        waitFor("Sign in")
        server.on("POST auth/logout", "", 204)
        server.on("POST auth/refresh", """{"access":"OLD-A","refresh":"R2"}""")
        signIn(); waitFor("My leads")
        compose.waitUntil(5_000) { server.bodiesOf("POST auth/refresh").any { "\"R\"" in it } }
        compose.waitUntil(5_000) { server.bodiesOf("POST auth/logout").size == 2 }
    }

    @Test fun anExpertLandsOnMyJobs() {
        signedIn("expert")
        launch(); signIn(); waitFor("My leads")
    }

    @Test fun theSignInQueuesThePushTokenToBeSentUntilItArrives() {
        signedIn("expert")
        launch(); signIn(); waitFor("My leads")
        org.junit.Assert.assertEquals(1, pushTokens)                       // WorkManager retries it (offline at sign-in)
    }

    @Test fun aSignInThatEndsWhileTheAppRunsAsksToSignInAgain() {
        signedIn("expert")
        launch(); signIn(); waitFor("My leads")
        // the first sync must be over, or the Refresh tap below is ignored while it runs (seen under load)
        compose.waitUntil(10_000) { server.requests.any { it.first == "GET sync/jobs" } &&
            compose.onAllNodes(androidx.compose.ui.test.hasContentDescription("Updating leads")).fetchSemanticsNodes().isEmpty() }
        server.on("GET sync/jobs", """{"code":"token_not_valid","detail":"Token is invalid or expired"}""", 401)
        server.on("POST auth/refresh", """{"code":"token_not_valid","detail":"Token is invalid or expired"}""", 401)
        compose.onNode(androidx.compose.ui.test.hasContentDescription("Refresh", substring = true)).performClick()
        waitFor("Your sign-in has ended. Sign in again; your unsent work stays on this phone.")
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
