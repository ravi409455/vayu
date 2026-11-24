package `in`.carcid.vayu.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/** The web app's colour tokens (web/src/styles.css), so the app and the web look like one product. */
@Immutable
data class VayuColors(
    val bg: Color, val soft: Color, val ink: Color, val ink2: Color, val muted: Color,
    val line: Color, val line2: Color, val brand: Color, val brandTint: Color,
    val ok: Color, val okTint: Color, val warn: Color, val warnTint: Color,
    val bad: Color, val badTint: Color, val info: Color, val infoTint: Color,
    val primary: Color, val onPrimary: Color, val raised: Color, val onWarn: Color,
    /** Illustration fills (approved prototype). */
    val illo: Color, val illo2: Color,
)

val LightColors = VayuColors(
    bg = Color(0xFFFFFFFF), soft = Color(0xFFF2F4F7), ink = Color(0xFF1C2330), ink2 = Color(0xFF344054),
    muted = Color(0xFF5D6679), line = Color(0xFFECEEF2), line2 = Color(0xFFD0D5DD),
    brand = Color(0xFFA62830), brandTint = Color(0xFFFBEAEC),
    ok = Color(0xFF15703F), okTint = Color(0xFFE6F4EC), warn = Color(0xFFB54708), warnTint = Color(0xFFFDF0E1),
    bad = Color(0xFFB3261E), badTint = Color(0xFFFBE9E7), info = Color(0xFF1D5FD1), infoTint = Color(0xFFE7EFFC),
    primary = Color(0xFF1C2330), onPrimary = Color(0xFFFFFFFF), raised = Color(0xFFFFFFFF),
    onWarn = Color(0xFFFFFFFF), illo = Color(0xFFDFE3EA), illo2 = Color(0xFFC9CFDA),
)

val DarkColors = VayuColors(
    bg = Color(0xFF0A0F1A), soft = Color(0xFF161F31), ink = Color(0xFFE6EAF2), ink2 = Color(0xFFC3CAD6),
    muted = Color(0xFF9AA4B5), line = Color(0xFF1F2A40), line2 = Color(0xFF364562),
    brand = Color(0xFFC83A45), brandTint = Color(0xFF3A1B22),
    ok = Color(0xFF4CC283), okTint = Color(0xFF123524), warn = Color(0xFFF0994A), warnTint = Color(0xFF3B2A12),
    bad = Color(0xFFF2776F), badTint = Color(0xFF3D1D1A), info = Color(0xFF7AAAFF), infoTint = Color(0xFF16264A),
    primary = Color(0xFFE6EAF2), onPrimary = Color(0xFF0B1220), raised = Color(0xFF1B2538),
    onWarn = Color(0xFF0B1220), illo = Color(0xFF1B2538), illo2 = Color(0xFF26324A),
)

/** Light, Dark or Match phone: the same choice the person makes on the web profile. */
enum class ThemeMode { LIGHT, DARK, SYSTEM }

val LocalVayuColors = staticCompositionLocalOf { LightColors }

object Vayu {
    val colors: VayuColors @Composable get() = LocalVayuColors.current
}

@Composable
fun VayuTheme(mode: ThemeMode = ThemeMode.SYSTEM, content: @Composable () -> Unit) {
    val dark = when (mode) {
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
        ThemeMode.SYSTEM -> isSystemInDarkTheme()
    }
    val c = if (dark) DarkColors else LightColors
    val scheme = if (dark) {
        darkColorScheme(primary = c.primary, onPrimary = c.onPrimary, background = c.bg, onBackground = c.ink,
            surface = c.bg, onSurface = c.ink, surfaceVariant = c.soft, onSurfaceVariant = c.muted,
            outline = c.line2, outlineVariant = c.line, error = c.bad,
            // dialogs, menus and pickers use these; left out they fall back to Material's lavender
            surfaceTint = c.bg, surfaceContainerLowest = c.bg, surfaceContainerLow = c.bg, surfaceContainer = c.bg,
            surfaceContainerHigh = c.bg, surfaceContainerHighest = c.soft, secondaryContainer = c.soft,
            onSecondaryContainer = c.ink, primaryContainer = c.soft, onPrimaryContainer = c.ink,
            tertiaryContainer = c.soft, onTertiaryContainer = c.ink)
    } else {
        lightColorScheme(primary = c.primary, onPrimary = c.onPrimary, background = c.bg, onBackground = c.ink,
            surface = c.bg, onSurface = c.ink, surfaceVariant = c.soft, onSurfaceVariant = c.muted,
            outline = c.line2, outlineVariant = c.line, error = c.bad,
            // dialogs, menus and pickers use these; left out they fall back to Material's lavender
            surfaceTint = c.bg, surfaceContainerLowest = c.bg, surfaceContainerLow = c.bg, surfaceContainer = c.bg,
            surfaceContainerHigh = c.bg, surfaceContainerHighest = c.soft, secondaryContainer = c.soft,
            onSecondaryContainer = c.ink, primaryContainer = c.soft, onPrimaryContainer = c.ink,
            tertiaryContainer = c.soft, onTertiaryContainer = c.ink)
    }
    CompositionLocalProvider(LocalVayuColors provides c) {
        MaterialTheme(colorScheme = scheme, typography = VayuTypography, content = content)
    }
}
