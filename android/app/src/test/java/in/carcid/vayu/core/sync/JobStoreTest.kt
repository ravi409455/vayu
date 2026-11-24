package `in`.carcid.vayu.core.sync

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** A sync payload like GET sync/jobs returns (apps/bookings/sync.py). */
fun payload(jobs: String, forms: String = "{}", time: String = "2026-11-24T05:00:00Z") = Json.parseToJsonElement("""
    {"server_time":"$time","jobs":[$jobs],"forms":$forms,"changes":[],
     "types":{"pdi":"PDI"},
     "lists":{"city":[{"key":"pune","label":"Pune"}],"car_make_model":[{"key":"nexon","label":"Tata Nexon"}]}}
""").jsonObject

fun job(id: String, stage: String = "assigned", date: String = "2026-11-24", time: String = "15:30",
        version: Int? = 7, mine: Boolean = true, start: Int? = null, end: Int? = null, code: String = "DEMO-$id") = """
    {"id":"$id","booking_id":"$code","stage":"$stage","inspection_type":"pdi",
     "answers":{"customer_name":"Arjun Mehta","customer_phone":"+919876500000","address":"MG Road",
                "city":"pune","car_make_model":"nexon","inspection_date":"$date","inspection_time":"$time:00"},
     "assigned_to_me":$mine,"my_draft":null,"versions":{"start":$start,"inspection":$version,"end":$end}}
"""

class JobStoreTest {
    private val file = File(Files.createTempDirectory("vayu").toFile(), "jobs.json")

    @Test fun jobsAreReadWithLabelsAndSurviveARestart() {
        JobStore(file).apply(payload(job("2"), forms = """{"7":{"pages":[]}}"""), phoneNow = 0)
        val j = JobStore(file).jobs().single()                       // a fresh store reads the file
        assertEquals("DEMO-2", j.bookingId)
        assertEquals("Pune", j.city); assertEquals("Tata Nexon", j.car); assertEquals("PDI", j.type)
        assertEquals("15:30", j.time); assertEquals("2026-11-24", j.date)
        assertTrue(JobStore(file).readyOffline(j))
    }

    @Test fun formsAreKeptAcrossSyncsAndDroppedWhenNoJobUsesThem() {
        val s = JobStore(file)
        s.apply(payload(job("1"), forms = """{"7":{"pages":[]}}"""), 0)
        s.apply(payload(job("1")), 0)                                  // server sent nothing new
        assertEquals(setOf(7), s.haveVersions())
        s.apply(payload(job("1", version = 8), forms = """{"8":{"pages":[]}}"""), 0)
        assertEquals(setOf(8), s.haveVersions())
    }

    @Test fun formsADraftIsPinnedToAreKeptWhenTheJobMovesOn() {
        val s = JobStore(file)
        s.apply(payload(job("1"), forms = """{"7":{"pages":[]}}"""), 0)
        s.apply(payload(job("1", version = 8), forms = """{"8":{"pages":[]}}"""), 0, keep = setOf(7))   // Admin published v8
        assertEquals(setOf(7, 8), s.haveVersions())
        s.apply(payload(""), 0, keep = setOf(7))                                // the job left the list
        assertEquals(setOf(7), s.haveVersions())
        s.clear(keep = setOf(7))                                                 // signed out by the server
        assertEquals(setOf(7), JobStore(file).haveVersions())
        assertTrue(JobStore(file).jobs().isEmpty())
    }

    @Test fun aJobWithoutItsFormIsNotReadyOffline() {
        val s = JobStore(file)
        s.apply(payload(job("1")), 0)
        assertFalse(s.readyOffline(s.jobs().single()))
        s.apply(payload(job("2", version = null)), 0)
        assertFalse(s.readyOffline(s.jobs().single()))
    }

    @Test fun theClockOffsetIsServerMinusPhone() {
        val s = JobStore(file)
        val server = java.time.Instant.parse("2026-11-24T05:00:00Z").toEpochMilli()
        s.apply(payload(job("1"), time = "2026-11-24T10:30:00+05:30"), phoneNow = server - 90_000)
        assertEquals(90_000L, s.clockOffset())
        assertEquals("2026-11-24T10:30:00+05:30", s.since())
        assertEquals(server - 90_000, s.syncedAt())
    }

    @Test fun jobsAreSortedByDayThenTimeAndClearForgetsEverything() {
        val s = JobStore(file)
        s.apply(payload(job("a", time = "17:00") + "," + job("b", time = "09:00") + "," + job("c", date = "2026-11-23")), 0)
        assertEquals(listOf("c", "b", "a"), s.jobs().map { it.id })
        s.clear()
        assertTrue(s.jobs().isEmpty()); assertNull(s.since()); assertFalse(file.exists())
        s.apply(payload(job("late")), 0)                              // a sync that finishes after sign-out
        assertFalse(file.exists())
    }

    @Test fun aDamagedFileReadsAsEmpty() {
        file.writeText("{not json")
        assertTrue(JobStore(file).jobs().isEmpty())
    }
}
