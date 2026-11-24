package `in`.carcid.vayu.core.rules

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import java.math.BigDecimal

/**
 * JsonLogic for the operators Vayu allows (shared/rule-vectors/SCHEMA.md), behaving exactly like
 * json-logic-js 2.0.5, the reference the web uses, including JavaScript's coercion rules. Proven by
 * the shared cases the server and the web pass too.
 *
 * Values are plain Kotlin: null, Boolean, Double, String, List<Any?>, Map<String, Any?>.
 */
object JsonLogic {

    /** Never throws: a rule that cannot apply gives null; NaN and Infinity also become null. */
    fun evaluate(rule: Any?, data: Any?): Any? = try {
        when (val v = apply(rule, data)) {
            is Double -> if (v.isFinite()) v else null
            else -> v
        }
    } catch (_: RuntimeException) {
        null
    }

    /** Truthiness of a rule; a missing rule (null) counts as true. */
    fun truthy(rule: Any?, data: Any?): Boolean =
        rule == null || truthy(evaluate(mapOf("!!" to listOf(rule)), data))

    fun truthy(v: Any?): Boolean = when (v) {
        is List<*> -> v.isNotEmpty()
        else -> jsTruthy(v)
    }

    private fun isLogic(x: Any?) = x is Map<*, *> && x.size == 1

    @Suppress("UNCHECKED_CAST")
    fun apply(logic: Any?, data: Any?): Any? {
        if (logic is List<*>) return logic.map { apply(it, data) }
        if (!isLogic(logic)) return logic
        val (op, raw) = (logic as Map<String, Any?>).entries.first()
        val values: List<Any?> = raw as? List<Any?> ?: listOf(raw)

        when (op) {
            "if", "?:" -> {
                var i = 0
                while (i < values.size - 1) {
                    if (truthy(apply(values[i], data))) return apply(values[i + 1], data)
                    i += 2
                }
                return if (values.size == i + 1) apply(values[i], data) else null
            }
            "and" -> {
                var current: Any? = null
                for (v in values) { current = apply(v, data); if (!truthy(current)) return current }
                return current
            }
            "or" -> {
                var current: Any? = null
                for (v in values) { current = apply(v, data); if (truthy(current)) return current }
                return current
            }
            "filter" -> {
                val scoped = apply(values.getOrNull(0), data)
                if (scoped !is List<*>) return emptyList<Any?>()
                return scoped.filter { truthy(apply(values.getOrNull(1), it)) }
            }
            "reduce" -> {
                val scoped = apply(values.getOrNull(0), data)
                val initial = if (values.size > 2) apply(values[2], data) else null
                if (scoped !is List<*>) return initial
                return scoped.fold(initial) { acc, cur ->
                    apply(values.getOrNull(1), mapOf("current" to cur, "accumulator" to acc))
                }
            }
            "all" -> {
                val scoped = apply(values.getOrNull(0), data)
                val items: List<Any?> = when (scoped) {
                    is List<*> -> scoped
                    is String -> scoped.map { it.toString() }
                    else -> return false                                      // no .length
                }
                if (items.isEmpty()) return false
                return items.all { truthy(apply(values.getOrNull(1), it)) }
            }
            "none" -> return (apply(mapOf("filter" to values), data) as List<*>).isEmpty()
            "some" -> return (apply(mapOf("filter" to values), data) as List<*>).isNotEmpty()
        }

        val a = values.map { apply(it, data) }
        val x = a.getOrNull(0)
        val y = a.getOrNull(1)
        return when (op) {
            "==" -> looseEquals(x, y)
            "!=" -> !looseEquals(x, y)
            "===" -> strictEquals(x, y)
            "!==" -> !strictEquals(x, y)
            "<" -> if (a.size > 2) less(x, y) && less(y, a[2]) else less(x, y)
            "<=" -> if (a.size > 2) lessEq(x, y) && lessEq(y, a[2]) else lessEq(x, y)
            ">" -> less(y, x)
            ">=" -> lessEq(y, x)
            "!!" -> truthy(x)
            "!" -> !truthy(x)
            "in" -> inOp(x, y)
            "+" -> a.fold(0.0) { acc, v -> acc + parseFloat(v) }
            "var" -> variable(x, if (a.size > 1) y else null, data)
            else -> throw IllegalArgumentException("Unrecognized operation $op")
        }
    }

    private fun variable(path: Any?, notFound: Any?, data: Any?): Any? {
        if (path == null || path == "") return data
        var cur: Any? = data
        for (prop in toJsString(path).split(".")) {
            if (cur == null) return notFound
            val next = property(cur, prop)
            if (next === UNDEFINED) return notFound
            cur = next
        }
        return cur
    }

    /** JS ``obj[prop]``: a stored JSON null is null; a missing key is UNDEFINED. */
    private fun property(obj: Any, prop: String): Any? {
        fun index(size: Int) = prop.toIntOrNull()?.takeIf { it in 0 until size && prop == it.toString() }
        return when (obj) {
            is Map<*, *> -> if (obj.containsKey(prop)) obj[prop] else UNDEFINED
            is List<*> -> if (prop == "length") obj.size.toDouble() else index(obj.size)?.let { obj[it] } ?: if (index(obj.size) != null) null else UNDEFINED
            is String -> if (prop == "length") obj.length.toDouble() else index(obj.length)?.let { obj[it].toString() } ?: UNDEFINED
            else -> UNDEFINED
        }
    }

    private val UNDEFINED = Any()

    // ---------------------------------------------------------------- JavaScript semantics

    fun jsTruthy(v: Any?): Boolean = when (v) {
        null -> false
        is Boolean -> v
        is Double -> !(v == 0.0 || v.isNaN())
        is String -> v.isNotEmpty()
        else -> true                         // arrays and objects
    }

    private fun strictEquals(x: Any?, y: Any?): Boolean = when {
        x == null || y == null -> x == null && y == null
        x is Double && y is Double -> x == y              // NaN != NaN
        x is List<*> || x is Map<*, *> -> x === y         // identity, like JS objects
        else -> x::class == y::class && x == y
    }

    private fun looseEquals(x: Any?, y: Any?): Boolean {
        if (x == null || y == null) return x == null && y == null
        if (x::class == y::class || (x is List<*> && y is List<*>) || (x is Map<*, *> && y is Map<*, *>)) {
            return strictEquals(x, y)
        }
        if (x is Double && y is String) return x == toNumber(y)
        if (x is String && y is Double) return toNumber(x) == y
        if (x is Boolean) return looseEquals(toNumber(x), y)
        if (y is Boolean) return looseEquals(x, toNumber(y))
        if ((x is String || x is Double) && (y is List<*> || y is Map<*, *>)) return looseEquals(x, toPrimitive(y))
        if ((x is List<*> || x is Map<*, *>) && (y is String || y is Double)) return looseEquals(toPrimitive(x), y)
        return false
    }

    /** JS abstract relational comparison: true / false, or null for "undefined" (NaN involved). */
    private fun compare(x: Any?, y: Any?): Boolean? {
        val px = toPrimitive(x)
        val py = toPrimitive(y)
        if (px is String && py is String) return px < py      // UTF-16 code units, like JS
        val nx = toNumber(px)
        val ny = toNumber(py)
        if (nx.isNaN() || ny.isNaN()) return null
        return nx < ny
    }

    private fun less(x: Any?, y: Any?): Boolean = compare(x, y) == true
    private fun lessEq(x: Any?, y: Any?): Boolean = when (compare(y, x)) {
        null, true -> false
        false -> true
    }

    private fun inOp(x: Any?, y: Any?): Boolean {
        if (!jsTruthy(y)) return false
        return when (y) {
            is String -> y.contains(toJsString(x))
            is List<*> -> y.any { strictEquals(it, x) }
            else -> false
        }
    }

    private fun toPrimitive(v: Any?): Any? = when (v) {
        is List<*> -> v.joinToString(",") { if (it == null) "" else toJsString(it) }
        is Map<*, *> -> "[object Object]"
        else -> v
    }

    fun toNumber(v: Any?): Double = when (v) {
        null -> 0.0
        is Boolean -> if (v) 1.0 else 0.0
        is Double -> v
        is String -> stringToNumber(v)
        is List<*>, is Map<*, *> -> toNumber(toPrimitive(v))
        else -> Double.NaN
    }

    private val DECIMAL = Regex("[+-]?(\\d+\\.?\\d*([eE][+-]?\\d+)?|\\.\\d+([eE][+-]?\\d+)?)")
    private val HEX = Regex("0[xX][0-9a-fA-F]+")
    private val PREFIX = Regex("^[+-]?(Infinity|\\d+\\.?\\d*([eE][+-]?\\d+)?|\\.\\d+([eE][+-]?\\d+)?)")

    private fun stringToNumber(s: String): Double {
        val t = s.trim()
        return when {
            t.isEmpty() -> 0.0
            t == "Infinity" || t == "+Infinity" -> Double.POSITIVE_INFINITY
            t == "-Infinity" -> Double.NEGATIVE_INFINITY
            DECIMAL.matches(t) -> t.toDouble()
            HEX.matches(t) -> t.substring(2).toLong(16).toDouble()
            else -> Double.NaN
        }
    }

    /** JS parseFloat(String(v)): the longest number at the start, else NaN. */
    private fun parseFloat(v: Any?): Double {
        val s = toJsString(v).trimStart()
        val m = PREFIX.find(s) ?: return Double.NaN
        val text = m.value
        return when {
            text.endsWith("Infinity") -> if (text.startsWith("-")) Double.NEGATIVE_INFINITY else Double.POSITIVE_INFINITY
            else -> text.toDouble()
        }
    }

    fun toJsString(v: Any?): String = when (v) {
        null -> "null"
        is Boolean -> v.toString()
        is Double -> numberToString(v)
        is String -> v
        is List<*>, is Map<*, *> -> toPrimitive(v) as String
        else -> v.toString()
    }

    private fun numberToString(d: Double): String = when {
        d.isNaN() -> "NaN"
        d.isInfinite() -> if (d > 0) "Infinity" else "-Infinity"
        d == 0.0 -> "0"
        d == Math.floor(d) && Math.abs(d) < 1e21 -> d.toLong().toString()
        Math.abs(d) >= 1e-6 && Math.abs(d) < 1e21 -> BigDecimal(d.toString()).stripTrailingZeros().toPlainString()
        else -> {
            val (mant, exp) = d.toString().split("E")
            val m = mant.removeSuffix(".0")
            "${m}e${if (exp.startsWith("-")) exp else "+$exp"}"
        }
    }

    // ---------------------------------------------------------------- JSON in and out

    fun fromJson(e: JsonElement?): Any? = when (e) {
        null, is JsonNull -> null
        is JsonObject -> e.mapValues { fromJson(it.value) }
        is JsonArray -> e.map { fromJson(it) }
        is JsonPrimitive -> when {
            e.isString -> e.content
            e.booleanOrNull != null -> e.booleanOrNull
            else -> e.content.toDouble()
        }
    }

    /** Back to JSON; whole numbers go out without ".0" (ids and counts stay integers). */
    fun toJson(v: Any?): JsonElement = when (v) {
        null -> JsonNull
        is JsonElement -> v
        is Boolean -> JsonPrimitive(v)
        is Double -> if (v % 1.0 == 0.0 && kotlin.math.abs(v) < 1e15) JsonPrimitive(v.toLong()) else JsonPrimitive(v)
        is Number -> JsonPrimitive(v)
        is String -> JsonPrimitive(v)
        is Map<*, *> -> JsonObject(v.entries.associate { (k, x) -> k.toString() to toJson(x) })
        is List<*> -> JsonArray(v.map { toJson(it) })
        else -> JsonPrimitive(v.toString())
    }
}
