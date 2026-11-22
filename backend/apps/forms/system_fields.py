"""Locked system fields per form kind (REQUIREMENTS §3, §11). The system relies on these keys for
search, tap-to-call, filters and dashboards; admins can relabel or move them, never remove them."""

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
        {"key": "inspection_type", "label": "Inspection type", "type": "master_list",
         "config": {"list": "inspection_type"}, "required": True},
        {"key": "car_make_model", "label": "Car make/model", "type": "master_list",
         "config": {"list": "car_make_model"}, "required": True},
        {"key": "lead_owner", "label": "Lead owner", "type": "user_picker",
         "config": {"role": "ops"}},
        {"key": "assigned_expert", "label": "Assigned expert", "type": "user_picker",
         "config": {"role": "expert"}},
    ],
    "inspection": [
        {"key": "chassis_no", "label": "Chassis number", "type": "short_text", "required": True},
    ],
    "ops": [],
}
