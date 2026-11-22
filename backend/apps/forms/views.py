from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts import audit
from apps.accounts.permissions import AnyReadAdminWrite, IsAdmin, OpsReadAdminWrite

from . import services
from .models import Field, Form, FormVersion, MasterList, MasterListItem, Page, Section
from .serializers import (
    FieldSerializer,
    FormSerializer,
    MasterListItemSerializer,
    MasterListSerializer,
    PageSerializer,
    SectionSerializer,
    VersionTreeSerializer,
)


def _next_order(qs) -> int:
    return (qs.aggregate(m=Max("order"))["m"] or 0) + 1


class MasterListViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.CreateModelMixin, mixins.UpdateModelMixin,
                        viewsets.GenericViewSet):
    queryset = MasterList.objects.order_by("key")
    serializer_class = MasterListSerializer
    permission_classes = [AnyReadAdminWrite]
    lookup_field = "key"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        obj = serializer.save()
        audit.record(self.request.user, "master_list.create", "master_list", obj.id, obj.key)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit.record(self.request.user, "master_list.update", "master_list", obj.id, obj.key)

    @action(detail=True, methods=["get", "post"])
    def items(self, request, key=None):
        lst = self.get_object()
        if request.method == "GET":
            qs = lst.items.all()
            if not request.query_params.get("include_archived"):
                qs = qs.filter(archived=False)
            return Response(MasterListItemSerializer(qs, many=True).data)
        s = MasterListItemSerializer(data=request.data, context={"list": lst})
        s.is_valid(raise_exception=True)
        item = s.save(list=lst)
        audit.record(request.user, "master_list.item_create", "master_list_item", item.id,
                     f"{lst.key}.{item.key}")
        return Response(s.data, status=status.HTTP_201_CREATED)


class MasterListItemViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = MasterListItem.objects.select_related("list")
    serializer_class = MasterListItemSerializer
    permission_classes = [IsAdmin]
    http_method_names = ["patch", "head", "options"]

    def perform_update(self, serializer):
        item = serializer.save()
        audit.record(self.request.user, "master_list.item_update", "master_list_item", item.id,
                     f"{item.list.key}.{item.key}")


class FormViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Form.objects.order_by("kind", "key")
    serializer_class = FormSerializer
    permission_classes = [OpsReadAdminWrite]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        form = services.create_form(request.user, key=d["key"], kind=d["kind"], name=d["name"])
        return Response(self.get_serializer(form).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def drafts(self, request, pk=None):
        draft = services.create_draft(request.user, self.get_object())
        return Response({"id": draft.id, "number": draft.number}, status=status.HTTP_201_CREATED)


class VersionDetail(generics.RetrieveAPIView):
    queryset = FormVersion.objects.all()
    serializer_class = VersionTreeSerializer
    permission_classes = [OpsReadAdminWrite]


class PageCreate(generics.CreateAPIView):
    serializer_class = PageSerializer
    permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        version = get_object_or_404(FormVersion, pk=self.kwargs["pk"])
        order = serializer.validated_data.get("order", _next_order(Page.objects.filter(
            version=version)))
        serializer.save(version=version, order=order)


class PageDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Page.objects.all()
    serializer_class = PageSerializer
    permission_classes = [OpsReadAdminWrite]
    http_method_names = ["get", "patch", "delete", "head", "options"]


class SectionCreate(generics.CreateAPIView):
    serializer_class = SectionSerializer
    permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        page = get_object_or_404(Page, pk=self.kwargs["pk"])
        order = serializer.validated_data.get("order", _next_order(page.sections.all()))
        serializer.save(page=page, version_id=page.version_id, order=order)


class SectionDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Section.objects.all()
    serializer_class = SectionSerializer
    permission_classes = [OpsReadAdminWrite]
    http_method_names = ["get", "patch", "delete", "head", "options"]


class FieldCreate(generics.CreateAPIView):
    serializer_class = FieldSerializer
    permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        section = get_object_or_404(Section, pk=self.kwargs["pk"])
        order = serializer.validated_data.get("order", _next_order(section.fields.all()))
        serializer.save(section=section, version_id=section.version_id, order=order)


class FieldDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Field.objects.select_related("section")
    serializer_class = FieldSerializer
    permission_classes = [OpsReadAdminWrite]
    http_method_names = ["get", "patch", "delete", "head", "options"]
