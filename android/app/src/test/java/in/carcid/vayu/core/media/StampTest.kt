package `in`.carcid.vayu.core.media

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files

@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34])
class StampTest {
    private val dir = Files.createTempDirectory("stamp").toFile()
    private fun white(w: Int = 400, h: Int = 300): File = File(dir, "in.jpg").also { f ->
        val b = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.WHITE) }
        FileOutputStream(f).use { b.compress(Bitmap.CompressFormat.JPEG, 95, it) }
    }
    /** How dark the stamp's corner (bottom left) is: 0 white … 255 black. */
    private fun corner(f: File) = BitmapFactory.decodeFile(f.path).let { 255 - Color.red(it.getPixel(4, it.height - 4)) }

    @Test fun aCameraPhotoIsStamped() {
        val out = File(dir, "cam.jpg"); stampPhoto(white(), out, listOf("DEMO-8 · Ravi · 24 Nov 2026 15:41", "Pune"))
        assertTrue(corner(out) > 60)
    }

    /** An upright camera shot keeps only the middle 4:3 band the camera showed bright, stamped at its bottom. */
    @Test fun anUprightCameraShotKeepsOnlyTheStrip() {
        val out = File(dir, "up.jpg"); stampPhoto(white(300, 400), out, listOf("DEMO-8 · Ravi · 24 Nov 2026 15:41", "Pune"), strip = true)
        val img = BitmapFactory.decodeFile(out.path)
        assertEquals(300, img.width); assertEquals(225, img.height)
        assertTrue(corner(out) > 60)
    }

    /** Sideways (already 4:3), or a gallery photo: nothing is cut. */
    @Test fun aWidePhotoOrAGalleryPhotoIsNotCut() {
        val wide = File(dir, "wide.jpg"); stampPhoto(white(400, 300), wide, listOf("x"), strip = true)
        assertEquals(300, BitmapFactory.decodeFile(wide.path).height)
        val gal = File(dir, "gal2.jpg"); shrinkPhoto(white(300, 400), gal)
        assertEquals(400, BitmapFactory.decodeFile(gal.path).height)
    }

    /** F-225: a photo from the gallery is not proof of this visit; it is resized, never stamped. */
    @Test fun aGalleryPhotoIsResizedButNotStamped() {
        val out = File(dir, "gal.jpg"); shrinkPhoto(white(), out)
        assertTrue("no stamp box", corner(out) < 10)
    }
}
