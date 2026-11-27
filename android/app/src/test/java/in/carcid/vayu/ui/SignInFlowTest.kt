package `in`.carcid.vayu.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.performImeAction
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onLast
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

    private var kicks = 0

    private fun launch() {
        graph = `in`.carcid.vayu.Graph(Api(server.url, tokens), tokens, root, { kicks++ },
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
        org.junit.Assert.assertEquals("""{"drafts":0,"files":0}""", server.bodiesOf("POST auth/logout").single())
    }

    private val unsentId = "00000000-0000-0000-0000-000000000002"

    /** Ravi has DEMO-2 unsent (one photo not sent): its draft and photo file are on the phone. */
    private fun unsentWork(): java.io.File {
        val photo = java.io.File(root, "drafts-3/files").apply { mkdirs() }.resolve("front.jpg").apply { writeText("stamped photo") }
        val file = `in`.carcid.vayu.core.draft.LocalFile("f1", "inspection", "front", "photo", photo.path, "image/jpeg", "camera", 13, "", "Front 1")
        graph.drafts(3).save(`in`.carcid.vayu.core.draft.Draft(unsentId, "DEMO-2", "Arjun", emptyMap(), "pdi", files = listOf(file)))
        return photo
    }

    private fun tapSignOutInSheet() =
        compose.onAllNodes(androidx.compose.ui.test.hasText("Sign out") and androidx.compose.ui.test.hasClickAction()).onLast().performClick()

    /** plan-media-backup: unsent work no longer blocks sign-out; a warning names the leads first. */
    @Test fun signingOutWithUnsentWorkWarnsFirstAndStayingSignedInChangesNothing() {
        signedIn("expert")
        server.on("POST auth/logout", "", 204)
        launch(); signIn(); waitFor("My leads")
        unsentWork()
        compose.onNodeWithContentDescription("Profile").performClick()
        compose.onNodeWithText("Sign out").performClick()
        waitFor("Sign out with unsent work?")
        compose.onNodeWithText("DEMO-2").assertIsDisplayed()
        compose.onRoot().captureRoboImage("src/test/screenshots/sign_out_unsent.png", roborazziOptions = options)
        compose.onNodeWithText("Stay signed in").performClick()
        compose.waitUntil(5_000) { compose.onAllNodes(androidx.compose.ui.test.hasText("Sign out with unsent work?")).fetchSemanticsNodes().isEmpty() }
        org.junit.Assert.assertEquals(0, server.bodiesOf("POST auth/logout").size)
        compose.onNodeWithText("Sign out").assertIsDisplayed()                   // still on Profile
    }

    /** plan-media-backup: the unsent work stays, the server is told, and it sends at the next sign-in. */
    @Test fun signingOutKeepsUnsentWorkAndTheNextSignInSendsIt() {
        signedIn("expert")
        server.on("POST auth/logout", "", 204)
        launch(); signIn(); waitFor("My leads")
        val photo = unsentWork()
        compose.onNodeWithContentDescription("Profile").performClick()
        compose.onNodeWithText("Sign out").performClick()
        waitFor("Sign out with unsent work?")
        tapSignOutInSheet()
        waitFor("Sign in")
        org.junit.Assert.assertEquals("""{"drafts":1,"files":1}""", server.bodiesOf("POST auth/logout").single())
        org.junit.Assert.assertTrue(photo.exists())
        org.junit.Assert.assertNotNull(graph.drafts(3).get(unsentId))
        val before = kicks
        signIn(); waitFor("My leads")
        org.junit.Assert.assertNotNull(graph.drafts(3).get(unsentId))
        org.junit.Assert.assertTrue(kicks > before)                              // the outbox starts sending
        // the same install both times, so the server lets this phone back in to send it
        val installs = server.bodiesOf("POST auth/login").map { Regex("\"install_id\":\"([^\"]+)\"").find(it)!!.groupValues[1] }
        org.junit.Assert.assertEquals(2, installs.size)
        org.junit.Assert.assertEquals(installs[0], installs[1])
    }

    /** Another person signing in on this phone neither sees nor removes the first person's unsent work. */
    @Test fun anotherPersonsSignInKeepsTheFirstPersonsUnsentWork() {
        signedIn("expert")
        server.on("POST auth/logout", "", 204)
        launch(); signIn(); waitFor("My leads")
        val photo = unsentWork()
        compose.onNodeWithContentDescription("Profile").performClick()
        compose.onNodeWithText("Sign out").performClick()
        waitFor("Sign out with unsent work?")
        tapSignOutInSheet()
        waitFor("Sign in")
        server.on("GET auth/me", """{"id":4,"username":"meera","name":"Meera","role":"expert","must_change_password":false,"theme":"light"}""")
        signIn(); waitFor("My leads")
        org.junit.Assert.assertTrue(photo.exists())
        org.junit.Assert.assertNotNull(graph.drafts(3).get(unsentId))
        org.junit.Assert.assertTrue(graph.drafts(4).all().isEmpty())
        org.junit.Assert.assertTrue(compose.onAllNodes(androidx.compose.ui.test.hasText("DEMO-2")).fetchSemanticsNodes().isEmpty())
    }

    /** No signal at sign-out: the work stays all the same, and the old sign-in ends at the next one. */
    @Test fun aSignOutWithoutSignalKeepsUnsentWork() {
        signedIn("expert")
        server.on("POST auth/logout", "", 503)
        launch(); signIn(); waitFor("My leads")
        val photo = unsentWork()
        compose.onNodeWithContentDescription("Profile").performClick()
        compose.onNodeWithText("Sign out").performClick()
        waitFor("Sign out with unsent work?")
        tapSignOutInSheet()
        waitFor("Sign in")
        org.junit.Assert.assertTrue(photo.exists())
        org.junit.Assert.assertNotNull(tokens.pendingLogout())
    }

    /** F-9: a booking Ops finished "without the missing files" is not named in the warning; other unsent work is. */
    @Test fun aBookingOpsFinishedIsNotNamedInTheWarning() {
        signedIn("expert")
        val id = "00000000-0000-0000-0000-000000000001"
        server.on("GET sync/jobs", """{"server_time":"2026-11-24T05:00:00Z","jobs":[${`in`.carcid.vayu.core.sync.job(id, stage = "completed")}]}""")
        server.on("POST auth/logout", "", 204)
        launch(); signIn(); waitFor("My leads")
        compose.waitUntil(10_000) { graph.jobs(3).jobs().any { it.id == id } }   // the first sync is slow under load (CI)
        val waiting = `in`.carcid.vayu.core.draft.LocalFile("f1", "inspection", "front", "photo", "", "image/jpeg", "camera", 4, "", "Front 1")
        graph.drafts(3).save(`in`.carcid.vayu.core.draft.Draft(id, "DEMO-1", "Farhan Ali", emptyMap(), "pdi", submitSent = true, files = listOf(waiting)))
        graph.drafts(3).save(`in`.carcid.vayu.core.draft.Draft(unsentId, "DEMO-2", "Arjun", emptyMap(), "pdi"))
        compose.onNodeWithContentDescription("Profile").performClick()
        compose.onNodeWithText("Sign out").performClick()
        waitFor("Sign out with unsent work?")
        compose.onNodeWithText("DEMO-2").assertIsDisplayed()
        org.junit.Assert.assertTrue(compose.onAllNodes(androidx.compose.ui.test.hasText("DEMO-1")).fetchSemanticsNodes().isEmpty())
        graph.drafts(3).discard(unsentId)
        compose.onNodeWithText("Stay signed in").performClick()
        compose.onNodeWithText("Sign out").performClick()              // only the finished one left: no warning
        waitFor("Sign in")
    }

    /** F-051: a draft file the phone can't read is never deleted by sign-out: sign-out says so and stops. */
    @Test fun aDraftThatCantBeReadStopsTheSignOut() {
        signedIn("expert")
        server.on("POST auth/logout", "", 204)
        launch(); signIn(); waitFor("My leads")
        val bad = java.io.File(root, "drafts-3").apply { mkdirs() }.resolve("00000000-0000-0000-0000-000000000009.json").apply { writeText("{not json") }
        compose.onNodeWithContentDescription("Profile").performClick()
        compose.onNodeWithText("Sign out").performClick()
        compose.waitUntil(5_000) { compose.onAllNodes(androidx.compose.ui.test.hasText("can't be read", substring = true)).fetchSemanticsNodes().isNotEmpty() }
        org.junit.Assert.assertTrue(bad.exists())
        org.junit.Assert.assertEquals(0, server.bodiesOf("POST auth/logout").size)
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

    /** F-018: the update downloads in the view model (it carries on if its screen closes) and is checked. */
    @Test fun theUpdateDownloadsInTheViewModel() {
        val bytes = "PK fake apk"
        val sha = java.security.MessageDigest.getInstance("SHA-256").digest(bytes.toByteArray()).joinToString("") { "%02x".format(it) }
        server.on("GET apk", bytes)
        val vm = AppViewModel(`in`.carcid.vayu.Graph(Api(server.url, tokens), tokens, root, {}), "Test phone")
        val file = java.io.File(root, "update/vayu-5.apk").apply { parentFile!!.mkdirs() }
        vm.downloadUpdate(`in`.carcid.vayu.core.update.AppUpdate(5, "1.1.0", 11, sha, emptyList(), server.raw("/api/v1/apk"), false), file)
        // no screen is shown here, so the main looper (where the view model resumes) is run by hand
        compose.waitUntil(10_000) { org.robolectric.shadows.ShadowLooper.idleMainLooper(); vm.updateDownload.value.ready }
        org.junit.Assert.assertEquals(bytes, file.readText())
        org.junit.Assert.assertEquals(11L, vm.updateDownload.value.got)
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

    @Test fun aStartWhileTheServerIsDownStillFetchesTheLeads() {
        // the start skips its first "came to the front" load (the server's answer loads all);
        // when that answer fails, the leads are still fetched once, as before
        signedIn("expert")
        server.on("GET auth/me", """{"detail":"down"}""", 503)
        tokens.save("A", "R")
        tokens.saveMe(mapOf("id" to "3", "username" to "ravi", "name" to "Ravi Expert", "role" to "expert",
            "theme" to "light", "must_change" to "false", "perms" to ""))
        launch(); waitFor("My leads")
        compose.waitUntil(5_000) { server.requests.any { it.first == "GET sync/jobs" } }
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
