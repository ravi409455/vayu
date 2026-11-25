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

    /**
     * F-191 / F-199: the shared colours are the web's (web/src/styles.css is the source). Left out on
     * purpose: bg and soft, the phone's own surfaces (a full-screen page, not the web's page-and-panel).
     */
    private fun web(theme: String): Map<String, String> {
        val css = java.io.File("../../web/src/styles.css").readText()
        val start = if (theme == "dark") css.indexOf(":root[data-theme=\"dark\"] {") else css.indexOf(":root {")
        val block = css.substring(start, css.indexOf('}', start))
        return Regex("--([a-z0-9-]+):\\s*(#[0-9a-fA-F]{3,6})").findAll(block).associate { it.groupValues[1] to it.groupValues[2].lowercase() }
    }
    private fun hex(c: Color) = "#%06x".format(c.value.toLong().ushr(32).toInt() and 0xFFFFFF)
    private fun same(c: VayuColors, theme: String) {
        val w = web(theme)
        fun long(h: String) = if (h.length == 4) "#" + h.drop(1).map { "$it$it" }.joinToString("") else h
        val pairs = mapOf("ink" to c.ink, "ink-2" to c.ink2, "muted" to c.muted, "line" to c.line, "line-strong" to c.line2,
            "brand" to c.brand, "brand-tint" to c.brandTint, "ok" to c.ok, "ok-tint" to c.okTint, "warn" to c.warn, "warn-tint" to c.warnTint,
            "bad" to c.bad, "bad-tint" to c.badTint, "info" to c.info, "info-tint" to c.infoTint, "primary" to c.primary,
            "primary-ink" to c.onPrimary, "raised" to c.raised)
        val wrong = pairs.filter { (k, v) -> w[k]?.let(::long) != hex(v) }.map { (k, v) -> "--$k web ${w[k]} app ${hex(v)}" }
        assertTrue("$theme: ${wrong.joinToString("; ")}", wrong.isEmpty())
    }

    @Test fun lightColoursAreTheWebs() = same(LightColors, "light")
    @Test fun darkColoursAreTheWebs() = same(DarkColors, "dark")
}
