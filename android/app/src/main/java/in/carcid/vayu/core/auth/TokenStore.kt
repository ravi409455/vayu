package `in`.carcid.vayu.core.auth

import android.content.Context

/** Where the sign-in tokens live. The app stays signed in (offline work needs it). */
interface TokenStore {
    fun access(): String?
    fun refresh(): String?
    fun save(access: String, refresh: String)
    fun clear()
    /** The signed-in person, kept so the app opens without signal. */
    fun me(): Map<String, String>? = null
    fun saveMe(fields: Map<String, String>) {}
}

/** App-private storage (other apps can't read it). */
class PrefsTokenStore(context: Context) : TokenStore {
    private val prefs = context.getSharedPreferences("vayu.auth", Context.MODE_PRIVATE)
    override fun access() = prefs.getString("access", null)
    override fun refresh() = prefs.getString("refresh", null)
    override fun save(access: String, refresh: String) {
        prefs.edit().putString("access", access).putString("refresh", refresh).apply()
    }
    override fun clear() { prefs.edit().clear().apply() }
    override fun me(): Map<String, String>? = prefs.getString("me.username", null)?.let {
        listOf("id", "username", "name", "role", "theme", "must_change").associateWith { k -> prefs.getString("me.$k", "")!! }
    }
    override fun saveMe(fields: Map<String, String>) {
        prefs.edit().apply { fields.forEach { (k, v) -> putString("me.$k", v) } }.apply()
    }
}

class MemoryTokenStore : TokenStore {
    private var m: Map<String, String>? = null
    override fun me() = m
    override fun saveMe(fields: Map<String, String>) { m = fields }
    private var a: String? = null
    private var r: String? = null
    override fun access() = a
    override fun refresh() = r
    override fun save(access: String, refresh: String) { a = access; r = refresh }
    override fun clear() { a = null; r = null; m = null }
}
