from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import perm, scope_for

from . import services
from .models import Booking
from .serializers import BookingSerializer

ACTION_PERMISSIONS = {
    "list": "bookings.view", "retrieve": "bookings.view", "create": "bookings.create",
    "partial_update": "bookings.edit", "change_type": "bookings.edit",
    "assign": "bookings.assign", "reschedule": "bookings.reschedule", "cancel": "bookings.cancel",
    "force_release": "bookings.force_release", "destroy": "bookings.delete",
}


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = BookingSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    declared_permissions = tuple(sorted(set(ACTION_PERMISSIONS.values())))

    def get_permissions(self):
        key = ACTION_PERMISSIONS.get(self.action)
        return [perm(key)()] if key else [perm("bookings.view")()]

    def get_queryset(self):
        qs = Booking.objects.select_related("last_edited_by", "released_by").prefetch_related(
            "reschedules__by")
        key = ACTION_PERMISSIONS.get(self.action, "bookings.view")
        if key in ("bookings.view", "bookings.edit") and \
                scope_for(self.request.user, key, self.request) == "own":
            qs = qs.filter(assigned_expert_id=self.request.user.pk)
        return qs

    def create(self, request, *args, **kwargs):
        b = services.create(request.user, request.data.get("answers") or {})
        return Response(self.get_serializer(b).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        if "row_version" not in request.data:
            raise ValidationError({"row_version": "This field is required."})
        b = services.edit(request.user, self.get_object(), request.data.get("answers") or {},
                          request.data["row_version"])
        return Response(self.get_serializer(b).data)

    def destroy(self, request, *args, **kwargs):
        services.delete(request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _out(self, b):
        return Response(self.get_serializer(Booking.objects.get(pk=b.pk)).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        return self._out(services.assign(request.user, self.get_object(),
                                         request.data.get("expert")))

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        d = request.data
        return self._out(services.reschedule(request.user, self.get_object(), d.get("date"),
                                             d.get("time"), d.get("reason")))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._out(services.cancel(request.user, self.get_object(),
                                         request.data.get("reason")))

    @action(detail=True, methods=["post"], url_path="force-release")
    def force_release(self, request, pk=None):
        return self._out(services.force_release(request.user, self.get_object()))

    @action(detail=True, methods=["post"], url_path="change-type")
    def change_type(self, request, pk=None):
        return self._out(services.change_type(request.user, self.get_object(),
                                              request.data.get("inspection_type")))
