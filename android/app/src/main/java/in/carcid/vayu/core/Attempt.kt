package `in`.carcid.vayu.core

import kotlin.coroutines.cancellation.CancellationException

/**
 * runCatching for suspend calls: a failure becomes a Result, but a cancelled coroutine stays
 * cancelled (runCatching would swallow the CancellationException and carry on).
 */
inline fun <T> attempt(block: () -> T): Result<T> = try {
    Result.success(block())
} catch (e: CancellationException) {
    throw e
} catch (e: Exception) {
    Result.failure(e)
}
