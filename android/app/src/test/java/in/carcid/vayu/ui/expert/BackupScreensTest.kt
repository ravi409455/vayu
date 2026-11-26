package `in`.carcid.vayu.ui.expert

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import `in`.carcid.vayu.core.backup.BackupCopies
import `in`.carcid.vayu.ui.theme.ThemeMode
import `in`.carcid.vayu.ui.theme.Vayu
import `in`.carcid.vayu.ui.theme.VayuTheme
import androidx.compose.ui.test.performClick
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** The approved backup screens (prototype page "Proposed: backup and sign-out"), light and dark. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w390dp-h844dp-xxhdpi", sdk = [34])
class BackupScreensTest {
    @get:org.junit.Rule val compose = androidx.compose.ui.test.junit4.createComposeRule()
    private val options = RoborazziOptions(compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.01F))
    private val found = BackupCopies.Found(listOf("TST-1009", "TST-1014"), 23,
        java.time.LocalDate.of(2026, 11, 28).atTime(12, 0).atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli())

    @Test fun fileAccessScreen() = captureRoboImage("src/test/screenshots/backup_access.png", roborazziOptions = options) {
        VayuTheme(ThemeMode.LIGHT) { BackupAccessScreen() }
    }

    @Test fun warningsAndFoundCopies() = listOf(ThemeMode.LIGHT, ThemeMode.DARK).forEach { mode ->
        captureRoboImage("src/test/screenshots/backup_notices_${mode.name.lowercase()}.png", roborazziOptions = options) {
            VayuTheme(mode) {
                Column(Modifier.fillMaxSize().background(Vayu.colors.bg), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    BackupWarning(phoneFull = false, onFreeSpace = {})
                    BackupWarning(phoneFull = true, onFreeSpace = {})
                    FoundCopiesCard(found, {}, Modifier.padding(horizontal = 20.dp))
                }
            }
        }
    }

    /** "Sent to Ops, delete now" asks first; only Delete deletes. */
    @Test fun deletingFoundCopiesAsksFirst() {
        var deleted = 0
        compose.setContent { VayuTheme(ThemeMode.LIGHT) { FoundCopiesCard(found, { deleted++ }) } }
        compose.onNode(androidx.compose.ui.test.hasText("Sent to Ops, delete now")).performClick()
        compose.onNode(androidx.compose.ui.test.hasText("Delete the copies?")).assertExists()
        compose.onNode(androidx.compose.ui.test.hasText("Cancel")).performClick()
        org.junit.Assert.assertEquals(0, deleted)
        compose.onNode(androidx.compose.ui.test.hasText("Sent to Ops, delete now")).performClick()
        compose.onNode(androidx.compose.ui.test.hasText("Delete")).performClick()
        org.junit.Assert.assertEquals(1, deleted)
    }
}
