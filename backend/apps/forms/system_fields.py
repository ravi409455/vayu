"""Locked system fields per form type (REQUIREMENTS §3, §11). The system relies on these keys for
search, tap-to-call, filters and dashboards; admins can relabel or move them, never remove them."""

PAID = {"==": [{"var": "end.taking_payment"}, True]}

SYSTEM_FIELDS: dict[str, list[dict]] = {
    "booking": [
        {"key": "booking_id", "label": "Booking ID", "type": "short_text", "required": True},
        {"key": "customer_name", "label": "Customer name", "type": "short_text",
         "required": True},
        {"key": "customer_phone", "label": "Customer phone", "type": "phone", "required": True},
        {"key": "address", "label": "Address", "type": "long_text", "required": True},
        {"key": "city", "label": "City", "type": "master_list", "config": {"list": "city"},
         "required": True},
        {"key": "inspection_date", "label": "Date", "type": "date", "required": True},
        {"key": "inspection_time", "label": "Time", "type": "time", "required": True},
        {"key": "inspection_type", "label": "Inspection type", "type": "form_choice",
         "required": True},
        {"key": "car_make_model", "label": "Car make/model", "type": "master_list",
         "config": {"list": "car_make_model"}, "required": True},
        {"key": "lead_owner", "label": "Lead owner", "type": "user_picker",
         "config": {"role": "ops"}},
        {"key": "assigned_expert", "label": "Assigned expert", "type": "user_picker",
         "config": {"role": "expert"}},
    ],
    "custom": [
        {"key": "chassis_no", "label": "Chassis number", "type": "short_text", "required": True},
    ],
    # the check-in the expert does before the inspection
    "start": [
        {"section": "Check-in",
         "key": "checkin_gps", "label": "Your location", "type": "gps", "config": {"auto": True}},
        {"section": "Check-in",
         "key": "checkin_time", "label": "Date and time", "type": "datetime",
         "config": {"auto": True}},
        {"section": "Check-in",
         "key": "selfie", "label": "Selfie at the car", "type": "photo", "required": True,
         "config": {"max_count": 1, "capture": "camera"}},
    ],
    # the wrap-up (payment) after it
    "end": [
        {"section": "Payment",
         "key": "taking_payment", "label": "Taking payment?", "type": "yes_no", "required": True},
        {"section": "Payment",
         "key": "payment_mode", "label": "Payment mode", "type": "single_choice",
         "config": {"options": [{"key": "cash", "label": "Cash"}, {"key": "upi", "label": "UPI"},
                                {"key": "card", "label": "Card"},
                                {"key": "bank_transfer", "label": "Bank transfer"},
                                {"key": "cheque", "label": "Cheque"}]},
         "required_if": PAID, "show_if": PAID},
        {"section": "Payment",
         "key": "payment_amount", "label": "Amount", "type": "currency",
         "required_if": PAID, "show_if": PAID},
        {"section": "Payment",
         "key": "payment_screenshot", "label": "Payment screenshot", "type": "photo",
         "config": {"max_count": 1}, "required_if": PAID, "show_if": PAID},
    ],
}

# the one page each of these forms starts with
PAGE_TITLE = {"booking": "Page 1", "custom": "Page 1", "start": "Check-in", "end": "Wrap-up"}
