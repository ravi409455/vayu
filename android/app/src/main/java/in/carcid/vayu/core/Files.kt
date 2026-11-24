package `in`.carcid.vayu.core

import java.io.File
import java.io.FileOutputStream

/** Write [bytes] so a crash or power cut leaves either the old file or the new one, never half. */
fun writeAtomically(file: File, bytes: ByteArray) {
    file.parentFile?.mkdirs()
    // a temp file of its own: two saves of the same file at once must not share one
    val tmp = File(file.path + "." + java.util.UUID.randomUUID() + ".tmp")
    FileOutputStream(tmp).use { it.write(bytes); it.fd.sync() }
    check(tmp.renameTo(file)) { "Could not save ${file.name}." }
}
