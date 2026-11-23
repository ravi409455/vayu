from rest_framework import serializers

from apps.forms.access import hidden_inspection_forms, levels_for, visible_answers

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
                  "created_at", "conflict", "alerts", "withdrawn_expert"]


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
    start_version = serializers.IntegerField(source="start_version_id", allow_null=True)
    end_version = serializers.IntegerField(source="end_version_id", allow_null=True)
    booking = serializers.UUIDField(source="booking_id")

    class Meta:
        model = Inspection
        fields = ["id", "booking", "expert", "status", "answers", "scores", "overrides",
                  "row_version", "form_version", "start_version", "end_version", "submitted_at",
                  "last_edited_by",
                  "last_edited_at", "created_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None:
            role, stage = request.user.role, instance.booking.stage
            hidden = self.context.setdefault("_hidden_forms", hidden_inspection_forms(request.user))
            if instance.form_version.form_id in hidden:        # not theirs to see
                data["answers"], data["scores"], data["overrides"] = {}, None, None
                return data
            if role == "expert":                       # experts never see ratings or Key Checks
                data.pop("scores", None)
                data.pop("overrides", None)
            if "scores" in data and role != "admin":
                self._hide_scores(data["scores"], instance, role, stage)
            for part, version in instance.pinned().items():
                if part not in data["answers"]:
                    continue
                if version is not None:
                    data["answers"][part] = visible_answers(
                        levels_for(version, role, stage), data["answers"][part], role)
                elif role != "admin":   # no form to say what is visible: fail closed
                    del data["answers"][part]
        return data

    @staticmethod
    def _hide_scores(scores: dict, instance, role: str, stage: str) -> None:
        """Key Checks and rating fields follow the same field access as answers."""
        levels = levels_for(instance.form_version, role, stage)

        def shown(key: str) -> bool:
            return levels.get(key, "hidden") != "hidden"

        for group in ("derived", "fields"):
            scores[group] = {k: v for k, v in scores.get(group, {}).items() if shown(k)}
        scores["defects"] = [d for d in scores.get("defects", [])
                             if shown(d.split(".", 1)[-1])]
