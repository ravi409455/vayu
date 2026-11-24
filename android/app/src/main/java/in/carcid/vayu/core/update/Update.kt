package `in`.carcid.vayu.core.update

import `in`.carcid.vayu.core.api.ApiError
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.IOException
import java.security.MessageDigest

/** A newer build of the app (server: GET app/latest). [required]: this one may not start new jobs. */
data class AppUpdate(val code: Int, val name: String, val size: Long, val sha256: String, val notes: List<String>,
                     val url: String, val required: Boolean)

/** The update on offer, or null when this build ([current]) is the newest. */
fun parseUpdate(o: JsonObject, current: Int): AppUpdate? {
    val code = o["version_code"]?.jsonPrimitive?.intOrNull ?: return null
    if (code <= current) return null
    fun s(k: String) = o[k]?.jsonPrimitive?.contentOrNull.orEmpty()
    return AppUpdate(code, s("version_name"), o["size"]?.jsonPrimitive?.longOrNull ?: 0, s("sha256"),
        o["notes"]?.jsonArray?.mapNotNull { it.jsonPrimitive.contentOrNull }.orEmpty(), s("url"),
        required = current < (o["min_version"]?.jsonPrimitive?.intOrNull ?: 0))
}

/**
 * Download [u] into [file], reporting bytes so far; the file is kept only when its SHA-256 matches
 * (a cut-off or altered download is never offered for install).
 */
suspend fun download(http: OkHttpClient, u: AppUpdate, file: File, progress: (Long) -> Unit): File = withContext(Dispatchers.IO) {
    val part = File(file.path + ".part")
    try {
        http.newCall(Request.Builder().url(u.url).build()).execute().use { r ->
            if (!r.isSuccessful) throw ApiError("DOWNLOAD_FAILED", "The update could not be downloaded (${r.code}).", r.code)
            val digest = MessageDigest.getInstance("SHA-256")
            var done = 0L
            file.parentFile?.mkdirs()
            r.body!!.byteStream().use { input ->
                part.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        ensureActive()
                        val n = input.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n); digest.update(buf, 0, n)
                        done += n; progress(done)
                    }
                }
            }
            val sha = digest.digest().joinToString("") { "%02x".format(it) }
            if (!sha.equals(u.sha256, ignoreCase = true)) {
                part.delete()
                throw ApiError("DOWNLOAD_DAMAGED", "The download was damaged. Try again.", 0)
            }
            if (!part.renameTo(file)) throw ApiError("DOWNLOAD_FAILED", "The update could not be saved.", 0)
            file
        }
    } catch (e: IOException) {
        part.delete()
        throw ApiError(ApiError.NETWORK, "No connection. Try again when you have signal.", 0)
    }
}
