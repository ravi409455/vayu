package `in`.carcid.vayu.ui.ops

import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.ui.expert.whenStamp
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId

/** The words Ops screens show for server values (found testing on a phone). */
class OpsTextTest {
    @Test fun minutesReadLikeTheWeb() {
        assertEquals("40 min", fmtMinutes(40)); assertEquals("2 h 5 min", fmtMinutes(125)); assertEquals("2 h", fmtMinutes(120))
        assertEquals("4 days 22 h", fmtMinutes(7125)); assertEquals("1 day", fmtMinutes(1440)); assertEquals("—", fmtMinutes(null))
    }

    @Test fun timingFlagsAreTwoSeparateProblems() {
        val b = Bk(Json.parseToJsonElement("""{"timing":{"late_minutes":40,"duration_minutes":25,"late":true,"quick":true,"min_minutes":45,
            "grace_minutes":15,"late_reviewed_by":"ops","late_reviewed_at":"2026-11-24T10:44:00+05:30","quick_reviewed_by":null,"quick_reviewed_at":null}}""").jsonObject)
        assertEquals(listOf("Started 40 min late", "Took 25 min (min 45)"), b.flags.map { it.words })
        assertEquals(listOf("ops", ""), b.flags.map { it.reviewedBy })
        assertEquals(emptyList<TimingFlag>(), Bk(Json.parseToJsonElement("{}").jsonObject).flags)   // Experts never get "timing"
    }

    @Test fun dashboardRowsAreRead() {
        // the dashboard answers {"rows": [...]}, lists answer {"results": [...]}
        assertEquals(2, Json.parseToJsonElement("""{"rows":[{"a":1},{"a":2}]}""").rows().size)
        assertEquals(1, Json.parseToJsonElement("""{"count":1,"results":[{"a":1}]}""").rows().size)
    }

    @Test fun serverTimesReadInWordsOnThePhoneClock() {
        val today = LocalDate.of(2026, 11, 24)
        val at = OffsetDateTime.of(2026, 11, 24, 14, 14, 0, 0, ZoneId.systemDefault().rules.getOffset(java.time.Instant.now()))
        assertEquals("Today, 2:14\u00A0pm", whenStamp(at.toString(), today))
        assertEquals("Yesterday, 2:14\u00A0pm", whenStamp(at.minusDays(1).toString(), today))
        assertEquals("not a time", whenStamp("not a time", today))
    }

    @Test fun yearsHaveNoCommaButBigNumbersDo() {
        assertEquals("2022", shown(2022.0))
        assertEquals("47,000", shown(47000.0))
    }

    @Test fun aRejectedTypeChangeUsesTypeNames() {
        val l = Labels(types = listOf(Triple("pdi", "PDI", true), Triple("used_car", "Used car", true)))
        assertEquals("The expert had already started a PDI inspection, so your change to Used car wasn't applied.",
            l.typeRejected("Type change to used_car rejected: expert started pdi"))
        assertEquals("something else", l.typeRejected("something else"))
    }

    @Test fun dashboardPeriodsAndTypesReadAsWords() {
        assertEquals("9 Nov", periodLabel("2026-W46"))
        assertEquals("Nov 2026", periodLabel("2026-11"))
        assertEquals("24 Nov", periodLabel("2026-11-24"))
        assertEquals("EV", Labels().type("ev"))
        assertEquals("Used car", Labels().type("used_car"))
    }

    @Test fun aDefectAnswerIsAProblem() {
        val f = `in`.carcid.vayu.core.forms.FormTree.parse(Json.parseToJsonElement("""{"id":1,"pages":[{"id":1,"title":"P","sections":[{"id":1,"title":"S",
            "fields":[{"id":1,"key":"door","label":"Door","type":"single_choice","config":{"options":[{"key":"ok","label":"OK"},
            {"key":"dent","label":"Dent","is_defect":true,"severity":"minor"}]}}]}]}]}""").jsonObject).fields.single()
        assertEquals("Minor", problemOf(f, "dent"))
        assertEquals(null, problemOf(f, "ok"))
    }
}
