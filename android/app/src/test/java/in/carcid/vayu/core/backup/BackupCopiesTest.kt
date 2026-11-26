package `in`.carcid.vayu.core.backup

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** docs/plan-media-backup.md part B: copies outside the app that survive an uninstall, and their clean-up. */
class BackupCopiesTest {
    private val day = 24 * 60 * 60 * 1000L
    private var now = 1_000 * day
    private val folder = Files.createTempDirectory("vayu-docs").toFile().resolve("Vayu")
    private val app = Files.createTempDirectory("vayu-app").toFile()
    private var access = true
    private var free = Long.MAX_VALUE

    private fun copies() = BackupCopies(folder, app.resolve("backup-index.json"), { now }, { access }, { free })

    private fun photo(text: String = "jpeg bytes") = File.createTempFile("shot", ".jpg", app).apply { writeText(text) }

    private val b = BackupCopies.Copy(bookingId = "b1", code = "TST-1014", fileId = "f1", page = "Exterior", label = "Front left 1")

    @Test fun aCopyIsNamedByPageAndFieldInTheBookingFolderHiddenFromTheGallery() {
        val c = copies()
        assertEquals(BackupCopies.Result.COPIED, c.copy(b, photo()))
        assertEquals("jpeg bytes", folder.resolve("TST-1014/Exterior - Front left 1.jpg").readText())
        assertTrue(folder.resolve(".nomedia").exists())
    }

    @Test fun theEndingComesFromTheFileTypeNotThePickedFilesName() {
        val picked = File.createTempFile("pick", ".file", app).apply { writeText("%PDF") }
        copies().copy(b.copy(label = "RC copy", contentType = "application/pdf"), picked)
        assertTrue(folder.resolve("TST-1014/Exterior - RC copy.pdf").exists())
    }

    @Test fun namesAreCleanedAndNeverOverwrite() {
        val c = copies()
        val odd = b.copy(page = "Tyres / Wheels", label = "Front: \"left\"\n1")
        c.copy(odd, photo("one"))
        c.copy(odd.copy(fileId = "f2"), photo("two"))
        val names = folder.resolve("TST-1014").list()!!.sorted()
        assertEquals(listOf("Tyres - Wheels - Front - left - 1 (2).jpg", "Tyres - Wheels - Front - left - 1.jpg"), names)
        assertEquals("one", folder.resolve("TST-1014/Tyres - Wheels - Front - left - 1.jpg").readText())
    }

    @Test fun aBookingCodeThatIsNotAPlainFolderNameIsCleaned() {
        copies().copy(b.copy(code = "../TST 9"), photo())
        assertTrue(folder.resolve("TST 9/Exterior - Front left 1.jpg").exists())
    }

    @Test fun withoutFileAccessNothingIsCopied() {
        access = false
        assertEquals(BackupCopies.Result.NO_ACCESS, copies().copy(b, photo()))
        assertFalse(folder.exists())
    }

    @Test fun aFullPhoneSkipsTheCopy() {
        free = 5
        assertEquals(BackupCopies.Result.PHONE_FULL, copies().copy(b, photo()))
        assertFalse(folder.resolve("TST-1014").exists())
    }

    @Test fun aCopyTheServerStillNeedsIsNeverDeleted() {
        val c = copies(); c.copy(b, photo())
        now += 30 * day
        c.clean(mapOf("f1" to BackupCopies.State.WAITING))
        assertTrue(folder.resolve("TST-1014/Exterior - Front left 1.jpg").exists())
    }

    @Test fun aCopyTheServerHasGoesWhenItIsTwoDaysOld() {
        val c = copies(); c.copy(b, photo())
        now += day
        c.clean(mapOf("f1" to BackupCopies.State.DONE))
        assertTrue(folder.resolve("TST-1014/Exterior - Front left 1.jpg").exists())
        now += day
        c.clean(mapOf("f1" to BackupCopies.State.DONE))
        assertFalse(folder.resolve("TST-1014").exists())                     // the empty folder goes too
    }

    @Test fun aCopyTheServerWillNeverTakeGoesTwoDaysAfterThePhoneLearnsIt() {
        val c = copies(); c.copy(b, photo())
        now += 10 * day
        c.clean(mapOf("f1" to BackupCopies.State.NEVER))                       // learnt now: 2 more days
        assertTrue(folder.resolve("TST-1014/Exterior - Front left 1.jpg").exists())
        now += 2 * day
        c.clean(mapOf("f1" to BackupCopies.State.NEVER))
        assertFalse(folder.resolve("TST-1014/Exterior - Front left 1.jpg").exists())
    }

    @Test fun aDiscardedLeadOrRemovedPhotoLosesItsCopyAtOnce() {
        val c = copies(); c.copy(b, photo()); c.copy(b.copy(fileId = "f2", label = "Front left 2"), photo())
        c.drop("f2")
        assertFalse(folder.resolve("TST-1014/Exterior - Front left 2.jpg").exists())
        c.dropBooking("b1")
        assertFalse(folder.resolve("TST-1014").exists())
    }

    @Test fun aCopyWhoseDraftIsGoneGoesOnlyWhenTheServerHadIt() {
        val c = copies(); c.copy(b, photo()); c.copy(b.copy(fileId = "f2", label = "Front left 2"), photo())
        c.clean(mapOf("f1" to BackupCopies.State.DONE, "f2" to BackupCopies.State.WAITING))
        now += 3 * day
        c.clean(emptyMap())                                                    // both drafts gone from the phone
        assertFalse(folder.resolve("TST-1014/Exterior - Front left 1.jpg").exists())   // the server had it
        assertFalse(folder.resolve("TST-1014/Exterior - Front left 2.jpg").exists())   // discarded
    }

    @Test fun nothingGoesWhileADraftCantBeRead() {
        val c = copies(); c.copy(b, photo())
        now += 30 * day
        c.clean(emptyMap(), sure = false)                                      // a damaged draft may still use it
        assertTrue(folder.resolve("TST-1014/Exterior - Front left 1.jpg").exists())
    }

    @Test fun copiesFromAnEarlierInstallAreFoundAndGoTwoDaysAfterThat() {
        copies().copy(b, photo())
        app.resolve("backup-index.json").delete()                              // uninstalled: the app's own storage is gone
        now += 5 * day
        val c = copies()
        c.clean(emptyMap())
        val found = c.found.value!!
        assertEquals(listOf("TST-1014"), found.codes)
        assertEquals(1, found.files)
        assertEquals(now + 2 * day, found.deleteAt)
        now += day; c.clean(emptyMap())
        assertTrue(folder.resolve("TST-1014/Exterior - Front left 1.jpg").exists())
        now += day; c.clean(emptyMap())
        assertFalse(folder.resolve("TST-1014").exists())
        assertNull(c.found.value)
    }

    @Test fun theIndexIsKeptAcrossAppStarts() {
        copies().copy(b, photo())
        now += 5 * day
        val c = copies(); c.clean(mapOf("f1" to BackupCopies.State.WAITING))
        assertNull(c.found.value)                                              // its own copy, not "found"
    }

    @Test fun aHalfWrittenCopyIsNotTakenForAFoundOne() {
        folder.resolve("TST-1014").mkdirs()
        folder.resolve("TST-1014/.Exterior - Front left 1.jpg.part").writeText("half")
        val c = copies(); c.clean(emptyMap())
        assertNull(c.found.value)
    }
}
