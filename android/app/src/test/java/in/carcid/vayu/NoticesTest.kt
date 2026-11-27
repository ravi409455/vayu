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
        Notices.show(app, "push-1", "Inspection started · DEMO-8", "Test Expert · Farhan Ali\nMG Road", "b1")
        val n = shadowOf(app.getSystemService(NotificationManager::class.java)).allNotifications.single()
        assertEquals(Notification.VISIBILITY_PRIVATE, n.visibility)
        val public = n.publicVersion!!.extras
        val shown = "${public.getCharSequence(Notification.EXTRA_TITLE)} ${public.getCharSequence(Notification.EXTRA_TEXT)}"
        assertFalse(shown, shown.contains("Farhan") || shown.contains("MG Road") || shown.contains("DEMO-8"))
        assertEquals("Inspection started", public.getCharSequence(Notification.EXTRA_TITLE))
    }

    /** The lock screen keeps what and when; only the booking ID goes. */
    @Test fun theLockScreenKeepsWhatAndWhen() {
        assertEquals("New lead · Wed 14 Oct, 3:30 pm", Notices.lockTitle("New lead · Wed 14 Oct, 3:30 pm"))
        assertEquals("In 1 hour · 11:00 am", Notices.lockTitle("In 1 hour · 11:00 am"))
        assertEquals("Report didn't build", Notices.lockTitle("Report didn't build · TST-1013"))
        assertEquals("Vayu", Notices.lockTitle("Vayu"))
        assertEquals("In 1 hour · 11:00\u00a0am", Notices.lockTitle("In 1 hour · 11:00\u00a0am"))
    }

    /** CarCID red with a car; a lead gets Directions, Call and Open; a problem is red with "Open booking". */
    @Test fun aLeadHasBrandAndButtonsAProblemIsRed() {
        shadowOf(app).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
        val lead = `in`.carcid.vayu.core.sync.Job("b1", "DEMO-8", "assigned", "Farhan Ali", "+91 98765 00111", "12 MG Road", "Pune",
            "Swift VXi", "PDI", "2026-11-24", "11:00", assignedToMe = true, myDraft = null, versions = emptyMap())
        Notices.show(app, "push-2", "New lead · Tue 24 Nov, 11:00 am", "PDI · Swift VXi · DEMO-8\nFarhan Ali · 12 MG Road", "b1", lead = lead)
        Notices.show(app, "push-3", "Report didn't build · DEMO-8", "Farhan Ali · PDI", "b1", problem = true)
        val all = shadowOf(app.getSystemService(NotificationManager::class.java)).allNotifications
        val n = all.first { it.extras.getCharSequence(Notification.EXTRA_TITLE)!!.startsWith("New lead") }
        assertEquals(app.getColor(R.color.brand), n.color)
        assertEquals(listOf("Directions", "Call", "Open"), n.actions.map { it.title.toString() })
        assertEquals("PDI · Swift VXi · DEMO-8", n.extras.getCharSequence(Notification.EXTRA_TEXT).toString())
        val p = all.first { it.extras.getCharSequence(Notification.EXTRA_TITLE)!!.startsWith("Report") }
        assertEquals(app.getColor(R.color.notice_problem), p.color)
        assertEquals(listOf("Open booking"), p.actions.map { it.title.toString() })
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
            .putExtra("title", "In 1 hour · 11:00 am").putExtra("body", "x")
        ReminderReceiver().onReceive(app, intent)                 // nobody signed in as 999
        assertEquals(0, shadowOf(app.getSystemService(NotificationManager::class.java)).allNotifications.size)
    }
}
