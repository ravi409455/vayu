package `in`.carcid.vayu.ui.ops

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.dp
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import `in`.carcid.vayu.ui.theme.ThemeMode
import `in`.carcid.vayu.ui.components.OpsBottomBar
import `in`.carcid.vayu.ui.components.OpsTab
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.theme.VayuTheme
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.time.LocalDate

/**
 * Real-world long text on a small phone with large text (360dp, 130%), the case that broke lists:
 * the quick filters stay on one line, the booking ID is never cut, names end in "…".
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w360dp-h780dp-xxhdpi", sdk = [34], fontScale = 1.3f)
class LongTextTest {
    @get:Rule val compose = createComposeRule()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))

    private fun bk(code: String, name: String, stage: String) = Bk(Json.parseToJsonElement("""{"id":"$code","booking_id":"$code","stage":"$stage",
        "inspection_type":"ev_pdi","answers":{"customer_name":"$name","inspection_date":"2026-11-24","inspection_time":"11:00"}}""").jsonObject)

    private fun lines(text: String): Int {
        val out = mutableListOf<TextLayoutResult>()
        compose.onNodeWithText(text).fetchSemanticsNode().config[SemanticsActions.GetTextLayoutResult].action?.invoke(out)
        return out.single().lineCount
    }

    @Test fun longTextFits() {
        val today = LocalDate.of(2026, 11, 24)
        compose.setContent {
            VayuTheme(ThemeMode.LIGHT) { Column(Modifier.background(androidx.compose.ui.graphics.Color.White)) {
                Column(Modifier.padding(horizontal = 20.dp)) {
                    SoftField("", {}, "Name, phone, ID, chassis")
                    QuickFilters(mapOf("stage" to "in_progress", "expert" to "3"), Labels(), {}, {})
                    BookingRow(bk("CARCID-2026-001234", "Venkata Subramanian Lakshminarayanan Iyer", "draft"), "Pre-Delivery Inspection (Electric) · Thiruvananthapuram", today, {}) {
                        PillButton("Assign", true) {}
                    }
                    BookingRow(bk("CARCID-2026-001236", "Anantha Padmanabhan Krishnamurthy", "submitted"), "Used Car · Mohammed Abdul Rahman Siddiqui", today, {})
                }
                OpsBottomBar(OpsTab.BOOKINGS, {}, {}, refreshing = true)
            } }
        }
        // the quick row stays on one line: Status, Experts and Filter share one top edge
        val tops = listOf("Status: In progress", "Experts: 1 chosen", "All filters, 2 on").map {
            compose.onNodeWithContentDescription(it).fetchSemanticsNode().boundsInRoot.top }
        assertEquals(1, tops.distinct().size)
        assertEquals(1, lines("In progress"))
        assertEquals(1, lines("CARCID-2026-001234"))
        assertEquals(1, lines("Venkata Subramanian Lakshminarayanan Iyer"))
        assertEquals(1, lines("Updating…"))
        assertFalse(compose.onNodeWithText("CARCID-2026-001236").fetchSemanticsNode().let { n ->
            val out = mutableListOf<TextLayoutResult>(); n.config[SemanticsActions.GetTextLayoutResult].action?.invoke(out); out.single().hasVisualOverflow
        })
        compose.onNode(isRoot()).captureRoboImage("src/test/screenshots/long_text_small_phone.png", roborazziOptions = options)
    }
}
