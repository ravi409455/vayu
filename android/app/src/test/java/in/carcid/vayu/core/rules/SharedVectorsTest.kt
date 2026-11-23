package `in`.carcid.vayu.core.rules

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Runs every case in /shared/rule-vectors, the same files the Python and web suites run. */
class SharedVectorsTest {
    private fun load(name: String): JsonArray {
        val dir = generateSequence(File(System.getProperty("user.dir")).absoluteFile) { it.parentFile }
            .map { File(it, "shared/rule-vectors") }.first { it.isDirectory }
        return Json.parseToJsonElement(File(dir, name).readText()).jsonArray
    }

    /** Deep equality with JSON numbers compared as doubles. */
    private fun same(a: Any?, b: Any?): Boolean = when {
        a is List<*> && b is List<*> -> a.size == b.size && a.indices.all { same(a[it], b[it]) }
        a is Map<*, *> && b is Map<*, *> -> a.keys == b.keys && a.keys.all { same(a[it], b[it]) }
        a is Double && b is Double -> a == b
        else -> a == b
    }

    private fun runEval(name: String) {
        val failures = load(name).map { it.jsonObject }.mapNotNull { c ->
            val got = JsonLogic.evaluate(JsonLogic.fromJson(c["rule"]), JsonLogic.fromJson(c["data"]))
            val want = JsonLogic.fromJson(c["expected"])
            if (same(got, want)) null else "${c["name"]}: rule=${c["rule"]} data=${c["data"]} want=$want got=$got"
        }
        assertTrue("${failures.size} failing:\n" + failures.take(25).joinToString("\n"), failures.isEmpty())
    }

    @Test fun evalVectors() = runEval("eval_vectors.json")
    @Test fun robustVectors() = runEval("robust_vectors.json")

    @Suppress("UNCHECKED_CAST")
    private fun spec(o: JsonObject): FormRules.Spec {
        val m = JsonLogic.fromJson(o) as Map<String, Any?>
        val containers = (m["containers"] as List<Map<String, Any?>>).map {
            FormRules.Container(it["id"] as String, it["kind"] as String, it["parent"] as String?,
                it["visible"] as Boolean? ?: true, it["show_if"])
        }
        val fields = (m["fields"] as List<Map<String, Any?>>).map { f ->
            FormRules.Field(f["key"] as String, f["type"] as String, f["section"] as String,
                f["visible"] as Boolean? ?: true, f["show_if"], f["required"] as Boolean? ?: false,
                f["required_if"],
                ((f["options"] as List<Map<String, Any?>>?) ?: emptyList()).map {
                    FormRules.Option(it["key"] as String, it["is_defect"] as Boolean? ?: false)
                },
                f["rule"])
        }
        val checks = ((m["checks"] as List<Map<String, Any?>>?) ?: emptyList()).map {
            FormRules.Check(it["rule"], it["message"] as String, it["fields"] as List<String>)
        }
        return FormRules.Spec(m["form"] as String, containers, fields, checks)
    }

    @Suppress("UNCHECKED_CAST")
    @Test fun formVectors() {
        val failures = load("form_vectors.json").map { it.jsonObject }.mapNotNull { c ->
            val name = c["name"]
            val r = FormRules.evaluate(spec(c["spec"]!!.jsonObject),
                JsonLogic.fromJson(c["answers"]) as Map<String, Map<String, Any?>?>,
                JsonLogic.fromJson(c["today"]) as String,
                (JsonLogic.fromJson(c["overrides"]) as Map<String, Any?>?) ?: emptyMap())
            val want = JsonLogic.fromJson(c["expected"]) as Map<String, Any?>
            val problems = buildList {
                (want["visible"] as Map<String, Any?>?)?.forEach { (k, v) -> if (r.visible[k] != v) add("visible.$k") }
                (want["required"] as Map<String, Any?>?)?.forEach { (k, v) -> if (r.required[k] != v) add("required.$k") }
                if (!same(r.errors, want["errors"])) add("errors ${r.errors} != ${want["errors"]}")
                if (!same(r.derived, want["derived"])) add("derived ${r.derived} != ${want["derived"]}")
                if (!same(r.defects, want["defects"])) add("defects ${r.defects} != ${want["defects"]}")
            }
            if (problems.isEmpty()) null else "$name: $problems"
        }
        assertEquals("form cases failing:\n" + failures.joinToString("\n"), 0, failures.size)
    }
}
