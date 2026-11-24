package `in`.carcid.vayu.core.api

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Every endpoint the app calls exists, with that method, in backend/openapi.yaml (the frozen API).
 * Reads the calls straight from Api.kt, so a new call is checked without editing this test.
 */
class ApiContractTest {
    private fun up(rel: String) = generateSequence(File(System.getProperty("user.dir")).absoluteFile) { it.parentFile }
        .map { File(it, rel) }.first { it.exists() }

    @Test fun everyCallIsInTheApiDescription() {
        val source = up("app/src/main/java/in/carcid/vayu/core/api/Api.kt").readText()
        // "bookings/$bookingId/start" -> "bookings/{id}/start" (the spec names every path id {id})
        val calls = Regex("""(?:call|send)\("(GET|POST|PATCH|PUT|DELETE)", "([a-z0-9/_${'$'}A-Za-z-]+)""").findAll(source)
            .map { it.groupValues[1].lowercase() to it.groupValues[2].replace(Regex("\\${'$'}[A-Za-z]+"), "{id}") }.toSet()
        assertTrue("no calls found in Api.kt", calls.size >= 7)
        // openapi.yaml: "  /api/v1/<path>:" then its methods indented below it
        val spec = up("backend/openapi.yaml").readLines()
        val missing = calls.filterNot { (method, path) ->
            val at = spec.indexOf("  /api/v1/$path:")
            at >= 0 && spec.drop(at + 1).takeWhile { it.startsWith("    ") }.any { it == "    $method:" }
        }
        assertTrue("not in backend/openapi.yaml: $missing", missing.isEmpty())
    }
}
