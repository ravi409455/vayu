from rest_framework import serializers

from apps.forms.access import levels_for, visible_answers

from .models import Booking, RescheduleLog


class RescheduleSerializer(serializers.ModelSerializer):
    by = serializers.CharField(source="by.username")

    class Meta:
        model = RescheduleLog
        fields = ["old_date", "old_time", "new_date", "new_time", "reason", "by", "at"]


class BookingSerializer(serializers.ModelSerializer):
    last_edited_by = serializers.CharField(source="last_edited_by.username", default=None)
    released_by = serializers.CharField(source="released_by.username", default=None)
    reschedules = RescheduleSerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = ["id", "booking_id", "stage", "ops_status", "inspection_type", "assigned_expert",
                  "answers", "row_version", "started_at", "cancel_reason", "released_by",
                  "released_draft_expected", "last_edited_by", "last_edited_at", "reschedules",
                  "created_at"]


    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None:
            cache = self.context.setdefault("_levels", {})
            role = request.user.role
            if "version" not in cache:
                from .services import booking_form_version

                cache["version"] = booking_form_version()
            key = (role, instance.stage)
            if key not in cache:
                cache[key] = levels_for(cache["version"], role, instance.stage)
            data["answers"] = visible_answers(cache[key], data["answers"], role)
        return data
