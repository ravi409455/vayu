package `in`.carcid.vayu.core.media

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
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

    /** An upright photo: the report prints its middle 4:3 band, so the stamp sits at the band's bottom. */
    @Test fun anUprightPhotoIsStampedInsideTheReportBand() {
        val out = File(dir, "up.jpg"); stampPhoto(white(300, 400), out, listOf("DEMO-8 · Ravi · 24 Nov 2026 15:41", "Pune"))
        val img = BitmapFactory.decodeFile(out.path)
        val bandBottom = (img.height + img.width * 3 / 4) / 2
        val dark = { y: Int -> 255 - Color.red(img.getPixel(4, y)) }
        assertTrue("stamp just inside the band", dark(bandBottom - 4) > 60)
        assertTrue("nothing below the band", dark(img.height - 4) < 10)
    }

    /** F-225: a photo from the gallery is not proof of this visit; it is resized, never stamped. */
    @Test fun aGalleryPhotoIsResizedButNotStamped() {
        val out = File(dir, "gal.jpg"); shrinkPhoto(white(), out)
        assertTrue("no stamp box", corner(out) < 10)
    }
}
