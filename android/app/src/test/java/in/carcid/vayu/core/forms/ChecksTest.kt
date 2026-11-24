package `in`.carcid.vayu.core.forms

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

/** The phone refuses what the server would refuse (forms/fieldtypes.py), before Submit. */
class ChecksTest {
    private fun f(type: String, config: Map<String, Any?> = emptyMap()) = Field("k", "K", type, "", false, null, null, true, "edit", config)

    @Test fun phonesAreTenDigitIndianMobiles() {
        assertEquals("+919876500014", indianMobile("98765 00014"))
        assertEquals("+919876500014", indianMobile("+91 98765-00014"))
        assertEquals("+919876500014", indianMobile("09876500014"))
        assertNull(indianMobile("87910593860784"))                 // 14 digits: the one that was refused
        assertNull(indianMobile("5876500014"))                     // mobiles start with 6 to 9
        assertNotNull(answerProblem(f("phone"), "87910593860784"))
        assertNull(answerProblem(f("phone"), "9876500014"))
    }

    @Test fun numbersKeepTheirRangeAndDecimals() {
        val km = f("number", mapOf("min" to 0.0, "max" to 999999.0))
        assertNull(answerProblem(km, 12400.0))
        assertEquals("Must be between 0 and 999999.", answerProblem(km, -1.0))
        assertEquals("Enter a whole number.", answerProblem(km, 12.5))
        assertNull(answerProblem(f("number", mapOf("decimals" to 1.0)), 12.5))
        assertNull(answerProblem(f("currency"), 1500.5))
        assertNotNull(answerProblem(f("currency"), 1.555))
        assertEquals("Enter a number.", answerProblem(km, "12a"))
    }

    @Test fun textKeepsItsLengthAndFormat() {
        assertNotNull(answerProblem(f("short_text"), "x".repeat(201)))
        val vin = f("short_text", mapOf("pattern" to "[A-HJ-NPR-Z0-9]{17}", "pattern_message" to "17 letters and digits, no I, O or Q."))
        assertEquals("17 letters and digits, no I, O or Q.", answerProblem(vin, "SHORT"))
        assertNull(answerProblem(vin, "MA3YPKCSKTJ273129"))
        assertNull(answerProblem(f("short_text"), null))            // empty is "needed", not wrong
    }

    @Test fun refusalsReadAsWords() {
        assertEquals("Enter a 10-digit Indian mobile number.", refusalText("INVALID_PHONE"))
        assertEquals("Check this answer.", refusalText("SOMETHING_NEW"))
    }
}
