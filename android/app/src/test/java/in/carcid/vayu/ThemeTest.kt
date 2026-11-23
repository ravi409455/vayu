package `in`.carcid.vayu

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import `in`.carcid.vayu.ui.theme.DarkColors
import `in`.carcid.vayu.ui.theme.LightColors
import `in`.carcid.vayu.ui.theme.VayuColors
import org.junit.Assert.assertTrue
import org.junit.Test

class ThemeTest {
    private fun contrast(a: Color, b: Color): Double {
        val (hi, lo) = listOf(a.luminance(), b.luminance()).sortedDescending()
        return (hi + 0.05) / (lo + 0.05)
    }

    private fun check(c: VayuColors, name: String) {
        // text pairs used on every screen must be readable (WCAG AA 4.5:1)
        listOf("ink on bg" to (c.ink to c.bg), "muted on bg" to (c.muted to c.bg),
            "ink on soft" to (c.ink to c.soft), "button text" to (c.onPrimary to c.primary), "chosen defect" to (c.onWarn to c.warn),
            "bad on bg" to (c.bad to c.bg), "info on bg" to (c.info to c.bg))
            .forEach { (pair, colors) ->
                val ratio = contrast(colors.first, colors.second)
                assertTrue("$name: $pair contrast $ratio", ratio >= 4.5)
            }
    }

    @Test fun lightThemeIsReadable() = check(LightColors, "light")
    @Test fun darkThemeIsReadable() = check(DarkColors, "dark")
}
