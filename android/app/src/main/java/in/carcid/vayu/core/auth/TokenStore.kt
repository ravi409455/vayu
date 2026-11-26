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
    /** The refresh token of a sign-out the server never heard of (no signal then); kept through clear(). */
    fun pendingLogout(): String? = null
    fun setPendingLogout(refresh: String?) {}
}

/** Seals text with a key only this app on this phone can use. */
interface Sealer {
    fun seal(plain: String): String
    fun open(sealed: String): String
}

/**
 * An AES-256-GCM key kept in the Android Keystore (it never leaves it; not in backups, so a copied
 * file is useless on another phone). Sealed text is base64 of the 12-byte IV and the cipher text.
 */
class KeystoreSealer(private val alias: String = "vayu.tokens") : Sealer {
    private fun key(): javax.crypto.SecretKey {
        val ks = java.security.KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(alias, null) as? javax.crypto.SecretKey)?.let { return it }
        return javax.crypto.KeyGenerator.getInstance(android.security.keystore.KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(android.security.keystore.KeyGenParameterSpec.Builder(alias,
                android.security.keystore.KeyProperties.PURPOSE_ENCRYPT or android.security.keystore.KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(android.security.keystore.KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build())
        }.generateKey()
    }
    override fun seal(plain: String): String {
        val c = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding").apply { init(javax.crypto.Cipher.ENCRYPT_MODE, key()) }
        return android.util.Base64.encodeToString(c.iv + c.doFinal(plain.toByteArray()), android.util.Base64.NO_WRAP)
    }
    override fun open(sealed: String): String {
        val b = android.util.Base64.decode(sealed, android.util.Base64.NO_WRAP)
        val c = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding")
            .apply { init(javax.crypto.Cipher.DECRYPT_MODE, key(), javax.crypto.spec.GCMParameterSpec(128, b, 0, 12)) }
        return String(c.doFinal(b, 12, b.size - 12))
    }
}

/**
 * App-private storage (other apps can't read it), tokens sealed with [sealer] (R-19). Tokens an older
 * app saved in plain text are moved over on the first start, so nobody is signed out by the update
 * (an expert offline must stay signed in). If the phone's key fails, tokens stay as they were.
 */
class PrefsTokenStore(context: Context, private val sealer: Sealer = KeystoreSealer(),
                      /** The phone's key failed, so tokens are kept unsealed: told once (a crash report in the app). */
                      private val onPlain: (Throwable) -> Unit = {}) : TokenStore {
    private val prefs = context.getSharedPreferences("vayu.auth", Context.MODE_PRIVATE)
    /** Opened tokens, so a request does not unseal them every time (N-9). */
    private val opened = java.util.concurrent.ConcurrentHashMap<String, String>()
    private var told = false

    init {
        val old = listOf("access", "refresh").mapNotNull { k -> prefs.getString(k, null)?.let { k to it } }
        if (old.isNotEmpty()) runCatching { old.map { (k, v) -> k to sealer.seal(v) } }.onSuccess { sealed ->
            prefs.edit().apply { sealed.forEach { (k, v) -> putString("$k.s", v); remove(k) } }.commit()
        }
    }

    private fun read(k: String): String? = opened[k] ?: (prefs.getString("$k.s", null)?.let { runCatching { sealer.open(it) }.getOrNull() }
        ?: prefs.getString(k, null))?.also { opened[k] = it }

    override fun access() = read("access")
    override fun refresh() = read("refresh")
    override fun save(access: String, refresh: String) {
        val tried = runCatching { sealer.seal(access) to sealer.seal(refresh) }
        tried.exceptionOrNull()?.let { if (!told) { told = true; onPlain(it) } }
        val sealed = tried.getOrNull()
        opened["access"] = access; opened["refresh"] = refresh
        prefs.edit().apply {
            if (sealed != null) putString("access.s", sealed.first).putString("refresh.s", sealed.second).remove("access").remove("refresh")
            else putString("access", access).putString("refresh", refresh).remove("access.s").remove("refresh.s")
        }.apply()
    }
    override fun clear() { opened.clear(); prefs.edit().clear().apply() }
    override fun me(): Map<String, String>? = prefs.getString("me.username", null)?.let {
        listOf("id", "username", "name", "role", "theme", "must_change", "theme_pending", "perms").associateWith { k -> prefs.getString("me.$k", "")!! }
    }
    override fun saveMe(fields: Map<String, String>) {
        prefs.edit().apply { fields.forEach { (k, v) -> putString("me.$k", v) } }.apply()
    }
    private val ended = context.getSharedPreferences("vayu.signout", Context.MODE_PRIVATE)
    override fun pendingLogout() = ended.getString("refresh.s", null)?.let { runCatching { sealer.open(it) }.getOrNull() }
        ?: ended.getString("refresh", null)
    override fun setPendingLogout(refresh: String?) {
        val sealed = refresh?.let { r -> runCatching { sealer.seal(r) }.getOrNull() }
        ended.edit().putString("refresh.s", sealed).putString("refresh", if (sealed == null) refresh else null).apply()
    }
}

class MemoryTokenStore : TokenStore {
    private var m: Map<String, String>? = null
    override fun me() = m
    override fun saveMe(fields: Map<String, String>) { m = m.orEmpty() + fields }
    private var a: String? = null
    private var r: String? = null
    override fun access() = a
    override fun refresh() = r
    override fun save(access: String, refresh: String) { a = access; r = refresh }
    override fun clear() { a = null; r = null; m = null }
    private var ended: String? = null
    override fun pendingLogout() = ended
    override fun setPendingLogout(refresh: String?) { ended = refresh }
}
