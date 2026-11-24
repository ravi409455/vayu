package `in`.carcid.vayu.core.api

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
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/** An error the server explained ({code, detail, ...}), or NETWORK when there is no connection. */
class ApiError(val code: String, override val message: String, val status: Int,
               val extra: JsonObject = JsonObject(emptyMap())) : Exception(message) {
    companion object { const val NETWORK = "NETWORK" }
}

data class Me(val id: Int, val username: String, val name: String, val role: String,
              val mustChangePassword: Boolean, val theme: String) {
    val initials: String
        get() = (name.ifBlank { username }).split(" ").filter { it.isNotBlank() }.take(2)
            .joinToString("") { it.first().uppercase() }
}

/** The Vayu API, as the app uses it. Tokens are refreshed once on a 401; a revoked phone signs out. */
class Api(private val baseUrl: String, private val tokens: TokenStore,
          private val http: OkHttpClient = OkHttpClient()) {

    private val json = "application/json".toMediaType()

    suspend fun login(username: String, password: String, deviceName: String): Me {
        val body = call("POST", "auth/login", buildJsonObject {
            put("username", username); put("password", password)
            put("client", "mobile"); put("device_name", deviceName)
        }, auth = false)
        tokens.save(body.str("access"), body.str("refresh"))
        return me()
    }

    suspend fun me(): Me = parseMe(call("GET", "auth/me"))

    suspend fun changePassword(old: String, new: String) {
        call("POST", "auth/change-password", buildJsonObject { put("old_password", old); put("new_password", new) })
    }

    suspend fun setTheme(theme: String): Me = parseMe(call("PATCH", "auth/me/profile", buildJsonObject { put("theme", theme) }))

    /** Tells the server what this phone still holds; returns the minimum app version it accepts. */
    suspend fun heartbeat(drafts: Int, files: Int): Int =
        call("POST", "devices/heartbeat", buildJsonObject { put("drafts", drafts); put("files", files) })
            .getValue("min_app_version").jsonPrimitive.intOrNull ?: 0

    /** Everything an expert needs offline (B2). [have]: form versions already on the phone; [since]: last server_time. */
    suspend fun syncJobs(have: Set<Int>, since: String?): JsonObject {
        val q = buildList {
            if (have.isNotEmpty()) add("have=" + have.sorted().joinToString(","))
            if (since != null) add("since=" + java.net.URLEncoder.encode(since, "UTF-8"))
        }
        return call("GET", "sync/jobs" + if (q.isEmpty()) "" else "?" + q.joinToString("&"))
    }

    suspend fun logout() {
        try { call("POST", "auth/logout") } finally { tokens.clear() }
    }

    private fun parseMe(o: JsonObject) = Me(
        id = o.getValue("id").jsonPrimitive.intOrNull ?: 0, username = o.str("username"),
        name = o.str("name"), role = o.str("role"),
        mustChangePassword = o["must_change_password"]?.jsonPrimitive?.booleanOrNull ?: false,
        theme = o["theme"]?.jsonPrimitive?.contentOrNull ?: "light")

    private fun JsonObject.str(k: String) = this[k]?.jsonPrimitive?.contentOrNull ?: ""

    private suspend fun call(method: String, path: String, body: JsonObject? = null, auth: Boolean = true): JsonObject =
        withContext(Dispatchers.IO) {
            var res = send(method, path, body, auth)
            if (res.status == 401 && auth && res.code != "DEVICE_REVOKED" && refresh()) res = send(method, path, body, auth)
            if (res.code == "DEVICE_REVOKED") tokens.clear()
            if (res.status !in 200..299) throw ApiError(res.code ?: "HTTP_${res.status}",
                res.body["detail"]?.jsonPrimitive?.contentOrNull ?: "Something went wrong (${res.status}).",
                res.status, res.body)
            res.body
        }

    private class Res(val status: Int, val body: JsonObject) {
        val code: String? get() = (body["code"] as? JsonPrimitive)?.contentOrNull
    }

    private fun send(method: String, path: String, body: JsonObject?, auth: Boolean): Res {
        val req = Request.Builder().url(baseUrl + path)
            .method(method, body?.toString()?.toRequestBody(json) ?: if (method == "GET") null else "{}".toRequestBody(json))
        if (auth) tokens.access()?.let { req.header("Authorization", "Bearer $it") }
        return try {
            http.newCall(req.build()).execute().use { r ->
                val text = r.body?.string().orEmpty()
                val parsed: JsonElement? = text.takeIf { it.isNotBlank() }?.let { runCatching { Json.parseToJsonElement(it) }.getOrNull() }
                Res(r.code, (parsed as? JsonObject) ?: JsonObject(emptyMap()))
            }
        } catch (e: IOException) {
            throw ApiError(ApiError.NETWORK, "No connection. Check your signal and try again.", 0)
        }
    }

    private fun refresh(): Boolean {
        val refresh = tokens.refresh() ?: return false
        val res = send("POST", "auth/refresh", buildJsonObject { put("refresh", refresh) }, auth = false)
        if (res.status != 200) return false
        tokens.save(res.body.getValue("access").jsonPrimitive.content,
            (res.body["refresh"] as? JsonPrimitive)?.contentOrNull ?: refresh)
        return true
    }
}
