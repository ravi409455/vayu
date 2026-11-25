package `in`.carcid.vayu.core.forms

import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

class FieldTypesTest {
    /** The phone knows exactly the server's field types (backend/apps/forms/models.py FieldType). */
    @Test fun everyServerTypeIsInTheRegistry() {
        val models = File("../../backend/apps/forms/models.py").readText()
        val block = models.substringAfter("class FieldType(models.TextChoices):").substringBefore("\nclass ")
        val server = Regex("=\\s*\"([a-z_]+)\"").findAll(block).map { it.groupValues[1] }.toSet()
        assertEquals(server, FieldTypes.all.map { it.key }.toSet())
    }

    @Test fun mediaAndSystemTypesAreMarked() {
        assertEquals(setOf("photo", "video", "file", "signature"), FieldTypes.all.filter { it.media }.map { it.key }.toSet())
        assertEquals(setOf("derived", "rating"), FieldTypes.all.filter { it.systemMade }.map { it.key }.toSet())
        assertEquals(false, FieldTypes.of("image").answerable)
        assertEquals(Kind.SYSTEM, FieldTypes.of("something_new").kind)
    }
}
