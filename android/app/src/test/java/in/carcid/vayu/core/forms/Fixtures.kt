package `in`.carcid.vayu.core.forms

/**
 * A small but complete inspection, shaped like the API's form trees: a check-in (version 1), the
 * custom form (version 7) and the wrap-up (version 9). Used by the store, outbox and screen tests.
 */
object Fixtures {
    private fun field(key: String, label: String, type: String, extra: String = "", config: String = "{}") =
        """{"key":"$key","label":"$label","type":"$type","helper_text":"","required":${extra.contains("\"req\"")},
            "visible":true,"level":"edit","config":$config${extra.replace("\"req\"", "\"r\":1")}}"""

    private const val OK4 = """{"options":[{"key":"ok","label":"OK"},{"key":"minor","label":"Minor","is_defect":true,"severity":"minor"},
        {"key":"major","label":"Major","is_defect":true,"severity":"major"},{"key":"critical","label":"Critical","is_defect":true,"severity":"critical"}]}"""

    val START = """{"id":1,"checks":[],"pages":[{"id":11,"title":"Check-in","visible":true,"gate":false,"sections":[
        {"id":111,"title":"Check-in","visible":true,"fields":[
          ${field("checkin_gps", "Your location", "gps", config = """{"auto":true}""")},
          ${field("checkin_time", "Date and time", "datetime", config = """{"auto":true}""")},
          ${field("travel", "How did you travel?", "single_choice", ""","req"""", """{"options":[{"key":"bike","label":"Bike"},{"key":"car","label":"Car"},{"key":"bus","label":"Bus / auto"}]}""")}
        ]}]}]}"""

    val INSPECTION = """{"id":7,"checks":[],"pages":[
      {"id":21,"title":"Vehicle","visible":true,"gate":true,"sections":[{"id":211,"title":"Identity","visible":true,"fields":[
        ${field("chassis_no", "Chassis number", "short_text", ""","req"""", """{"scan":true}""")},
        ${field("odometer", "Odometer", "number", ""","req"""", """{"unit":"km"}""")}
      ]}]},
      {"id":22,"title":"Exterior","visible":true,"gate":false,"sections":[{"id":221,"title":"Body","visible":true,"fields":[
        ${field("bonnet", "Bonnet", "single_choice", ""","req"""", OK4)},
        ${field("door", "Front left door", "single_choice", ""","req"""", OK4)},
        ${field("door_photos", "Door photos", "photo", ""","req","show_if":{"in":[{"var":"inspection.door"},["minor","major","critical"]]}""", """{"max_count":4}""")},
        ${field("paint", "Paint condition", "single_choice", "", """{"options":[{"key":"orig","label":"Original paint"},
            {"key":"repaint","label":"Repainted","is_defect":true,"severity":"minor"},
            {"key":"mismatch","label":"Repainted, colour does not match the rest of the car","is_defect":true,"severity":"major"},
            {"key":"putty","label":"Putty or filler work visible","is_defect":true,"severity":"major"},
            {"key":"rust","label":"Rust through the paint","is_defect":true,"severity":"critical"},
            {"key":"replaced","label":"Panel replaced","is_defect":true,"severity":"major"},
            {"key":"na","label":"Could not check"}]}""")},
        ${field("tyre", "Tyre brand", "single_choice", "", """{"options":[${listOf("Apollo","Bridgestone","CEAT","Continental","Goodyear","JK Tyre","Michelin","MRF","Pirelli","Yokohama").joinToString(",") { """{"key":"${it.lowercase().replace(" ", "_")}","label":"$it"}""" }}]}""")},
        ${field("scratches", "Scratches found on", "multi_choice", "", """{"options":[{"key":"fb","label":"Front bumper"},{"key":"rb","label":"Rear bumper"},{"key":"roof","label":"Roof"},{"key":"boot","label":"Boot"}]}""")},
        ${field("seal", "Key Check", "derived", "", """{"rule":{"!!":[{"var":"inspection.chassis_no"}]}}""")}
      ]}]}]}"""

    val END = """{"id":9,"checks":[],"pages":[{"id":31,"title":"Wrap-up","visible":true,"gate":false,"sections":[{"id":311,"title":"Payment","visible":true,"fields":[
        ${field("taking_payment", "Taking payment?", "yes_no", ""","req"""")},
        ${field("payment_amount", "Amount", "currency", ""","required_if":{"==":[{"var":"end.taking_payment"},true]},"show_if":{"==":[{"var":"end.taking_payment"},true]}""")}
      ]}]}]}"""

    /** The three forms as the sync download carries them. */
    val FORMS = """{"1":$START,"7":$INSPECTION,"9":$END}"""
}
