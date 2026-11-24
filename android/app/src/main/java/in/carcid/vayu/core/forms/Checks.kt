package `in`.carcid.vayu.core.forms

import java.math.BigDecimal

/**
 * The server's answer rules (forms/fieldtypes.py clean_answer) the phone can check while the
 * expert types, so a wrong answer shows at once instead of being refused after Submit.
 * Returns what to fix, or null when the answer is fine (empty answers are "needed", not wrong).
 */
fun answerProblem(f: Field, v: Any?): String? {
    if (v == null || v == "") return null
    val c = f.config
    return when (f.type) {
        "phone" -> if (v is String && indianMobile(v) == null) "Enter a 10-digit Indian mobile number." else null
        "number" -> number(v, (c["decimals"] as? Number)?.toInt() ?: 0, c["min"] as? Number, c["max"] as? Number)
        "currency" -> number(v, 2, 0, null)
        "short_text", "long_text" -> {
            val text = (v as? String)?.let { if (f.type == "short_text") it.trim() else it } ?: return null
            val max = (c["max_length"] as? Number)?.toInt() ?: if (f.type == "short_text") 200 else 5000
            val pattern = c["pattern"] as? String
            when {
                text.length > max -> "Too long: at most $max characters."
                pattern != null && runCatching { !Regex(pattern).matches(text) }.getOrDefault(false) ->
                    (c["pattern_message"] as? String)?.ifBlank { null } ?: "Wrong format."
                else -> null
            }
        }
        else -> null
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

private fun number(v: Any, decimals: Int, lo: Number?, hi: Number?): String? {
    val d = runCatching { BigDecimal(v.toString().trim()) }.getOrNull() ?: return "Enter a number."
    if (d.stripTrailingZeros().scale() > decimals) return if (decimals == 0) "Enter a whole number." else "Use at most $decimals decimal places."
    if ((lo != null && d < BigDecimal(lo.toString())) || (hi != null && d > BigDecimal(hi.toString())))
        return when {
            lo != null && hi != null -> "Must be between ${plain(lo)} and ${plain(hi)}."
            lo != null -> "Must be at least ${plain(lo)}."
            else -> "Must be at most ${plain(hi!!)}."
        }
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
