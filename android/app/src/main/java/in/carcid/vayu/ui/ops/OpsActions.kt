package `in`.carcid.vayu.ui.ops

import `in`.carcid.vayu.core.api.ApiError
import `in`.carcid.vayu.core.ops.OpsData
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/**
 * Ops' changes (assign, reschedule, save answers, regenerate…), run in OpsModel's scope instead of
 * the screen's (F-018): leaving the screen mid-send no longer cancels the change. On success it says
 * [done] (if any), reloads the screens and calls ok with the reply; a refusal goes to refused
 * (by default the server's words).
 */
class OpsActions(private val data: OpsData, private val scope: CoroutineScope,
                 private val refresh: () -> Unit, private val say: (String) -> Unit) {
    fun send(method: String, path: String, body: JsonObject? = null, done: String? = null,
             refused: (ApiError) -> Unit = { say(it.message) }, ok: (JsonElement) -> Unit = {}): Job = scope.launch {
        try {
            val r = data.act(method, path, body)
            done?.let(say); refresh(); ok(r)
        } catch (e: ApiError) { refused(e) }
    }
}
