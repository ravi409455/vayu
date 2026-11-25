package `in`.carcid.vayu.core.api

import `in`.carcid.vayu.core.s

import `in`.carcid.vayu.core.auth.TokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/** An error the server explained ({code, detail, ...}), or NETWORK when there is no connection. */
class ApiError(val code: String, override val message: String, val status: Int,
               val extra: JsonObject = JsonObject(emptyMap())) : Exception(message) {
    companion object {
        const val NETWORK = "NETWORK"
        /** The sign-in could not be renewed (60 days, or ended elsewhere): sign in again; drafts stay. */
        const val SESSION_EXPIRED = "SESSION_EXPIRED"
    }
}

data class Me(val id: Int, val username: String, val name: String, val role: String,
              val mustChangePassword: Boolean, val theme: String,
              /** What this person may do ({permission: all|own} keys), from auth/me. */
              val permissions: Set<String> = emptySet(),
              /** Ops' notification switches that are off ("submitted", "started", "new_bookings"). */
              val muted: Set<String> = emptySet()) {
    fun can(p: String) = p in permissions
    val initials: String get() = initials(name.ifBlank { username })
}

/** "Ravi Kumar" → "RK": the first letters of the first two words (avatars). */
fun initials(name: String): String = name.split(" ").filter { it.isNotBlank() }.take(2).joinToString("") { it.first().uppercase() }

/** The Vayu API, as the app uses it. Tokens are refreshed once on a 401; a revoked phone signs out. */
class Api(private val baseUrl: String, private val tokens: TokenStore,
          // a dead connection gives up after 5 s (screens then show the saved copy); a slow but
          // working one keeps the usual time to send and receive
          private val http: OkHttpClient = OkHttpClient.Builder().connectTimeout(5, java.util.concurrent.TimeUnit.SECONDS).build()) {

    private val json = "application/json".toMediaType()

    /** Set when the sign-in could not be renewed: the app asks the person to sign in again. */
    val expired = kotlinx.coroutines.flow.MutableStateFlow(false)

    suspend fun login(username: String, password: String, deviceName: String): Me {
        val body = call("POST", "auth/login", buildJsonObject {
            put("username", username); put("password", password)
            put("client", "mobile"); put("device_name", deviceName)
        }, auth = false)
        tokens.save(body.s("access"), body.s("refresh"))
        expired.value = false
        return me()
    }

    suspend fun me(): Me = parseMe(call("GET", "auth/me"))

    suspend fun changePassword(old: String, new: String) {
        call("POST", "auth/change-password", buildJsonObject { put("old_password", old); put("new_password", new) })
    }

    suspend fun setTheme(theme: String): Me = parseMe(call("PATCH", "auth/me/profile", buildJsonObject { put("theme", theme) }))

    /** Ops: switch one kind of notification on or off (problems are always on). */
    suspend fun setNotify(key: String, on: Boolean): Me =
        parseMe(call("PATCH", "auth/me/profile", buildJsonObject { put("notify_prefs", buildJsonObject { put(key, on) }) }))

    /** This phone's Firebase token, so the server can push to it. */
    suspend fun pushToken(token: String) { call("POST", "devices/push-token", buildJsonObject { put("token", token) }) }

    /** The bell: latest notifications and how many are unread. */
    suspend fun notifications(): JsonObject = call("GET", "notifications")

    /** Mark these notifications read (all of them when [ids] is null); returns the unread count. */
    suspend fun markRead(ids: List<Long>?): Int = call("POST", "notifications/read", buildJsonObject {
        if (ids == null) put("all", true) else put("ids", kotlinx.serialization.json.JsonArray(ids.map { JsonPrimitive(it) }))
    })["unread"]?.jsonPrimitive?.intOrNull ?: 0

    /** The newest app build ({version_code, url, sha256, size, notes, min_version}). */
    suspend fun appLatest(): JsonObject = call("GET", "app/latest")

    /** Tells the server what this phone still holds; returns the minimum app version it accepts. */
    suspend fun heartbeat(drafts: Int, files: Int): Int =
        call("POST", "devices/heartbeat", buildJsonObject { put("drafts", drafts); put("files", files) })
            .getValue("min_app_version").jsonPrimitive.intOrNull ?: 0

    /**
     * Everything an expert needs offline (B2). [have]: form versions already on the phone; [since]:
     * last server_time; [drafts]: versions the phone's drafts are pinned to (sent even when no listed job uses them).
     */
    suspend fun syncJobs(have: Set<Int>, since: String?, drafts: Set<Int> = emptySet()): JsonObject {
        val q = buildList {
            if (have.isNotEmpty()) add("have=" + have.sorted().joinToString(","))
            if (drafts.isNotEmpty()) add("drafts=" + drafts.sorted().joinToString(","))
            if (since != null) add("since=" + java.net.URLEncoder.encode(since, "UTF-8"))
        }
        return call("GET", "sync/jobs" + if (q.isEmpty()) "" else "?" + q.joinToString("&"))
    }

    /**
     * Start a job with its check-in (B: submissions.start). Same [clientUuid] = same start (safe to
     * retry). [versions]: the form versions the phone pinned and filled (start, inspection, end);
     * the server keeps them if they were the latest published at [startedAt].
     */
    suspend fun start(bookingId: String, clientUuid: String, startedAt: String?, inspectionType: String,
                      startAnswers: JsonObject, appVersion: Int, versions: Map<String, Int?> = emptyMap(),
                      /** The phone's clock wasn't checked against the server that day (requirement 9). */
                      unverifiedTime: Boolean = false): JsonObject =
        call("POST", "bookings/$bookingId/start", buildJsonObject {
            put("client_uuid", clientUuid); put("inspection_type", inspectionType)
            put("unverified_time", unverifiedTime)
            if (startedAt != null) put("client_started_at", startedAt)
            versions["inspection"]?.let { put("form_version", it) }
            versions["start"]?.let { put("start_version", it) }
            versions["end"]?.let { put("end_version", it) }
            put("start_answers", startAnswers)
        }, headers = mapOf("X-App-Version" to appVersion.toString()))

    /** Submit the answers (idempotent by [submissionUuid]). */
    suspend fun submit(bookingId: String, submissionUuid: String, formVersion: Int?, answers: JsonObject,
                       /** The phone's clock was unreliable at some point of this inspection (the server keeps "true"). */
                       unverifiedTime: Boolean = false): JsonObject =
        call("POST", "bookings/$bookingId/submit", buildJsonObject {
            put("client_submission_uuid", submissionUuid)
            put("unverified_time", unverifiedTime)
            if (formVersion != null) put("form_version", formVersion)
            put("answers", answers)
        })

    /** Register a file (same client_uuid = same file); returns id, status, part_size and part URLs. */
    suspend fun mediaInitiate(bookingId: String, clientUuid: String, fieldKey: String, kind: String,
                              contentType: String, size: Long, sha256: String, source: String, replaces: String? = null): JsonObject =
        call("POST", "media/initiate", buildJsonObject {
            put("booking", bookingId); put("client_uuid", clientUuid); put("field_key", fieldKey); put("kind", kind)
            put("content_type", contentType); put("size", size); put("sha256", sha256); put("source", source)
            // Ops replacing a submitted file say which one (the old one stays as history)
            if (replaces != null) put("replaces", replaces)
        })

    suspend fun media(id: String): JsonObject = call("GET", "media/$id")

    suspend fun mediaComplete(id: String, parts: List<Pair<Int, String>>): JsonObject =
        call("POST", "media/$id/complete", buildJsonObject {
            put("parts", kotlinx.serialization.json.JsonArray(parts.map { (n, etag) ->
                buildJsonObject { put("part_number", n); put("etag", etag) } }))
        })

    /** PUT one part straight to storage (a signed URL: no sign-in header). Returns the ETag. */
    suspend fun putPart(url: String, bytes: ByteArray, contentType: String): String = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url).put(bytes.toRequestBody(contentType.toMediaType())).build()
        try {
            http.newCall(req).execute().use { r ->
                val etag = r.header("ETag")
                if (!r.isSuccessful || etag == null) throw ApiError("UPLOAD_FAILED", "The file could not be sent (${r.code}).", r.code)
                etag
            }
        } catch (e: IOException) {
            throw ApiError(ApiError.NETWORK, "No connection. Check your signal and try again.", 0)
        }
    }

    /** A form picture (image field), as bytes. */
    suspend fun formAsset(id: String): ByteArray = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(baseUrl + "form-assets/$id")
        tokens.access()?.let { req.header("Authorization", "Bearer $it") }
        try {
            http.newCall(req.build()).execute().use { r ->
                if (!r.isSuccessful) throw ApiError("HTTP_${r.code}", "Picture not available.", r.code)
                r.body!!.bytes()
            }
        } catch (e: IOException) {
            throw ApiError(ApiError.NETWORK, "No connection.", 0)
        }
    }

    /** Any GET (Ops screens): the parsed body, list or object. */
    suspend fun get(path: String): JsonElement = callAny("GET", path)

    /** Any change (Ops actions): POST, PATCH or DELETE with a JSON body. */
    suspend fun act(method: String, path: String, body: JsonObject? = null): JsonElement = callAny(method, path, body)

    /** A file the server signed (photo, report): its bytes, no sign-in header. */
    suspend fun download(url: String, maxBytes: Long = 100L * 1024 * 1024): ByteArray = withContext(Dispatchers.IO) {
        // only signed storage links: https (plain http only against a local server in a debug build)
        val u = url.toHttpUrlOrNull()
        if (u == null || (!u.isHttps && !`in`.carcid.vayu.BuildConfig.DEBUG)) throw ApiError("BAD_LINK", "That download link isn't safe to open.", 0)
        try {
            http.newCall(Request.Builder().url(u).build()).execute().use { r -> capped(r, maxBytes) }
        } catch (e: IOException) {
            throw ApiError(ApiError.NETWORK, "No connection. Check your signal and try again.", 0)
        }
    }

    /**
     * A booking's report PDF through the server, signed in, so the download is logged on the
     * booking; the server redirects to the file (the sign-in header is not sent on to storage).
     */
    suspend fun reportPdf(bookingId: String, maxBytes: Long = 100L * 1024 * 1024): ByteArray = withContext(Dispatchers.IO) {
        // our own address from the booking ID, never a link taken from a reply
        val path = "bookings/" + java.util.UUID.fromString(bookingId) + "/report/download"
        fun get() = http.newCall(Request.Builder().url(baseUrl + path)
            .apply { tokens.access()?.let { header("Authorization", "Bearer $it") } }.build()).execute()
        try {
            val sentWith = tokens.access()
            var r = get()
            if (r.code == 401) { r.close(); if (renewed(sentWith)) r = get() }
            r.use { capped(it, maxBytes) }
        } catch (e: IOException) {
            throw ApiError(ApiError.NETWORK, "No connection. Check your signal and try again.", 0)
        }
    }

    private fun capped(r: okhttp3.Response, maxBytes: Long): ByteArray {
        if (!r.isSuccessful) throw ApiError("HTTP_${r.code}", "Couldn't download it (${r.code}).", r.code)
        val body = r.body!!
        if (body.contentLength() > maxBytes) throw ApiError("TOO_LARGE", "That file is too large to open on the phone.", 0)
        val out = java.io.ByteArrayOutputStream()
        body.byteStream().use { input ->
            val buf = ByteArray(1 shl 16)
            while (true) {
                val n = input.read(buf); if (n < 0) break
                out.write(buf, 0, n)
                if (out.size() > maxBytes) throw ApiError("TOO_LARGE", "That file is too large to open on the phone.", 0)
            }
        }
        return out.toByteArray()
    }

    suspend fun logout() {
        try { call("POST", "auth/logout") } finally { tokens.clear() }
    }

    /**
     * End a sign-in this phone left behind (signed out without signal): renew it with its own refresh
     * token, then sign it out. True when done or the server already ended it; false: try again later.
     */
    suspend fun endOld(refresh: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val r = send("POST", "auth/refresh", buildJsonObject { put("refresh", refresh) }, auth = false)
            val access = (r.body["access"] as? JsonPrimitive)?.contentOrNull
            when {
                r.status == 200 && access != null ->
                    send("POST", "auth/logout", null, auth = false, mapOf("Authorization" to "Bearer $access")).status < 500
                else -> r.status in 400..499              // refused: already ended
            }
        } catch (e: ApiError) { false }
    }

    private fun parseMe(o: JsonObject) = Me(
        id = o.getValue("id").jsonPrimitive.intOrNull ?: 0, username = o.s("username"),
        name = o.s("name"), role = o.s("role"),
        mustChangePassword = o["must_change_password"]?.jsonPrimitive?.booleanOrNull ?: false,
        theme = o["theme"]?.jsonPrimitive?.contentOrNull ?: "light",
        permissions = (o["permissions"] as? JsonObject)?.keys.orEmpty(),
        muted = (o["notify_prefs"] as? JsonObject)?.filterValues { it.jsonPrimitive.booleanOrNull == false }?.keys.orEmpty())


    private suspend fun call(method: String, path: String, body: JsonObject? = null, auth: Boolean = true,
                             headers: Map<String, String> = emptyMap()): JsonObject =
        withContext(Dispatchers.IO) { checked(method, path, body, auth, headers).body }

    private suspend fun callAny(method: String, path: String, body: JsonObject? = null): JsonElement =
        withContext(Dispatchers.IO) { checked(method, path, body, true).raw ?: JsonObject(emptyMap()) }

    /** One call, renewed once on a 401; an error the server explained becomes an [ApiError]. */
    private fun checked(method: String, path: String, body: JsonObject?, auth: Boolean, headers: Map<String, String> = emptyMap()): Res {
        val sentWith = tokens.access()
        var res = send(method, path, body, auth, headers)
        if (res.status == 401 && auth && res.code != "DEVICE_REVOKED") {
            if (renewed(sentWith)) res = send(method, path, body, auth, headers)
            else if (expired.value) throw ApiError(ApiError.SESSION_EXPIRED, "Your sign-in has ended. Sign in again; your unsent work stays on this phone.", 401)
        }
        if (res.code == "DEVICE_REVOKED") tokens.clear()
        if (res.status !in 200..299) throw ApiError(res.code ?: "HTTP_${res.status}",
            res.body["detail"]?.jsonPrimitive?.contentOrNull ?: "Something went wrong (${res.status}).",
            res.status, res.body)
        return res
    }

    private class Res(val status: Int, val body: JsonObject, val raw: JsonElement? = null) {
        val code: String? get() = (body["code"] as? JsonPrimitive)?.contentOrNull
    }

    private fun send(method: String, path: String, body: JsonObject?, auth: Boolean, headers: Map<String, String> = emptyMap()): Res {
        val req = Request.Builder().url(baseUrl + path)
            .method(method, body?.toString()?.toRequestBody(json) ?: if (method == "GET") null else "{}".toRequestBody(json))
        if (auth) tokens.access()?.let { req.header("Authorization", "Bearer $it") }
        headers.forEach { (k, v) -> req.header(k, v) }
        return try {
            http.newCall(req.build()).execute().use { r ->
                val text = r.body?.string().orEmpty()
                val parsed: JsonElement? = text.takeIf { it.isNotBlank() }?.let { runCatching { Json.parseToJsonElement(it) }.getOrNull() }
                Res(r.code, (parsed as? JsonObject) ?: JsonObject(emptyMap()), parsed)
            }
        } catch (e: IOException) {
            throw ApiError(ApiError.NETWORK, "No connection. Check your signal and try again.", 0)
        }
    }

    /**
     * Renew the sign-in after a 401 to a call sent with [sentWith]. One at a time: calls that fail
     * together renew once, and the others use the new token. A refused renewal ends the sign-in
     * ([expired]); a busy or unreachable server does not.
     */
    @Synchronized
    private fun renewed(sentWith: String?): Boolean {
        tokens.access()?.let { if (it != sentWith) return true }      // another call renewed it meanwhile
        val refresh = tokens.refresh() ?: return false
        val res = send("POST", "auth/refresh", buildJsonObject { put("refresh", refresh) }, auth = false)
        val access = (res.body["access"] as? JsonPrimitive)?.contentOrNull
        if (res.status == 200 && access != null) {
            tokens.save(access, (res.body["refresh"] as? JsonPrimitive)?.contentOrNull ?: refresh)
            return true
        }
        if (res.status == 400 || res.status == 401) { tokens.clear(); expired.value = true }
        return false
    }
}
