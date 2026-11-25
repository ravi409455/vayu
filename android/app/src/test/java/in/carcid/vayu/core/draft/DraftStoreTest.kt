package `in`.carcid.vayu.core.draft

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

class DraftStoreTest {
    private val dir = File(Files.createTempDirectory("vayu").toFile(), "drafts-3")
    private fun draft(files: List<LocalFile> = emptyList()) = Draft(BOOKING, "DEMO-2", "Arjun", mapOf("inspection" to 7), "pdi", files = files)
    private fun file(name: String, ageMs: Long = 2 * 60 * 60 * 1000) = File(File(dir, "files").apply { mkdirs() }, name)
        .apply { writeBytes(ByteArray(4)); setLastModified(System.currentTimeMillis() - ageMs) }

    @Test fun savesAreWrittenInTheBackgroundNewestLastAndADiscardIsNeverUndone() {
        val queued = mutableListOf<Runnable>()
        val store = DraftStore(dir, { queued += it })
        store.save(draft()); store.save(draft().copy(step = 3))
        assertEquals(3, store.get(BOOKING)!!.step)                         // read at once, before it is written
        assertEquals(1, store.all().size)
        queued.forEach { it.run() }; queued.clear()
        assertEquals(3, DraftStore(dir).get(BOOKING)!!.step)              // the newest is on disk
        store.save(draft().copy(step = 4)); store.discard(BOOKING)
        queued.forEach { it.run() }
        assertFalse(File(dir, "$BOOKING.json").exists())                   // a late write does not bring it back
    }

    @Test fun aFullPhoneKeepsTheAnswersAndSaysSo() {
        dir.mkdirs(); dir.setWritable(false)
        try {
            val store = DraftStore(dir)
            store.save(draft().copy(step = 2))
            assertTrue(store.writeFailed.value)
            assertEquals(2, store.get(BOOKING)!!.step)                     // still there, in memory
        } finally { dir.setWritable(true) }
    }

    @Test fun anUnreadableDraftIsReportedOnceAndKept() {
        dir.mkdirs(); File(dir, "$BOOKING.json").writeText("{not json")
        var reports = 0
        val store = DraftStore(dir, onDamaged = { _, _ -> reports++ })
        assertNull(store.get(BOOKING)); store.all(); store.all()
        assertEquals(1, reports)
        val shot = file("orphan.jpg")
        store.sweep()
        assertTrue(shot.exists())                                         // its photos might be these: nothing is swept
        assertTrue(File(dir, "$BOOKING.json").exists())
    }

    @Test fun startingALeadWhoseDraftCantBeReadKeepsTheDamagedOne() {
        // N-4: a new draft may be started, but the old file is moved aside, never overwritten or swept
        dir.mkdirs(); File(dir, "$BOOKING.json").writeText("{not json")
        val store = DraftStore(dir)
        store.setAsideDamaged(BOOKING)
        store.save(draft().copy(step = 1))
        assertEquals("{not json", File(dir, "$BOOKING.damaged").readText())
        assertEquals(listOf(BOOKING), store.unreadable())                  // sign-out still stops
        val shot = file("orphan.jpg")
        store.sweep()
        assertTrue(shot.exists())                                         // its photos might be these
    }

    @Test fun filesNoDraftRefersToAreSweptOnceAnHourOld() {
        val kept = file("kept.jpg")
        val store = DraftStore(dir)
        store.save(draft(listOf(LocalFile("f1", "inspection", "door_photos", "photo", kept.path, "image/jpeg", "camera", 4, "", "Door 1"))))
        val shot = file("never-confirmed.jpg")
        val fresh = file("being-taken.jpg", ageMs = 0)
        val tmp = File(dir, "$BOOKING.json.x.tmp").apply { writeText("half"); setLastModified(System.currentTimeMillis() - 2 * 60 * 60 * 1000) }
        store.sweep()
        assertTrue(kept.exists()); assertTrue(fresh.exists())
        assertFalse(shot.exists()); assertFalse(tmp.exists())
    }
}
