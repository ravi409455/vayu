package `in`.carcid.vayu.core.alerts

import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.api.FakeServer
import `in`.carcid.vayu.core.auth.MemoryTokenStore
import `in`.carcid.vayu.core.draft.Draft
import `in`.carcid.vayu.core.draft.LocalFile
import `in`.carcid.vayu.core.sync.Job
import `in`.carcid.vayu.core.update.AppUpdate
import `in`.carcid.vayu.core.update.download
import `in`.carcid.vayu.core.update.parseUpdate
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import java.time.Instant
import java.time.ZoneId

/** Phase 17 phone-side rules: reminders, stuck photos, app updates, the bell and push calls. */
class AlertsTest {
    private val zone = ZoneId.of("Asia/Kolkata")
    private val server = FakeServer()
    private val api = Api(server.url, MemoryTokenStore().apply { save("a", "r") })
    @After fun stop() = server.stop()

    private fun j(id: String, time: String, stage: String = "assigned", mine: Boolean = true, draft: String? = null, date: String = "2026-11-24") =
        Job(id, "DEMO-$id", stage, "Farhan Ali", "", "MG Road", "Pune", "", "PDI", date, time, mine, draft, versions = emptyMap())

    @Test fun remindersAnHourBeforeOnlyForJobsNotStartedAndStillAhead() {
        val now = Instant.parse("2026-11-24T04:00:00Z")             // 09:30 in India
        val got = reminders(listOf(j("8", "11:00"), j("9", "10:00"), j("10", "12:00", stage = "in_progress"),
            j("11", "12:00", mine = false), j("12", "12:00", draft = "d"), j("13", ""), j("14", "15:00", stage = "completed")), now, zone)
        assertEquals(listOf("8"), got.map { it.jobId })
        assertEquals(Instant.parse("2026-11-24T04:30:00Z"), got[0].at)
        assertEquals("In 1 hour: DEMO-8 at 11:00", got[0].title)
        assertEquals("Farhan Ali · MG Road", got[0].body)
    }

    @Test fun photosStuckForTwoHoursAreFound() {
        val now = Instant.parse("2026-11-24T10:00:00Z")
        fun f(path: String, sent: Boolean = false) = LocalFile(path, "inspection", "door", "photo", path, "image/jpeg", "camera", 1, "x", "Door", sent = sent)
        val drafts = listOf(Draft("b1", "DEMO-1", "", emptyMap(), "pdi", files = listOf(f("old"))),
            Draft("b2", "DEMO-2", "", emptyMap(), "pdi", files = listOf(f("new"))),
            Draft("b3", "DEMO-3", "", emptyMap(), "pdi", files = listOf(f("old", sent = true))),
            Draft("b4", "DEMO-4", "", emptyMap(), "pdi", files = listOf(f("gone"))))
        val taken = mapOf("old" to now.minusSeconds(3 * 3600), "new" to now.minusSeconds(600))
        assertEquals(listOf("b1" to "DEMO-1"), stuck(drafts, now) { taken[it] })
    }

    @Test fun anUpdateIsOfferedOnlyWhenNewer() {
        fun o(s: String) = Json.parseToJsonElement(s).jsonObject
        val body = """{"version_code":5,"version_name":"1.1.0","size":24000000,"sha256":"ab","notes":["Faster"],"url":"u","min_version":3}"""
        assertEquals(AppUpdate(5, "1.1.0", 24000000, "ab", listOf("Faster"), "u", required = true), parseUpdate(o(body), 2))
        assertFalse(parseUpdate(o(body), 4)!!.required)
        assertNull(parseUpdate(o(body), 5))
        assertNull(parseUpdate(o("""{"version_code":null,"min_version":0}"""), 1))
    }

    @Test fun downloadKeepsOnlyACheckedFile() = runTest {
        val bytes = "PK fake apk"
        val sha = MessageDigest.getInstance("SHA-256").digest(bytes.toByteArray()).joinToString("") { "%02x".format(it) }
        server.on("GET apk", bytes)
        val dir = Files.createTempDirectory("upd").toFile()
        val seen = mutableListOf<Long>()
        val u = AppUpdate(5, "1.1.0", 11, sha, emptyList(), server.raw("/api/v1/apk"), false)
        val f = download(OkHttpClient(), u, File(dir, "vayu.apk")) { seen += it }
        assertEquals(bytes, f.readText()); assertEquals(11L, seen.last())
        val bad = runCatching { download(OkHttpClient(), u.copy(sha256 = "00"), File(dir, "bad.apk")) {} }.exceptionOrNull() as ApiError
        assertEquals("DOWNLOAD_DAMAGED", bad.code)
        assertFalse(File(dir, "bad.apk").exists() || File(dir, "bad.apk.part").exists())
        server.on("GET apk", "", 404)
        assertEquals("DOWNLOAD_FAILED", (runCatching { download(OkHttpClient(), u, File(dir, "x.apk")) {} }.exceptionOrNull() as ApiError).code)
        val off = u.copy(url = "http://127.0.0.1:1/none")
        assertEquals(ApiError.NETWORK, (runCatching { download(OkHttpClient(), off, File(dir, "y.apk")) {} }.exceptionOrNull() as ApiError).code)
    }

    @Test fun bellSwitchesAndPushTokenCalls() = runTest {
        server.on("GET notifications", """{"unread":1,"results":[]}""")
        assertEquals(1, api.notifications()["unread"].toString().toInt())
        server.on("POST notifications/read", """{"unread":0}""")
        assertEquals(0, api.markRead(listOf(4L)))
        assertEquals(0, api.markRead(null))
        assertEquals(listOf("""{"ids":[4]}""", """{"all":true}"""), server.bodiesOf("POST notifications/read"))
        server.on("PATCH auth/me/profile", """{"id":1,"username":"ops","name":"","role":"ops","must_change_password":false,
            "theme":"light","notify_prefs":{"started":false,"submitted":true}}""")
        assertEquals(setOf("started"), api.setNotify("started", false).muted)
        assertEquals("""{"notify_prefs":{"started":false}}""", server.bodiesOf("PATCH auth/me/profile").last())
        server.on("POST devices/push-token", "", 204)
        api.pushToken("tok")
        assertEquals("""{"token":"tok"}""", server.bodiesOf("POST devices/push-token").single())
        server.on("GET app/latest", """{"version_code":null,"min_version":0}""")
        assertTrue(api.appLatest().containsKey("min_version"))
    }

    @Test fun signingOutTakesTheNoticesOffThePhone() {
        var cleared = 0
        val root = Files.createTempDirectory("vayu").toFile()
        val g = `in`.carcid.vayu.Graph(api, MemoryTokenStore(), root, {}, clearNotices = { cleared++ })
        g.forgetCopies(3)
        assertEquals(1, cleared)
    }
}
