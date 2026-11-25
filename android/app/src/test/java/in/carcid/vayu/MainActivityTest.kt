package `in`.carcid.vayu

import android.content.Intent
import androidx.lifecycle.ViewModelProvider
import `in`.carcid.vayu.ui.AppViewModel
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MainActivityTest {
    /** F-145: Android re-created the activity (the app was closed in the background), then the tapped notice arrives before the first frame. */
    @Test fun aNoticeTappedWhileTheScreenIsBeingRebuiltStillOpensItsBooking() {
        val c = Robolectric.buildActivity(MainActivity::class.java).create()
        c.newIntent(Intent(c.get(), MainActivity::class.java).putExtra(Notices.EXTRA_BOOKING, "b-42"))
        c.start().resume().visible()
        val vm = ViewModelProvider(c.get())[AppViewModel::class.java]
        assertEquals("b-42", vm.opening.value)
    }
}
