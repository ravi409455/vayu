package `in`.carcid.vayu.core.auth

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** R-19: tokens are sealed with a phone key; an update moves the old plain ones over, so nobody is signed out. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class TokenStoreTest {
    private val app = ApplicationProvider.getApplicationContext<Context>()
    private val prefs = app.getSharedPreferences("vayu.auth", Context.MODE_PRIVATE)

    /** Stands in for the Android Keystore (not in Robolectric): reversible, and visibly not the plain text. */
    private class Fake(var broken: Boolean = false) : Sealer {
        override fun seal(plain: String): String { if (broken) error("no key"); return "sealed:" + plain.reversed() }
        override fun open(sealed: String): String { if (broken) error("no key"); return sealed.removePrefix("sealed:").reversed() }
    }

    @Test fun anUpdateMovesTheOldTokensIntoTheSealedStoreAndStaysSignedIn() {
        prefs.edit().putString("access", "A1").putString("refresh", "R1").putString("me.username", "ravi").commit()   // the old app's file
        val s = PrefsTokenStore(app, Fake())
        assertEquals("A1", s.access()); assertEquals("R1", s.refresh())
        assertFalse("plain tokens are gone from the file", prefs.contains("access") || prefs.contains("refresh"))
        assertTrue(prefs.getString("refresh.s", "")!!.startsWith("sealed:"))
        assertEquals("ravi", s.me()!!["username"])
        assertEquals("R1", PrefsTokenStore(app, Fake()).refresh())                 // and after the next start
    }

    /** plan-media-backup: one id per install, kept through sign-outs, so the server lets this phone back in. */
    @Test fun theInstallIdIsMadeOnceAndKeptThroughSignOut() {
        val s = PrefsTokenStore(app, Fake())
        val id = s.installId()
        java.util.UUID.fromString(id)                                            // a real UUID: the server checks it
        s.save("A", "R"); s.clear()
        assertEquals(id, s.installId())
        assertEquals(id, PrefsTokenStore(app, Fake()).installId())                 // and after the next start
    }

    @Test fun newTokensAreSavedSealed() {
        PrefsTokenStore(app, Fake()).save("A2", "R2")
        assertNull(prefs.getString("access", null))
        assertEquals("R2", PrefsTokenStore(app, Fake()).refresh())
    }

    @Test fun aPhoneWhoseKeyFailsKeepsWorkingSignedIn() {
        prefs.edit().putString("access", "A1").putString("refresh", "R1").commit()
        var told = 0
        val s = PrefsTokenStore(app, Fake(broken = true), onPlain = { told++ })
        assertEquals("R1", s.refresh())                                            // never signed out by the move
        s.save("A3", "R3"); s.save("A4", "R4")
        assertEquals("R4", PrefsTokenStore(app, Fake(broken = true)).refresh())
        assertEquals(1, told)                                                      // the plain fallback is reported, once (N-9)
    }

    @Test fun clearForgetsBoth() {
        val s = PrefsTokenStore(app, Fake()); s.save("A", "R"); s.clear()
        assertNull(s.access()); assertNull(PrefsTokenStore(app, Fake()).refresh())
    }
}
