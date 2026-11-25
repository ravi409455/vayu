package `in`.carcid.vayu

import android.Manifest
import android.app.Notification
import android.app.NotificationManager
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class NoticesTest {
    private val app = ApplicationProvider.getApplicationContext<android.app.Application>()

    /** F-075: the lock screen shows that a notice came, never the customer's name or address. */
    @Test fun aNoticeIsPrivateOnTheLockScreen() {
        shadowOf(app).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
        Notices.show(app, "remind-1", "In 1 hour: DEMO-8 at 11:00", "Farhan Ali · MG Road", "b1")
        val n = shadowOf(app.getSystemService(NotificationManager::class.java)).allNotifications.single()
        assertEquals(Notification.VISIBILITY_PRIVATE, n.visibility)
        val public = n.publicVersion!!.extras
        val shown = "${public.getCharSequence(Notification.EXTRA_TITLE)} ${public.getCharSequence(Notification.EXTRA_TEXT)}"
        assertFalse(shown, shown.contains("Farhan") || shown.contains("MG Road") || shown.contains("DEMO-8"))
    }

    /** F-077: after sign-out no reminder rows (customer and address) or stuck-photo marks stay behind. */
    @Test fun signingOutLeavesNoRemindersOrStuckMarks() {
        androidx.work.testing.WorkManagerTestInitHelper.initializeTestWorkManager(app)
        val wm = androidx.work.WorkManager.getInstance(app)
        wm.enqueue(androidx.work.OneTimeWorkRequestBuilder<ReminderWorker>().addTag("remind")
            .setInitialDelay(1, java.util.concurrent.TimeUnit.HOURS).build()).result.get()
        app.getSharedPreferences("vayu.stuck", android.content.Context.MODE_PRIVATE).edit().putStringSet("told", setOf("b1")).commit()
        forgetLeftovers(app)
        assertEquals(0, wm.getWorkInfosByTag("remind").get().size)
        assertEquals(null, app.getSharedPreferences("vayu.stuck", android.content.Context.MODE_PRIVATE).getStringSet("told", null))
    }
}
