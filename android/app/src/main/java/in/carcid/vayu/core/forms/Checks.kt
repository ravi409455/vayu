package `in`.carcid.vayu.core.forms

import java.math.BigDecimal

/**
 * The server's answer rules (forms/fieldtypes.py clean_answer) the phone can check while the
 * expert types, as the server's refusal code (INVALID_PHONE, INVALID_TYPE, TOO_MANY_DECIMALS,
 * OUT_OF_RANGE, TOO_LONG, PATTERN_MISMATCH), or null when fine. Empty answers are "needed", not
 * wrong. Kept equal to the server by shared/rule-vectors/answer_vectors.json. A pattern Java can't
 * compile (Python-only syntax) is left to the server.
 */
fun answerCode(f: Field, v: Any?): String? {
    if (v == null || v == "") return null
    val c = f.config
    return when (f.type) {
        "phone" -> if (v !is String) "INVALID_TYPE" else if (indianMobile(v) == null) "INVALID_PHONE" else null
        "number" -> numberCode(v, (c["decimals"] as? Number)?.toInt() ?: 0, c["min"] as? Number, c["max"] as? Number)
        "currency" -> numberCode(v, 2, 0, null)
        "short_text", "long_text" -> {
            val text = (v as? String)?.let { if (f.type == "short_text") it.trim() else it } ?: return "INVALID_TYPE"
            val max = (c["max_length"] as? Number)?.toInt() ?: if (f.type == "short_text") 200 else 5000
            val pattern = (c["pattern"] as? String)?.takeIf { it.isNotEmpty() }
            when {
                // characters as the server counts them (an emoji is one, not two UTF-16 units)
                text.codePointCount(0, text.length) > max -> "TOO_LONG"
                pattern != null && runCatching { !Regex(pattern).matches(text) }.getOrDefault(false) -> "PATTERN_MISMATCH"
                else -> null
            }
        }
        else -> null
    }
}

/** What to fix, in words, or null when the answer is fine (what the expert sees under the field). */
fun answerProblem(f: Field, v: Any?): String? {
    val c = f.config
    return when (answerCode(f, v)) {
        null -> null
        "INVALID_PHONE" -> "Enter a 10-digit Indian mobile number."
        "TOO_LONG" -> "Too long: at most ${(c["max_length"] as? Number)?.toInt() ?: if (f.type == "short_text") 200 else 5000} characters."
        "PATTERN_MISMATCH" -> (c["pattern_message"] as? String)?.ifBlank { null } ?: "Wrong format."
        "TOO_MANY_DECIMALS" -> (if (f.type == "currency") 2 else (c["decimals"] as? Number)?.toInt() ?: 0)
            .let { d -> if (d == 0) "Enter a whole number." else "Use at most $d decimal places." }
        "OUT_OF_RANGE" -> {
            val lo = if (f.type == "currency") 0 else c["min"] as? Number
            val hi = if (f.type == "currency") null else c["max"] as? Number
            when {
                lo != null && hi != null -> "Must be between ${plain(lo)} and ${plain(hi)}."
                lo != null -> "Must be at least ${plain(lo)}."
                else -> "Must be at most ${plain(hi!!)}."
            }
        }
        else -> if (f.type in setOf("number", "currency")) "Enter a number." else "Check this answer."
    }
}

/** "+91XXXXXXXXXX" for a 10-digit Indian mobile written any common way, else null (apps/core/phone.py). */
fun indianMobile(value: String): String? {
    var d = value.replace(Regex("[\\s\\-()]"), "")
    d = when {
        d.startsWith("+91") -> d.drop(3)
        d.length == 12 && d.startsWith("91") -> d.drop(2)
        d.length == 11 && d.startsWith("0") -> d.drop(1)
        else -> d
    }
    return if (Regex("[6-9]\\d{9}").matches(d)) "+91$d" else null
}

private fun numberCode(v: Any, decimals: Int, lo: Number?, hi: Number?): String? {
    if (v is Boolean || (v is Double && !v.isFinite()) || (v is Float && !v.isFinite())) return "INVALID_TYPE"
    val d = runCatching { BigDecimal(v.toString().trim()) }.getOrNull() ?: return "INVALID_TYPE"
    if (d.stripTrailingZeros().scale() > decimals) return "TOO_MANY_DECIMALS"
    if ((lo != null && d < BigDecimal(lo.toString())) || (hi != null && d > BigDecimal(hi.toString()))) return "OUT_OF_RANGE"
    return null
}

private fun plain(n: Number) = BigDecimal(n.toString()).stripTrailingZeros().toPlainString()

/** The server's refusal codes in words (shown under the field it refused). */
fun refusalText(code: String): String = when (code) {
    "required" -> "This is needed."
    "check_failed" -> "This doesn't fit with another answer."
    "INVALID_PHONE" -> "Enter a 10-digit Indian mobile number."
    "OUT_OF_RANGE" -> "This number is out of range."
    "TOO_MANY_DECIMALS" -> "Too many decimal places."
    "TOO_LONG" -> "Too long."
    "PATTERN_MISMATCH" -> "Wrong format."
    "UNKNOWN_MEDIA", "WRONG_MEDIA_KIND" -> "A file didn't arrive; take it again."
    "TOO_FEW" -> "Add more files."
    "TOO_MANY" -> "Too many files."
    "INVALID_OPTION", "ARCHIVED_OPTION" -> "That choice isn't available any more; pick again."
    else -> if (code.contains(' ')) code else "Check this answer."
}
