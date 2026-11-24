package `in`.carcid.vayu.core.forms

import `in`.carcid.vayu.core.rules.FormRules
import `in`.carcid.vayu.core.rules.JsonLogic
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject

/** The parts an inspection goes through, in order: check-in, the custom form, wrap-up. */
val PARTS = listOf("start", "inspection", "end")

data class Option(val key: String, val label: String, val isDefect: Boolean, val severity: String?)

data class Field(
    val key: String, val label: String, val type: String, val help: String,
    val required: Boolean, val requiredIf: Any?, val showIf: Any?, val visible: Boolean,
    /** "edit" or "view" for this person (hidden fields never reach the phone). */
    val level: String,
    val config: Map<String, Any?>,
) {
    @Suppress("UNCHECKED_CAST")
    val options: List<Option> get() = (config["options"] as? List<Map<String, Any?>>).orEmpty().map {
        Option(it["key"] as String, (it["label"] as? String) ?: (it["key"] as String),
            it["is_defect"] == true, it["severity"] as? String)
    }
    val editable: Boolean get() = level == "edit" && type !in SYSTEM_MADE
    /** Never typed by the expert: computed, or only shown. */
    val answerable: Boolean get() = type !in SYSTEM_MADE && type != "image"
    val isMedia: Boolean get() = type in MEDIA
    val maxCount: Int get() = if (type == "signature") 1
        else (config["max_count"] as? Number)?.toInt() ?: if (type == "video") 3 else 10

    companion object {
        val MEDIA = setOf("photo", "video", "file", "signature")
        val SYSTEM_MADE = setOf("derived", "rating")
    }
}

data class Section(val id: Int, val title: String, val visible: Boolean, val showIf: Any?, val fields: List<Field>)
data class Page(val id: Int, val title: String, val visible: Boolean, val gate: Boolean, val showIf: Any?, val sections: List<Section>) {
    val fields: List<Field> get() = sections.flatMap { it.fields }
}

/** One form version as the API sends it (forms/serializers.py VersionTreeSerializer, trimmed for the role). */
data class FormTree(val id: Int, val pages: List<Page>, val checks: List<FormRules.Check>) {
    val fields: List<Field> get() = pages.flatMap { it.fields }
    fun field(key: String): Field? = fields.firstOrNull { it.key == key }

    fun spec(part: String) = FormRules.Spec(part,
        pages.flatMap { p ->
            listOf(FormRules.Container("p${p.id}", "page", null, p.visible, p.showIf)) +
                p.sections.map { s -> FormRules.Container("s${s.id}", "section", "p${p.id}", s.visible, s.showIf) }
        },
        pages.flatMap { p -> p.sections.flatMap { s -> s.fields.map { f ->
            FormRules.Field(f.key, f.type, "s${s.id}", f.visible, f.showIf, f.required, f.requiredIf,
                f.options.map { FormRules.Option(it.key, it.isDefect) }, if (f.type == "derived") f.config["rule"] else null)
        } } },
        checks)

    companion object {
        @Suppress("UNCHECKED_CAST")
        fun parse(o: JsonObject): FormTree {
            fun JsonObject.s(k: String) = (this[k] as? JsonPrimitive)?.contentOrNull ?: ""
            fun JsonObject.b(k: String, d: Boolean) = (this[k] as? JsonPrimitive)?.booleanOrNull ?: d
            fun JsonObject.logic(k: String) = this[k]?.let { JsonLogic.fromJson(it) }
            val pages = (o["pages"] as? JsonArray).orEmpty().map { it.jsonObject }.map { p ->
                Page((p["id"] as JsonPrimitive).intOrNull ?: 0, p.s("title"), p.b("visible", true), p.b("gate", false), p.logic("show_if"),
                    (p["sections"] as? JsonArray).orEmpty().map { it.jsonObject }.map { s ->
                        Section((s["id"] as JsonPrimitive).intOrNull ?: 0, s.s("title"), s.b("visible", true), s.logic("show_if"),
                            (s["fields"] as? JsonArray).orEmpty().map { it.jsonObject }.map { f ->
                                Field(f.s("key"), f.s("label").ifBlank { f.s("key") }, f.s("type"), f.s("helper_text"),
                                    f.b("required", false), f.logic("required_if"), f.logic("show_if"), f.b("visible", true),
                                    f.s("level").ifBlank { "edit" },
                                    (f["config"]?.let { JsonLogic.fromJson(it) } as? Map<String, Any?>).orEmpty())
                            })
                    })
            }
            val checks = (o["checks"] as? JsonArray).orEmpty().map { it.jsonObject }.map { c ->
                FormRules.Check(c.logic("rule"), c.s("message"),
                    (c["fields"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.contentOrNull })
            }
            return FormTree((o["id"] as? JsonPrimitive)?.intOrNull ?: 0, pages, checks)
        }
    }
}

/** A question still to answer. */
data class Gap(val part: String, val key: String, val label: String, val pageId: Int, val pageTitle: String)

/**
 * The forms of one inspection with its answers: what is visible, required, missing (port of
 * web/src/lib/formSpec.ts). [answers] is by part; [booking] the booking's answers.
 */
class Filled(val trees: Map<String, FormTree?>, val answers: Map<String, Map<String, Any?>>,
             val booking: Map<String, Any?>, val today: String) {
    private val results = HashMap<String, FormRules.Result>()

    fun result(part: String): FormRules.Result = results.getOrPut(part) {
        FormRules.evaluate(trees[part]!!.spec(part),
            mapOf("booking" to booking) + PARTS.associateWith { answers[it] }, today)
    }

    fun visible(part: String, key: String) = result(part).visible[key] == true
    fun required(part: String, key: String) = result(part).required[key] == true

    fun visiblePages(part: String): List<Page> {
        val t = trees[part] ?: return emptyList()
        return t.pages.filter { p -> p.fields.any { visible(part, it.key) } }
    }

    fun gaps(part: String): List<Gap> {
        val t = trees[part] ?: return emptyList()
        val values = answers[part].orEmpty()
        return t.pages.flatMap { p -> p.fields.filter {
            it.answerable && visible(part, it.key) && required(part, it.key) && FormRules.isEmpty(values[it.key])
        }.map { Gap(part, it.key, it.label, p.id, p.title) } }
    }

    fun allGaps(): List<Gap> = PARTS.flatMap { gaps(it) }

    fun pageGaps(part: String, page: Page): List<Gap> = gaps(part).filter { it.pageId == page.id }

    /** Only answers of visible, answerable fields: what the server receives. */
    fun submittable(part: String): Map<String, Any?> {
        val t = trees[part] ?: return emptyMap()
        val values = answers[part].orEmpty()
        return t.fields.filter { it.answerable && visible(part, it.key) && !FormRules.isEmpty(values[it.key]) }
            .associate { it.key to values[it.key] }
    }
}
