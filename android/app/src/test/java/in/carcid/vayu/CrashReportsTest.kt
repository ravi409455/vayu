package `in`.carcid.vayu

import io.sentry.SentryEvent
import io.sentry.android.core.SentryAndroidOptions
import io.sentry.protocol.Message
import io.sentry.protocol.SentryException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

/** Crash reports never carry customer text, whatever the Sentry version's defaults. */
class CrashReportsTest {
    @Test fun everyPrivacyOptionIsSetExplicitly() {
        val o = SentryAndroidOptions().apply { isAttachScreenshot = true; isAttachViewHierarchy = true; logs.isEnabled = true; isSendDefaultPii = true }
        privateCrashReports(o)
        assertFalse(o.isSendDefaultPii); assertFalse(o.isAttachScreenshot); assertFalse(o.isAttachViewHierarchy); assertFalse(o.logs.isEnabled)
        assertEquals(0, o.maxBreadcrumbs); assertNull(o.tracesSampleRate)
        assertNull(o.beforeBreadcrumb!!.execute(io.sentry.Breadcrumb("Opened DEMO-8 for Farhan Ali"), io.sentry.Hint()))
    }

    @Test fun anErrorNamingABookingIsSentWithoutItsText() {
        val o = SentryAndroidOptions(); privateCrashReports(o)
        val e = SentryEvent().apply {
            message = Message().apply { this.message = "Couldn't save DEMO-8 for Farhan Ali" }
            exceptions = listOf(SentryException().apply { type = "IllegalStateException"; value = "DEMO-8 Farhan Ali" })
            setExtra("customer", "Farhan Ali")
        }
        val sent = o.beforeSend!!.execute(e, io.sentry.Hint())!!
        assertNull(sent.message); assertNull(sent.exceptions!!.single().value); assertEquals("IllegalStateException", sent.exceptions!!.single().type)
        assertNull(sent.getExtra("customer"))
    }
}
