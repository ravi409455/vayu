package `in`.carcid.vayu.core.api

import `in`.carcid.vayu.core.auth.MemoryTokenStore
import kotlinx.coroutines.async
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ApiTest {
    private val server = MockWebServer()
    private val tokens = MemoryTokenStore()
    private lateinit var api: Api

    private fun json(code: Int, body: String) = MockResponse().setResponseCode(code).setBody(body)
        .setHeader("Content-Type", "application/json")
    private val me = """{"id":3,"username":"ravi","name":"Ravi Expert","role":"expert","must_change_password":false,"theme":"dark"}"""

    @Before fun start() { server.start(); api = Api(server.url("/api/v1/").toString(), tokens) }
    @After fun stop() = server.shutdown()

    @Test fun signInSavesTokensAndLoadsMe() = runTest {
        server.enqueue(json(200, """{"access":"A1","refresh":"R1","device_id":"d"}"""))
        server.enqueue(json(200, me))
        val m = api.login("ravi", "pw", "Pixel 8")
        assertEquals("expert", m.role); assertEquals("RE", m.initials); assertEquals("A1", tokens.access())
        val login = server.takeRequest()
        assertTrue(login.body.readUtf8().contains("\"client\":\"mobile\""))
        assertEquals("Bearer A1", server.takeRequest().getHeader("Authorization"))
    }

    @Test fun anAdminIsToldToUseTheWeb() = runTest {
        server.enqueue(json(403, """{"code":"ADMIN_USE_WEB","detail":"The app is for Ops and experts. Admins use the web."}"""))
        val e = runCatching { api.login("boss", "pw", "Pixel") }.exceptionOrNull() as ApiError
        assertEquals("ADMIN_USE_WEB", e.code); assertNull(tokens.access())
    }

    @Test fun anExpiredTokenIsRefreshedOnce() = runTest {
        tokens.save("old", "R1")
        server.enqueue(json(401, """{"code":"token_not_valid","detail":"expired"}"""))
        server.enqueue(json(200, """{"access":"new"}"""))
        server.enqueue(json(200, me))
        assertEquals("ravi", api.me().username)
        assertEquals("new", tokens.access()); assertEquals("R1", tokens.refresh())
    }

    @Test fun aRevokedPhoneIsSignedOut() = runTest {
        tokens.save("A", "R")
        server.enqueue(json(401, """{"code":"DEVICE_REVOKED","detail":"This device was signed out."}"""))
        val e = runCatching { api.me() }.exceptionOrNull() as ApiError
        assertEquals("DEVICE_REVOKED", e.code); assertNull(tokens.access())
    }

    @Test fun noConnectionIsAFriendlyError() = runTest {
        server.shutdown()
        val e = runCatching { api.me() }.exceptionOrNull() as ApiError
        assertEquals(ApiError.NETWORK, e.code)
    }

    @Test fun heartbeatReturnsTheMinimumVersion() = runTest {
        tokens.save("A", "R")
        server.enqueue(json(200, """{"server_time":"2026-11-24T10:00:00Z","min_app_version":4}"""))
        assertEquals(4, api.heartbeat(drafts = 0, files = 2))
        assertTrue(server.takeRequest().body.readUtf8().contains("\"files\":2"))
    }

    @Test fun callsThatFailTogetherRenewTheSignInOnce() = runTest {
        tokens.save("old", "R1")
        var refreshes = 0
        server.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
            override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): MockResponse = when {
                request.path!!.endsWith("auth/refresh") -> { synchronized(this) { refreshes++ }; Thread.sleep(100); json(200, """{"access":"new"}""") }
                request.getHeader("Authorization") == "Bearer new" -> json(200, me)
                else -> json(401, """{"code":"token_not_valid","detail":"expired"}""")
            }
        }
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            (1..4).map { async { api.me() } }.forEach { assertEquals("ravi", it.await().username) }
        }
        assertEquals(1, refreshes)
    }

    @Test fun aRefusedRenewalEndsTheSignIn() = runTest {
        tokens.save("old", "R1")
        server.enqueue(json(401, """{"code":"token_not_valid","detail":"expired"}"""))
        server.enqueue(json(401, """{"code":"token_not_valid","detail":"Token is invalid or expired"}"""))
        val e = runCatching { api.me() }.exceptionOrNull() as ApiError
        assertEquals(ApiError.SESSION_EXPIRED, e.code)
        assertTrue(api.expired.value); assertNull(tokens.access())
    }

    @Test fun aBusyServerDoesNotEndTheSignIn() = runTest {
        tokens.save("old", "R1")
        server.enqueue(json(401, """{"code":"token_not_valid","detail":"expired"}"""))
        server.enqueue(json(429, """{"detail":"Slow down."}"""))
        runCatching { api.me() }
        assertTrue(!api.expired.value); assertEquals("R1", tokens.refresh())
    }
}
