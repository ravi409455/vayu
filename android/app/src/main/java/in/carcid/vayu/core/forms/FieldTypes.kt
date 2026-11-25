package `in`.carcid.vayu.core.forms

/** What kind of answer a field takes; screens draw and word answers by kind (Q3: one place per type). */
enum class Kind { TEXT, NUMBER, WHEN, YES_NO, CHOICE, MULTI, LIST, FORM_CHOICE, USER, GPS, MEDIA, SIGNATURE, IMAGE, SYSTEM }

/** Which of the server's answer checks the phone runs while the expert types (Checks.kt). */
enum class Check { NONE, PHONE, NUMBER, CURRENCY, SHORT_TEXT, LONG_TEXT }

/**
 * One field type: its [kind], whether it holds files ([media]), whether the system fills it
 * ([systemMade], Ops may override), and its phone-side [check]. A new type that behaves like an
 * existing kind is one row here.
 */
data class FieldType(val key: String, val kind: Kind, val check: Check = Check.NONE,
                     val media: Boolean = false, val systemMade: Boolean = false) {
    /** A person can answer it (not filled by the system, not a picture the Admin shows). */
    val answerable: Boolean get() = !systemMade && kind != Kind.IMAGE
}

/** Every field type, the same list as the server's FieldType (FieldTypesTest checks it). */
object FieldTypes {
    val all: List<FieldType> = listOf(
        FieldType("short_text", Kind.TEXT, Check.SHORT_TEXT),
        FieldType("long_text", Kind.TEXT, Check.LONG_TEXT),
        FieldType("phone", Kind.TEXT, Check.PHONE),
        FieldType("number", Kind.NUMBER, Check.NUMBER),
        FieldType("currency", Kind.NUMBER, Check.CURRENCY),
        FieldType("date", Kind.WHEN), FieldType("time", Kind.WHEN), FieldType("datetime", Kind.WHEN),
        FieldType("yes_no", Kind.YES_NO),
        FieldType("single_choice", Kind.CHOICE),
        FieldType("multi_choice", Kind.MULTI),
        FieldType("master_list", Kind.LIST),
        FieldType("form_choice", Kind.FORM_CHOICE),
        FieldType("user_picker", Kind.USER),
        FieldType("gps", Kind.GPS),
        FieldType("photo", Kind.MEDIA, media = true), FieldType("video", Kind.MEDIA, media = true),
        FieldType("file", Kind.MEDIA, media = true),
        FieldType("signature", Kind.SIGNATURE, media = true),
        FieldType("image", Kind.IMAGE),
        FieldType("derived", Kind.SYSTEM, systemMade = true), FieldType("rating", Kind.SYSTEM, systemMade = true),
    )
    private val byKey = all.associateBy { it.key }

    /** The type for [key]; a type this app doesn't know (a newer server) is shown read-only as text. */
    fun of(key: String): FieldType = byKey[key] ?: FieldType(key, Kind.SYSTEM)
}
