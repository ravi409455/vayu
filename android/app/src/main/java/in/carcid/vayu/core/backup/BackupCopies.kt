package `in`.carcid.vayu.core.backup

import `in`.carcid.vayu.core.writeAtomically
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File

/**
 * A copy of every photo, video, document and signature an expert takes, outside the app, in
 * `Documents/Vayu/<booking code>/` (docs/plan-media-backup.md part B). It survives an uninstall, so
 * the expert can still send the files to Ops by hand. Hidden from the Gallery (`.nomedia`).
 *
 * [index] (in the app's own storage) lists the copies this install made. A file in [folder] that
 * isn't on it was left by an earlier install ("found"). Clean-up: a copy the server still needs is
 * never deleted; one it has goes when it is [KEEP_MS] old; one it will never take goes [KEEP_MS]
 * after the phone learns that; a found one [KEEP_MS] after it was found.
 */
class BackupCopies(
    private val folder: File,
    private val index: File,
    private val clock: () -> Long,
    /** "All files access" is on (without it nothing outside the app can be written). */
    private val canWrite: () -> Boolean,
    /** Free bytes where [folder] lives. */
    // ponytail: usableSpace leaves out cache Android could clear; fine for "skip the copy", use
    // StorageManager.getAllocatableBytes if copies are skipped while the phone has room
    @Suppress("UsableSpace") private val freeBytes: () -> Long = { folder.parentFile?.usableSpace ?: 0L },
) {
    data class Copy(val bookingId: String, val code: String, val fileId: String, val page: String, val label: String,
                    /** Picks the file's ending (a picked document's own file has none that means anything). */
                    val contentType: String = "")

    enum class Result { COPIED, NO_ACCESS, PHONE_FULL, FAILED }

    /** What the server thinks of one file, from the drafts on this phone. */
    enum class State { WAITING, DONE, NEVER }

    /** Copies left by an earlier install: the leads, how many files, and when they are deleted. */
    data class Found(val codes: List<String>, val files: Int, val deleteAt: Long)

    @Serializable
    private data class Entry(val path: String, val bookingId: String = "", val fileId: String = "",
                             val madeAt: Long = 0, val doneAt: Long? = null, val neverAt: Long? = null,
                             /** Not made by this install: when it was found. */
                             val foundAt: Long? = null)

    private val json = Json { ignoreUnknownKeys = true }
    private var entries: List<Entry> = runCatching { json.decodeFromString<List<Entry>>(index.readText()) }.getOrDefault(emptyList())
    private val _found = MutableStateFlow<Found?>(null)
    val found: StateFlow<Found?> = _found
    /** How the last copy went (null: none yet); the inspection says when a copy was skipped. */
    val lastCopy = MutableStateFlow<Result?>(null)

    private fun save() = writeAtomically(index, json.encodeToString(entries).toByteArray())

    /** Copy [src] for [c]. Never throws: a failed copy must not stop the inspection. */
    @Synchronized fun copy(c: Copy, src: File): Result = copyOnce(c, src).also { lastCopy.value = it }

    private fun copyOnce(c: Copy, src: File): Result {
        if (!canWrite()) return Result.NO_ACCESS
        // room for the copy and some to spare, so the phone isn't filled to the last byte
        if (freeBytes() < src.length() * 2 + MIN_FREE) return Result.PHONE_FULL
        return runCatching {
            folder.mkdirs()
            folder.resolve(".nomedia").takeIf { !it.exists() }?.createNewFile()
            val dir = folder.resolve(clean(c.code).ifBlank { "lead" }).apply { mkdirs() }
            val target = unused(dir, clean("${c.page} - ${c.label}").ifBlank { "file" }, ending(c.contentType, src))
            // written under a hidden name, listed, then renamed: a power cut never leaves a half file
            // that looks real, and clean-up never takes a copy in the making for a found one
            val part = dir.resolve(".${target.name}.part")
            src.copyTo(part, overwrite = true)
            entries = entries + Entry(target.path, c.bookingId, c.fileId, madeAt = clock())
            save()
            check(part.renameTo(target)) { "rename failed" }
            Result.COPIED
        }.getOrElse { Result.FAILED }
    }

    /** A photo was removed or replaced: its copy goes at once. */
    @Synchronized fun drop(fileId: String) = remove { it.fileId == fileId }

    /** The expert sent the copies from an earlier install to Ops: they go at once, with the notice. */
    @Synchronized fun dropFound() { remove { it.foundAt != null }; _found.value = null }

    /** A lead was discarded: all its copies go at once. */
    @Synchronized fun dropBooking(bookingId: String) = remove { it.bookingId == bookingId }

    /**
     * Apply the clean-up rules. [files]: every file id the drafts on this phone hold, with what the
     * server thinks of it. [sure]: false while some draft can't be read (it may hold more files):
     * then a copy whose draft is gone is kept.
     */
    @Synchronized fun clean(files: Map<String, State>, sure: Boolean = true) {
        // without access the folder can't be listed (nothing is "found" or taken as gone), but this
        // install's own copies that are due are still deleted: the keep rules never fail open
        val access = canWrite()
        val now = clock()
        val known = entries.map { it.path }.toSet()
        val newlyFound = if (!access) emptyList() else folder.listFiles().orEmpty().filter { it.isDirectory }.flatMap { d ->
            d.listFiles().orEmpty().filter { it.isFile && !it.name.startsWith(".") && it.path !in known }
        }.map { Entry(it.path, foundAt = now) }
        entries = (entries + newlyFound).mapNotNull { e ->
            val state = files[e.fileId]
            val updated = when {
                e.foundAt != null -> e
                state == State.DONE && e.doneAt == null -> e.copy(doneAt = now)
                state == State.NEVER && e.neverAt == null -> e.copy(neverAt = now)
                else -> e
            }
            val goes = when {
                access && !File(e.path).exists() -> true
                updated.foundAt != null -> now - updated.foundAt >= KEEP_MS
                state == State.WAITING -> false
                state == State.DONE -> now - updated.madeAt >= KEEP_MS
                state == State.NEVER -> now - updated.neverAt!! >= KEEP_MS
                // its draft is gone: discarded (delete), or sent and cleared (the 2-day rule)
                !sure -> false
                updated.doneAt != null -> now - updated.madeAt >= KEEP_MS
                updated.neverAt != null -> now - updated.neverAt >= KEEP_MS
                else -> true
            }
            // a copy that couldn't be deleted stays listed, and is tried again next time
            if (goes && gone(e.path, access)) null else updated
        }
        save()
        removeEmptyFolders()
        _found.value = entries.filter { it.foundAt != null }.takeIf { it.isNotEmpty() }?.let { f ->
            Found(f.map { File(it.path).parentFile!!.name }.distinct().sorted(), f.size, f.minOf { it.foundAt!! } + KEEP_MS)
        }
    }

    private fun remove(match: (Entry) -> Boolean) {
        val (gone, kept) = entries.partition(match)
        if (gone.isEmpty()) return
        entries = kept + gone.filterNot { gone(it.path, canWrite()) }
        save()
        removeEmptyFolders()
    }

    /** Delete [path]; true when it is gone (a file that can't even be seen counts only with access). */
    private fun gone(path: String, access: Boolean): Boolean { val f = File(path); return f.delete() || (access && !f.exists()) }

    private fun removeEmptyFolders() =
        folder.listFiles().orEmpty().filter { it.isDirectory && it.list().isNullOrEmpty() }.forEach { it.delete() }

    private fun unused(dir: File, base: String, ext: String): File {
        val dot = if (ext.isBlank()) "" else ".$ext"
        return generateSequence(1) { it + 1 }.map { n -> dir.resolve(if (n == 1) "$base$dot" else "$base ($n)$dot") }
            .first { !it.exists() }
    }

    companion object {
        /** The usual ending for [type], so the copy opens in the right app; else [src]'s own. */
        fun ending(type: String, src: File): String {
            val t = type.substringBefore(';').trim().lowercase()
            return ENDINGS[t] ?: runCatching { android.webkit.MimeTypeMap.getSingleton().getExtensionFromMimeType(t) }.getOrNull()
                ?: src.extension
        }

        /** What experts take most; anything else asks Android. */
        private val ENDINGS = mapOf("image/jpeg" to "jpg", "image/png" to "png", "image/webp" to "webp", "image/heic" to "heic",
            "video/mp4" to "mp4", "application/pdf" to "pdf")
        /** How long a copy stays once the server has it (or never will), and a found one. */
        const val KEEP_MS = 2 * 24 * 60 * 60 * 1000L
        private const val MIN_FREE = 200L * 1024 * 1024

        /** A file or folder name anyone can open: no path or reserved characters, no emoji, not hidden. */
        fun clean(name: String): String =
            name.replace(Regex("""\s*[^\p{L}\p{N} _()&,'+.-]+\s*"""), " - ")
                .replace(Regex("""\s+"""), " ").replace(Regex("""-( -)+"""), "-").trim(' ', '.', '-').take(80).trim(' ', '.', '-')
    }
}
