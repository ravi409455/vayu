package `in`.carcid.vayu.core.media

import androidx.compose.ui.graphics.asImageBitmap

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Typeface
import android.location.Location
import android.location.LocationManager
import android.media.ExifInterface
import android.net.Uri
import android.os.Build
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Executors
import kotlin.coroutines.resume

/** The longest edge of a sent photo (plan: ~2048 px, ~500 KB). */
const val MAX_EDGE = 2048

/** A location fix as the answers store it: {lat, lng, accuracy}. Null without permission or signal. */
object Locator {
    private val executor = Executors.newSingleThreadExecutor()
    @Volatile var last: Location? = null
        private set

    fun allowed(ctx: Context) = ctx.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
        ctx.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    /** The phone's own Location switch is on. */
    fun enabled(ctx: Context) = ctx.getSystemService(LocationManager::class.java)?.isLocationEnabled == true

    @SuppressLint("MissingPermission")
    suspend fun fix(ctx: Context, timeoutMs: Long = 10_000): Location? {
        if (!allowed(ctx)) return null
        val lm = ctx.getSystemService(LocationManager::class.java) ?: return null
        val provider = listOf(if (Build.VERSION.SDK_INT >= 31) LocationManager.FUSED_PROVIDER else LocationManager.GPS_PROVIDER,
            LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER).firstOrNull { lm.isProviderEnabled(it) } ?: return null
        val got = withTimeoutOrNull(timeoutMs) {
            suspendCancellableCoroutine<Location?> { cont ->
                lm.getCurrentLocation(provider, null, executor) { cont.resume(it) }
            }
        }
        return (got ?: lm.getLastKnownLocation(provider))?.also { last = it }
    }

    fun answer(l: Location): Map<String, Any?> = mapOf(
        "lat" to "%.6f".format(l.latitude).toDouble(), "lng" to "%.6f".format(l.longitude).toDouble(),
        "accuracy" to Math.round(l.accuracy).toDouble())

    fun stampLine(l: Location?): String = l?.let { "%.6f, %.6f".format(it.latitude, it.longitude) } ?: "GPS unavailable"
}

/**
 * A photo as it is sent: upright, at most [MAX_EDGE] px, JPEG around 500 KB, with the stamp
 * (booking, expert, time, place) burned into the bottom-left corner.
 */
fun stampPhoto(src: File, dest: File, lines: List<String>) {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(src.path, bounds)
    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= MAX_EDGE) sample *= 2
    val raw = BitmapFactory.decodeFile(src.path, BitmapFactory.Options().apply { inSampleSize = sample })
        ?: error("Not a picture.")
    val turn = when (runCatching { ExifInterface(src.path).getAttributeInt(ExifInterface.TAG_ORIENTATION, 1) }.getOrDefault(1)) {
        ExifInterface.ORIENTATION_ROTATE_90 -> 90f; ExifInterface.ORIENTATION_ROTATE_180 -> 180f
        ExifInterface.ORIENTATION_ROTATE_270 -> 270f; else -> 0f
    }
    val scale = minOf(1f, MAX_EDGE.toFloat() / maxOf(raw.width, raw.height))
    val m = Matrix().apply { postScale(scale, scale); postRotate(turn) }
    val img = Bitmap.createBitmap(raw, 0, 0, raw.width, raw.height, m, true).copy(Bitmap.Config.ARGB_8888, true)
    if (img !== raw) raw.recycle()
    if (lines.isNotEmpty()) drawStamp(img, lines)
    for (quality in listOf(85, 75, 65)) {
        FileOutputStream(dest).use { img.compress(Bitmap.CompressFormat.JPEG, quality, it) }
        if (dest.length() <= 700_000) break
    }
    img.recycle()
}

/** A gallery photo: resized and turned upright like a camera shot, but never stamped (it isn't proof of this visit). */
fun shrinkPhoto(src: File, dest: File) = stampPhoto(src, dest, emptyList())

private fun drawStamp(img: Bitmap, lines: List<String>) {
    val c = Canvas(img)
    val size = img.width / 38f
    val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textSize = size; typeface = Typeface.MONOSPACE }
    val pad = size * 0.6f
    val width = lines.maxOf { text.measureText(it) } + pad * 2
    val height = lines.size * size * 1.3f + pad * 1.4f
    // an upright photo prints only its middle 4:3 band in the report (and the camera shows that band):
    // the stamp sits at the band's bottom so the report shows it (owner, 2026-11-27)
    val bottom = if (img.height > img.width) (img.height + img.width * 3f / 4f) / 2f else img.height.toFloat()
    c.drawRect(0f, bottom - height, width, bottom, Paint().apply { color = Color.argb(140, 0, 0, 0) })
    lines.forEachIndexed { i, l -> c.drawText(l, pad, bottom - height + pad + size * (i + 1) * 1.2f, text) }
}

/** Copy something the person picked (gallery, files) into the app's own folder. */
fun copyIn(ctx: Context, uri: Uri, dest: File): String? {
    val type = ctx.contentResolver.getType(uri)
    ctx.contentResolver.openInputStream(uri)?.use { input -> FileOutputStream(dest).use { input.copyTo(it) } } ?: return null
    return type
}

/** A small picture of the image at [path], decoded at about [size] px (whole-power-of-two sampling); null if it can't be read. */
fun thumb(path: String, size: Int): androidx.compose.ui.graphics.ImageBitmap? = runCatching {
    val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(path, o)
    var s = 1
    while (o.outWidth / (s * 2) >= size && o.outHeight / (s * 2) >= size) s *= 2
    BitmapFactory.decodeFile(path, BitmapFactory.Options().apply { inSampleSize = s })?.asImageBitmap()
}.getOrNull()
