package `in`.carcid.vayu.core.forms

import `in`.carcid.vayu.ui.expert.ChoiceLayout
import `in`.carcid.vayu.ui.expert.choiceLayout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FormTreeTest {
    private fun tree(json: String) = FormTree.parse(Json.parseToJsonElement(json).jsonObject)
    private val trees = mapOf("start" to tree(Fixtures.START), "inspection" to tree(Fixtures.INSPECTION), "end" to tree(Fixtures.END))
    private fun filled(answers: Map<String, Map<String, Any?>> = emptyMap()) = Filled(trees, answers, emptyMap(), "2026-11-24")

    @Test fun theTreeIsReadWithOptionsAndConfig() {
        val t = trees["inspection"]!!
        assertEquals(listOf("Vehicle", "Exterior"), t.pages.map { it.title })
        assertTrue(t.pages[0].gate)
        assertEquals(4, t.field("door_photos")!!.maxCount)
        assertEquals("Major", t.field("bonnet")!!.options[2].label)
        assertEquals(true, t.field("chassis_no")!!.config["scan"])
        assertFalse(t.field("seal")!!.answerable)
    }

    @Test fun requiredQuestionsAreMissingUntilAnswered() {
        val f = filled()
        assertEquals(listOf("travel"), f.gaps("start").map { it.key })
        assertEquals(listOf("chassis_no", "odometer", "bonnet", "door"), f.gaps("inspection").map { it.key })
        assertEquals(listOf("taking_payment"), f.gaps("end").map { it.key })
        assertEquals(6, f.allGaps().size)
    }

    @Test fun aWrongAnswerCountsAsStillToDo() {
        val f = filled(mapOf("inspection" to mapOf("chassis_no" to "MA3", "odometer" to 12.5, "bonnet" to "ok", "door" to "ok")))
        assertEquals(listOf("odometer"), f.gaps("inspection").map { it.key })
    }

    @Test fun aBrokenAnswerRuleShowsTheAdminsMessageAndBlocksSubmit() {
        val withCheck = tree(Fixtures.INSPECTION.replaceFirst("""{"id":7,"checks":[]""",
            """{"id":7,"checks":[{"rule":{"<":[{"var":"inspection.odometer"},500000]},"message":"Odometer looks too high.","fields":["odometer"]}]"""))
        fun f(odo: Any) = Filled(trees + ("inspection" to withCheck),
            mapOf("inspection" to mapOf("chassis_no" to "MA3", "odometer" to odo, "bonnet" to "ok", "door" to "ok")), emptyMap(), "2026-11-24")
        assertEquals("Odometer looks too high.", f(900000.0).checkMessage("inspection", "odometer"))
        assertEquals(listOf("odometer"), f(900000.0).gaps("inspection").map { it.key })
        assertEquals(null, f("12000").checkMessage("inspection", "odometer"))
        assertTrue(f("12000").gaps("inspection").isEmpty())
    }

    @Test fun aFollowUpAppearsOnlyAfterADefect() {
        assertFalse(filled().visible("inspection", "door_photos"))
        val f = filled(mapOf("inspection" to mapOf("door" to "minor")))
        assertTrue(f.visible("inspection", "door_photos"))
        assertTrue(f.gaps("inspection").any { it.key == "door_photos" })
        val paid = filled(mapOf("end" to mapOf("taking_payment" to true)))
        assertEquals(listOf("payment_amount"), paid.gaps("end").map { it.key })
    }

    @Test fun onlyVisibleAnswerableAnswersAreSent() {
        val f = filled(mapOf("inspection" to mapOf("door" to "ok", "door_photos" to listOf("x"), "seal" to true, "bonnet" to "")))
        assertEquals(mapOf("door" to "ok"), f.submittable("inspection"))   // hidden, computed and empty ones left out
    }

    @Test fun pagesWithNothingVisibleAreSkipped() {
        assertEquals(listOf("Vehicle", "Exterior"), filled().visiblePages("inspection").map { it.title })
    }

    @Test fun theChoiceLayoutRule() {
        assertEquals(ChoiceLayout.ROW, choiceLayout(listOf("OK", "Minor", "Major", "Critical")))
        assertEquals(ChoiceLayout.STACK, choiceLayout(listOf("OK", "Minor", "Major", "Critical", "N/A")))
        assertEquals(ChoiceLayout.STACK, choiceLayout(listOf("Original paint", "Repainted")))          // long labels
        assertEquals(ChoiceLayout.LIST, choiceLayout((1..9).map { "Brand $it" }))
    }
}
