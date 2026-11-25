package `in`.carcid.vayu

import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

/**
 * The agreed words (docs/plan-leads-bookings-words.md): experts read "lead", Ops "booking", nobody
 * ever "job". Reads every string literal in the app's code (not comments, not code keys) and fails on
 * "job"/"jobs" anywhere, and on "booking" in expert-only screens except "Booking ID".
 */
class WordsTest {
    private val root = File("src/main/java/in/carcid/vayu")

    /** The string literals of a Kotlin file, with `${…}` templates left out (their insides are code). */
    private fun literals(src: String): List<Pair<Int, String>> {
        val out = mutableListOf<Pair<Int, String>>()
        var i = 0; var line = 1
        fun at(k: Int) = if (k < src.length) src[k] else '\u0000'
        while (i < src.length) {
            val c = src[i]
            when {
                c == '\n' -> { line++; i++ }
                c == '/' && at(i + 1) == '/' -> { while (i < src.length && src[i] != '\n') i++ }
                c == '/' && at(i + 1) == '*' -> { i += 2; while (i < src.length && !(src[i] == '*' && at(i + 1) == '/')) { if (src[i] == '\n') line++; i++ }; i += 2 }
                c == '\'' -> { i++; while (i < src.length && src[i] != '\'') { if (src[i] == '\\') i++; i++ }; i++ }
                c == '"' -> {
                    val raw = at(i + 1) == '"' && at(i + 2) == '"'
                    i += if (raw) 3 else 1
                    val start = line; val sb = StringBuilder()
                    while (i < src.length) {
                        if (raw && src.startsWith("\"\"\"", i)) { i += 3; break }
                        if (!raw && src[i] == '"') { i++; break }
                        if (!raw && src[i] == '\\') { sb.append(at(i + 1)); i += 2; continue }
                        if (src[i] == '$' && at(i + 1) == '{') {           // skip a template, nested braces included
                            var depth = 1; i += 2
                            while (i < src.length && depth > 0) { if (src[i] == '{') depth++ else if (src[i] == '}') depth--; if (src[i] == '\n') line++; i++ }
                            sb.append(' '); continue
                        }
                        if (src[i] == '\n') line++
                        sb.append(src[i]); i++
                    }
                    out += start to sb.toString()
                }
                else -> i++
            }
        }
        return out
    }

    /** Text a person reads: has a space or starts with a capital (code keys like "jobs" or "remind-x" don't). */
    private fun shown(s: String) = s.contains(' ') || s.firstOrNull()?.isUpperCase() == true

    @Test fun noScreenSaysJobAndExpertScreensSayLead() {
        val wrong = root.walk().filter { it.extension == "kt" }.flatMap { f ->
            val expert = f.path.contains("/ui/expert/")
            literals(f.readText()).filter { (_, s) -> shown(s) }.mapNotNull { (n, s) ->
                val job = Regex("\\b[Jj]obs?\\b").containsMatchIn(s)
                val booking = expert && Regex("\\b[Bb]ookings?\\b").containsMatchIn(s.replace("Booking ID", ""))
                if (job || booking) "${f.relativeTo(root)}:$n \"$s\"" else null
            }
        }.toList()
        assertEquals("", wrong.joinToString("\n"))
    }
}
