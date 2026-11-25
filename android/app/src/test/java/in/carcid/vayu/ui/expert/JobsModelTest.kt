package `in`.carcid.vayu.ui.expert

import `in`.carcid.vayu.core.api.Api
import `in`.carcid.vayu.core.auth.MemoryTokenStore
import `in`.carcid.vayu.core.sync.JobStore
import `in`.carcid.vayu.core.sync.job
import `in`.carcid.vayu.core.sync.payload
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.time.Instant

/** Requirement 9: a time is "checked" only when the phone synced today and its clock was not changed since. */
class JobsModelTest {
    private val store = JobStore(File(Files.createTempDirectory("vayu").toFile(), "jobs-1.json"))
    private var now = Instant.parse("2026-11-24T05:00:00Z").toEpochMilli()
    private var boot = 3_600_000L
    private val hour = 3_600_000L

    private fun model() = JobsModel(Api("http://localhost/", MemoryTokenStore()), { store }, CoroutineScope(Dispatchers.Unconfined),
        { now }, {}, {}, elapsed = { boot }).apply { open(1, offline = true) }

    @Test fun neverSyncedIsNotChecked() = assertFalse(model().verified())

    @Test fun aClockChangedByHandAfterTheSyncIsNoLongerTrusted() {
        store.apply(payload(job("1"), time = "2026-11-24T05:00:00Z"), now, elapsed = boot)
        val m = model()
        assertTrue(m.verified())
        now += hour; boot += hour
        assertTrue(m.verified())                       // time just went by
        now += 3 * hour                                // the expert set the clock 3 hours ahead
        assertFalse(m.verified())
    }

    @Test fun aRestartOrANewDayNeedsAFreshSync() {
        store.apply(payload(job("1"), time = "2026-11-24T05:00:00Z"), now, elapsed = boot)
        val m = model()
        now += hour; boot = 1_000                      // the phone restarted
        assertFalse(m.verified())
        store.apply(payload(job("1"), time = "2026-11-24T06:00:00Z"), now, elapsed = boot)
        assertTrue(m.verified())
        now += 24 * hour; boot += 24 * hour            // the next day
        assertFalse(m.verified())
    }

    @Test fun todayIsIndiaTodayWhateverZoneThePhoneIsIn() {
        val was = java.util.TimeZone.getDefault()
        java.util.TimeZone.setDefault(java.util.TimeZone.getTimeZone("Europe/London"))
        try {
            now = Instant.parse("2026-11-24T20:00:00Z").toEpochMilli()          // 01:30 on the 25th in India
            org.junit.Assert.assertEquals(java.time.LocalDate.parse("2026-11-25"), model().today())
        } finally { java.util.TimeZone.setDefault(was) }
    }
}
