package `in`.carcid.vayu.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp
import `in`.carcid.vayu.ui.theme.Vayu

/*
 * The three drawings from the approved prototype (sign in, Admin refused, choose password),
 * copied shape for shape from its SVGs. Coordinates are in each SVG's viewBox units.
 */

private val White = Color.White

private class Svg(val d: DrawScope) {
    fun circle(cx: Float, cy: Float, r: Float, fill: Color? = null, stroke: Color? = null, w: Float = 0f) {
        fill?.let { d.drawCircle(it, r, Offset(cx, cy)) }
        stroke?.let { d.drawCircle(it, r, Offset(cx, cy), style = Stroke(w)) }
    }

    fun rect(x: Float, y: Float, w: Float, h: Float, rx: Float, fill: Color? = null, stroke: Color? = null, sw: Float = 0f) {
        fill?.let { d.drawRoundRect(it, Offset(x, y), Size(w, h), CornerRadius(rx)) }
        stroke?.let { d.drawRoundRect(it, Offset(x, y), Size(w, h), CornerRadius(rx), style = Stroke(sw)) }
    }

    fun path(data: String, fill: Color? = null, stroke: Color? = null, w: Float = 0f,
             cap: StrokeCap = StrokeCap.Butt, join: StrokeJoin = StrokeJoin.Miter) {
        val p = PathParser().parsePathString(data).toPath()
        fill?.let { d.drawPath(p, it) }
        stroke?.let { d.drawPath(p, it, style = Stroke(w, cap = cap, join = join)) }
    }
}

@Composable
private fun Drawing(vw: Float, vh: Float, widthDp: Int, draw: Svg.() -> Unit) {
    Canvas(Modifier.size(widthDp.dp, (widthDp * vh / vw).dp)) {
        val s = size.width / vw
        scale(s, s, Offset.Zero) { Svg(this).draw() }
    }
}

/** Sign in: a car with an inspection checklist. */
@Composable
fun SignInDrawing() {
    val c = Vayu.colors
    Drawing(300f, 260f, 300) {
        circle(150f, 130f, 112f, fill = c.soft)
        rect(40f, 168f, 220f, 2f, 1f, fill = c.illo2)
        path("M62 168v-10c0-6 4-10 10-11l24-4 18-18c4-4 9-6 15-6h44c6 0 11 2 15 6l20 20 22 3c6 1 10 5 10 11v9",
            fill = c.illo, stroke = c.ink, w = 2.5f, join = StrokeJoin.Round)
        path("M118 141l14-14h38l15 14z", fill = c.bg, stroke = c.ink, w = 2f)
        for (x in listOf(100f, 205f)) {
            circle(x, 168f, 15f, fill = c.bg, stroke = c.ink, w = 2.5f)
            circle(x, 168f, 5f, fill = c.ink)
        }
        rect(196f, 38f, 62f, 100f, 10f, fill = c.bg, stroke = c.ink, sw = 2.5f)
        rect(206f, 52f, 42f, 6f, 3f, fill = c.illo2)
        rect(206f, 66f, 30f, 6f, 3f, fill = c.illo2)
        rect(206f, 80f, 36f, 6f, 3f, fill = c.illo2)
        circle(227f, 112f, 14f, fill = c.brand)
        path("M220 112l5 5 9-10", stroke = White, w = 3f, cap = StrokeCap.Round, join = StrokeJoin.Round)
        path("M38 96h34M48 108h22M30 120h30", stroke = c.illo2, w = 4f, cap = StrokeCap.Round)
    }
}

/** Admin refused: a laptop with an arrow pointing to the web. */
@Composable
fun AdminRefusedDrawing() {
    val c = Vayu.colors
    Drawing(260f, 240f, 260) {
        circle(130f, 120f, 104f, fill = c.soft)
        rect(48f, 62f, 164f, 108f, 10f, fill = c.bg, stroke = c.ink, sw = 2.5f)
        rect(48f, 62f, 164f, 20f, 10f, fill = c.illo, stroke = c.ink, sw = 2.5f)
        rect(64f, 96f, 60f, 8f, 4f, fill = c.illo2)
        rect(64f, 112f, 90f, 8f, 4f, fill = c.illo2)
        rect(64f, 128f, 74f, 8f, 4f, fill = c.illo2)
        path("M104 170l-8 22h68l-8-22", fill = c.illo, stroke = c.ink, w = 2.5f, join = StrokeJoin.Round)
        circle(192f, 150f, 22f, fill = c.brand)
        path("M184 150h16M194 143l7 7-7 7", stroke = White, w = 3f, cap = StrokeCap.Round, join = StrokeJoin.Round)
    }
}

/** Choose password: a padlock. */
@Composable
fun ChangePasswordDrawing() {
    val c = Vayu.colors
    Drawing(200f, 180f, 200) {
        circle(100f, 90f, 80f, fill = c.soft)
        rect(60f, 78f, 80f, 62f, 12f, fill = c.bg, stroke = c.ink, sw = 2.5f)
        path("M76 78V62a24 24 0 0 1 48 0v16", stroke = c.ink, w = 2.5f)
        circle(100f, 106f, 8f, fill = c.brand)
        path("M100 112v10", stroke = c.brand, w = 4f, cap = StrokeCap.Round)
    }
}
