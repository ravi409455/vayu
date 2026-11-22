from rest_framework import serializers

from apps.forms.access import levels_for, visible_answers

from .models import Booking, Inspection, RescheduleLog


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


class InspectionSerializer(serializers.ModelSerializer):
    last_edited_by = serializers.CharField(source="last_edited_by.username", default=None)
    form_version = serializers.IntegerField(source="form_version_id")
    booking = serializers.UUIDField(source="booking_id")

    class Meta:
        model = Inspection
        fields = ["id", "booking", "expert", "status", "answers", "row_version", "form_version",
                  "submitted_at", "last_edited_by", "last_edited_at", "created_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None:
            from .submissions import ops_version

            role, stage = request.user.role, instance.booking.stage
            ov = ops_version()
            for part, version in (("inspection", instance.form_version), ("ops", ov)):
                if part not in data["answers"]:
                    continue
                if version is not None:
                    data["answers"][part] = visible_answers(
                        levels_for(version, role, stage), data["answers"][part], role)
                elif role != "admin":   # no form to say what is visible: fail closed
                    del data["answers"][part]
        return data
