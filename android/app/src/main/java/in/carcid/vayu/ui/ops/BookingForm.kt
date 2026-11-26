package `in`.carcid.vayu.ui.ops



import `in`.carcid.vayu.core.ops.ListItem
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.layout.positionInParent
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.api.answerErrors
import `in`.carcid.vayu.core.forms.answerProblem
import `in`.carcid.vayu.core.forms.refusalText
import `in`.carcid.vayu.core.forms.Filled
import `in`.carcid.vayu.core.forms.FormTree
import `in`.carcid.vayu.core.ops.a
import `in`.carcid.vayu.core.ops.o
import `in`.carcid.vayu.core.ops.rows
import `in`.carcid.vayu.core.s
import `in`.carcid.vayu.core.rules.JsonLogic
import `in`.carcid.vayu.ui.components.PrimaryButton
import `in`.carcid.vayu.ui.components.SoftButton
import `in`.carcid.vayu.ui.expert.Question
import `in`.carcid.vayu.ui.theme.Vayu
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** New booking or edit: the booking form as the Admin built it. */
@Composable
fun BookingFormScreen(env: OpsEnv, id: String?, onBack: () -> Unit, onSaved: (String, Boolean) -> Unit) {
    val scope = rememberCoroutineScope()
    val forms = rememberLoad(env, "forms").value?.data?.rows().orEmpty()
    val version = forms.firstOrNull { it.s("type") == "booking" && it.s("is_active") != "false" }?.o("published_version")?.int("id")
    val tree = rememberLoad(env, version?.let { "form-versions/$it" }).value?.data?.let { FormTree.parse(it as JsonObject) }
    val existing = id?.let { rememberLoad(env, "bookings/$it").value?.data?.let { d -> Bk(d as JsonObject) } }
    val listKeys = tree?.fields?.filter { it.type == "master_list" }?.mapNotNull { it.config["list"] as? String }?.distinct().orEmpty()
    val lists = listKeys.associateWith { k -> ListItem.list(rememberLoad(env, "master-lists/$k/items").value?.data?.rows().orEmpty()).filter { !it.archived }.map { it.key to it.label } }
    @Suppress("UNCHECKED_CAST")
    var values by remember(existing?.rowVersion) { mutableStateOf((existing?.answers?.let { JsonLogic.fromJson(it) } as? Map<String, Any?>).orEmpty()) }
    var changed by remember(existing?.rowVersion) { mutableStateOf(setOf<String>()) }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var busy by remember { mutableStateOf(false) }
    val scroll = rememberScrollState()
    val where = remember { mutableMapOf<String, Int>() }
    var refused by remember { mutableStateOf(0) }
    BackHandler(onBack = onBack)
    fun save(assign: Boolean) {
        busy = true
        val body = if (id == null) buildJsonObject { put("answers", JsonLogic.toJson(values)) }
            else buildJsonObject { put("row_version", existing!!.rowVersion); put("answers", JsonLogic.toJson(values.filterKeys { it in changed })) }
        env.actions.send(if (id == null) "POST" else "PATCH", if (id == null) "bookings" else "bookings/$id", body, "Saved.", refused = { e ->
            errors = e.answerErrors().mapValues { it.value.ifBlank { "Check this." } }
            if (e.code == "DUPLICATE_BOOKING_ID") errors = errors + ("booking_id" to e.message)
            refused++
            if (e.code.startsWith("STALE")) { env.refresh(); env.say("Someone else saved this booking meanwhile; their version is loaded.") }
            else if (errors.isEmpty()) env.say(e.message)
            busy = false
        }) { r -> busy = false; onSaved((r as? JsonObject)?.s("id").orEmpty(), assign) }
    }
    Column(Modifier.fillMaxSize().background(Vayu.colors.bg)) {
        SubHeader(if (id == null) "New booking" else "Edit booking", existing?.code, onBack)
        if (tree == null) { Text("Loading the booking form…", color = Vayu.colors.muted, modifier = Modifier.padding(20.dp)); return }
        // the booking form's own answers are "booking" in its rules
        val filled = Filled(mapOf("booking" to tree), emptyMap(), values, env.today().toString())
        // after a refused save: say so and bring the first marked question into view
        LaunchedEffect(refused) {
            if (refused == 0 || errors.isEmpty()) return@LaunchedEffect
            env.say(if (errors.size == 1) "Fix the question marked in red." else "Fix the ${errors.size} questions marked in red.")
            errors.keys.mapNotNull { where[it] }.minOrNull()?.let { scroll.animateScrollTo(it) }
        }
        Column(Modifier.weight(1f).verticalScroll(scroll).padding(horizontal = 20.dp)) {
            val fe = opsFieldEnv(env, lists)
            val shown = tree.pages.flatMap { it.sections }.map { s ->
                s to s.fields.filter { it.answerable && filled.visible("booking", it.key) && it.key != "assigned_expert" && !(id != null && it.key == "inspection_type") }
            }.filter { it.second.isNotEmpty() }
            shown.forEach { (s, fs) ->
                // a lone section needs no heading ("Section 1")
                if (shown.size > 1) Section(s.title)
                fs.forEach { f ->
                    Box(Modifier.onGloballyPositioned { where[f.key] = it.positionInParent().y.toInt() }) {
                        Question(f, values[f.key], filled.required("booking", f.key), false,
                            errors[f.key]?.let { refusalText(it) } ?: answerProblem(f, values[f.key]) ?: filled.checkMessage("booking", f.key), false, fe) { v ->
                            values = values + (f.key to v); changed = changed + f.key; errors = errors - f.key
                        }
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
        }
        Row(Modifier.padding(horizontal = 20.dp, vertical = 14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            when {
                id != null -> PrimaryButton(if (busy) "Saving…" else "Save changes", { save(false) }, Modifier.weight(1f), enabled = !busy && changed.isNotEmpty())
                env.can("bookings.assign") -> {
                    SoftButton("Save", { save(false) }, Modifier.weight(1f))
                    PrimaryButton(if (busy) "Saving…" else "Save and assign", { save(true) }, Modifier.weight(1f), enabled = !busy)
                }
                else -> PrimaryButton(if (busy) "Saving…" else "Save", { save(false) }, Modifier.weight(1f), enabled = !busy)
            }
        }
    }
}
