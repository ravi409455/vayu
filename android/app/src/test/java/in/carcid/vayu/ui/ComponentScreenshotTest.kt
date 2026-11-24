package `in`.carcid.vayu.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Person
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import `in`.carcid.vayu.ui.components.Avatar
import `in`.carcid.vayu.ui.components.Banner
import `in`.carcid.vayu.ui.components.ChipRow
import `in`.carcid.vayu.ui.components.ChoiceRow
import `in`.carcid.vayu.ui.components.ExpertBottomBar
import `in`.carcid.vayu.ui.components.ExpertTab
import `in`.carcid.vayu.ui.components.ListRow
import `in`.carcid.vayu.ui.components.OfflineStrip
import `in`.carcid.vayu.ui.components.OpsBottomBar
import `in`.carcid.vayu.ui.components.OpsTab
import `in`.carcid.vayu.ui.components.Page
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SectionLabel
import `in`.carcid.vayu.ui.components.Segmented
import `in`.carcid.vayu.ui.components.SoftField
import `in`.carcid.vayu.ui.components.StackedOption
import `in`.carcid.vayu.ui.components.StatusDot
import `in`.carcid.vayu.ui.components.ToggleChip
import `in`.carcid.vayu.ui.components.Tone
import `in`.carcid.vayu.ui.components.VayuTopBar
import `in`.carcid.vayu.ui.theme.ThemeMode
import `in`.carcid.vayu.ui.theme.VayuTheme
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Every design-system piece, light and dark. Images live in src/test/screenshots; CI verifies them. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w390dp-h1400dp-xxhdpi", sdk = [34])
class ComponentScreenshotTest {
    // Linux CI and a Mac can anti-alias text a little differently; real changes are far bigger
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))


    @Composable
    private fun Gallery() {
        Column {
            VayuTopBar("Today", "PO", bellCount = 3, onBell = {}, onProfile = {})
            Page {
                SectionLabel("Unassigned · 3")
                ListRow("Rohit Sharma", subtitle = "DEMO-4 · Delhi", trailing = { StatusDot("Assigned", Tone.NEUTRAL) })
                ListRow("Farhan Ali", subtitle = "DEMO-8 · Ravi", leading = { Avatar("RA") },
                    trailing = { StatusDot("In progress", Tone.INFO) })
                SectionLabel("Controls")
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Segmented(listOf("Today", "Upcoming", "All"), 0, {})
                    ChoiceRow(listOf("OK" to false, "Minor" to true, "Major" to true, "Critical" to true), "Minor") {}
                    StackedOption("Repainted, colour does not match the rest of the car", false, "Major") {}
                    StackedOption("Original paint", true, null) {}
                    ChipRow { ToggleChip("Front bumper", true) {}; ToggleChip("Roof", false) {} }
                    SoftField("ravi", {}, "Username", icon = Icons.Outlined.Person)
                    Banner("Ops moved DEMO-7 · 2 Dec → 4 Dec", Tone.INFO, {})
                    Banner("1.6 GB free. Clear sent photos.", Tone.WARN, {})
                    OfflineStrip("Offline · as of 10:42")
                    PrimaryButton("Next · Interior", {})
                }
            }
            OpsBottomBar(OpsTab.TODAY, {}, {})
            ExpertBottomBar(ExpertTab.UPLOADS, uploads = 3, {}, {})
        }
    }

    @Test fun light() = captureRoboImage("src/test/screenshots/components_light.png", roborazziOptions = options) {
        VayuTheme(ThemeMode.LIGHT) { Gallery() }
    }

    @Test fun dark() = captureRoboImage("src/test/screenshots/components_dark.png", roborazziOptions = options) {
        VayuTheme(ThemeMode.DARK) { Gallery() }
    }
}
