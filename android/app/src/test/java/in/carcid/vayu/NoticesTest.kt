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

    /** F-077: after sign-out no reminders (customer and address) or stuck-photo marks stay behind. */
    @Test fun signingOutLeavesNoRemindersOrStuckMarks() {
        androidx.work.testing.WorkManagerTestInitHelper.initializeTestWorkManager(app)
        val am = app.getSystemService(android.app.AlarmManager::class.java)
        am.setAndAllowWhileIdle(android.app.AlarmManager.RTC_WAKEUP, System.currentTimeMillis() + 3_600_000,
            Reminders.pending(app, "b1") { putExtra("body", "Farhan Ali · MG Road") })
        app.getSharedPreferences("vayu.reminders", android.content.Context.MODE_PRIVATE).edit().putStringSet("set", setOf("b1")).commit()
        app.getSharedPreferences("vayu.stuck", android.content.Context.MODE_PRIVATE).edit().putStringSet("told", setOf("b1")).commit()
        forgetLeftovers(app)
        assertEquals(0, shadowOf(am).scheduledAlarms.size)
        assertEquals(null, app.getSharedPreferences("vayu.stuck", android.content.Context.MODE_PRIVATE).getStringSet("told", null))
    }

    /** F-8: a reminder is an alarm allowed in deep sleep, and it shows only for the person it was set for. */
    @Test fun aReminderAlarmShowsOnlyForItsOwner() {
        shadowOf(app).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
        val intent = android.content.Intent(app, ReminderReceiver::class.java).putExtra("job", "b1").putExtra("user", 999)
            .putExtra("title", "In 1 hour: DEMO-8 at 11:00").putExtra("body", "x")
        ReminderReceiver().onReceive(app, intent)                 // nobody signed in as 999
        assertEquals(0, shadowOf(app.getSystemService(NotificationManager::class.java)).allNotifications.size)
    }
}
