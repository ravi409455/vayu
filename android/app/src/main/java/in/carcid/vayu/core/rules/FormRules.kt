package `in`.carcid.vayu.core.rules

/**
 * Vayu's form logic on top of JsonLogic (shared/rule-vectors/SCHEMA.md, normative). Mirrors
 * backend/apps/forms/rules.py and web/src/rules/rules.ts; all three pass the same shared cases.
 */
object FormRules {
    val FORMS = listOf("booking", "start", "end", "inspection")
    private val CHOICE = setOf("single_choice", "multi_choice")

    data class Container(val id: String, val kind: String, val parent: String? = null,
                         val visible: Boolean = true, val showIf: Any? = null)

    data class Option(val key: String, val isDefect: Boolean = false)

    data class Field(val key: String, val type: String, val section: String, val visible: Boolean = true,
                     val showIf: Any? = null, val required: Boolean = false, val requiredIf: Any? = null,
                     val options: List<Option> = emptyList(), val rule: Any? = null)

    data class Check(val rule: Any?, val message: String, val fields: List<String>)

    data class Spec(val form: String, val containers: List<Container>, val fields: List<Field>,
                    val checks: List<Check> = emptyList())

    data class Result(val visible: Map<String, Boolean>, val required: Map<String, Boolean>,
                      val errors: Map<String, String>, val derived: Map<String, Any?>,
                      val defects: List<String>)

    fun isEmpty(v: Any?): Boolean = when (v) {
        null -> true
        is String -> v.isBlank()
        is List<*> -> v.isEmpty()
        is Map<*, *> -> v.isEmpty()
        else -> false
    }

    private fun normalise(answers: Map<String, Any?>?): Map<String, Any?> =
        (answers ?: emptyMap()).mapValues { if (isEmpty(it.value)) null else it.value }

    private fun isDefect(f: Field, value: Any?): Boolean {
        if (f.type !in CHOICE || value == null) return false
        val defects = f.options.filter { it.isDefect }.map { it.key }.toSet()
        val chosen = if (value is List<*>) value else listOf(value)
        return chosen.any { it in defects }
    }

    fun evaluate(spec: Spec, answers: Map<String, Map<String, Any?>?>, today: String,
                 overrides: Map<String, Any?> = emptyMap()): Result {
        val own = spec.form
        val base = FORMS.associateWith { normalise(answers[it]) }
        val values = spec.fields.associate { it.key to base[own]?.get(it.key) }
        val containers = spec.containers.associateBy { it.id }

        fun buildData(vis: Map<String, Boolean>): Map<String, Any?> {
            val shown = spec.fields.associate { it.key to if (vis[it.key] == true) values[it.key] else null }
            val defects = spec.fields.filter { vis[it.key] == true && isDefect(it, values[it.key]) }
                .map { "$own.${it.key}" }.sorted()
            return base + mapOf(own to shown, "_today" to today, "_defects" to defects)
        }

        fun containerVisible(cid: String?, data: Map<String, Any?>, memo: MutableMap<String, Boolean>): Boolean {
            if (cid == null) return true
            memo[cid]?.let { return it }
            val c = containers[cid] ?: error("Unknown container $cid")
            val v = c.visible && containerVisible(c.parent, data, memo) && JsonLogic.truthy(c.showIf, data)
            memo[cid] = v
            return v
        }

        var visible = spec.fields.associate { it.key to true }
        var settled = false
        repeat(spec.fields.size + spec.containers.size + 2) {
            if (settled) return@repeat
            val data = buildData(visible)
            val memo = mutableMapOf<String, Boolean>()
            val next = spec.fields.associate {
                it.key to (it.visible && containerVisible(it.section, data, memo) && JsonLogic.truthy(it.showIf, data))
            }
            if (spec.fields.all { next[it.key] == visible[it.key] }) settled = true else visible = next
        }
        check(settled) { "Visibility did not settle: the form has a rule cycle." }

        val data = buildData(visible)
        val derived = spec.fields.filter { it.type == "derived" }.associate { f ->
            val ov = overrides[f.key]
            f.key to when {
                visible[f.key] != true -> null
                ov != null -> ov
                else -> JsonLogic.truthy(f.rule, data)
            }
        }
        val required = spec.fields.associate {
            it.key to (visible[it.key] == true &&
                (it.required || (it.requiredIf != null && JsonLogic.truthy(it.requiredIf, data))))
        }
        val errors = linkedMapOf<String, String>()
        spec.fields.filter { required[it.key] == true && values[it.key] == null }.forEach { errors[it.key] = "required" }
        for (c in spec.checks) {
            val runnable = c.fields.all { visible[it] == true && values[it] != null }
            if (runnable && !JsonLogic.truthy(c.rule, data)) c.fields.forEach { errors.putIfAbsent(it, "check_failed") }
        }
        @Suppress("UNCHECKED_CAST")
        return Result(visible, required, errors, derived, data["_defects"] as List<String>)
    }
}
