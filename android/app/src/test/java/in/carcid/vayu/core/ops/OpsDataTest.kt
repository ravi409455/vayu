package `in`.carcid.vayu.core.ops

import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.api.FakeServer
import `in`.carcid.vayu.core.auth.MemoryTokenStore
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import java.nio.file.Files

/** F-095: every search and filter is its own saved copy; the oldest go once there are too many. */
class OpsDataTest {
    private val server = FakeServer()
    @After fun stop() = server.stop()

    @Test fun theSavedCopiesStopGrowingAndTheOldestGoFirst() = runTest {
        val dir = Files.createTempDirectory("ops").toFile()
        var now = 1_000L
        val data = OpsData(Api(server.url, MemoryTokenStore().apply { save("A", "R") }), dir, clock = { now }, keep = 3)
        (1..5).forEach { i ->
            server.on("GET bookings", """{"count":$i,"results":[]}""")
            data.load("bookings?search=$i"); now += 1_000
            Thread.sleep(20)                                  // file times tell the copies apart
        }
        assertEquals(3, dir.listFiles()!!.size)
        assertNull(data.saved("bookings?search=1"))
        assertNotNull(data.saved("bookings?search=5"))
    }
}
