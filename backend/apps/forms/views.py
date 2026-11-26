"""Form builder API: master lists, forms, versions and their parts, the library, publish,
promote (export / import) and form pictures."""
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import audit
from apps.accounts.permissions import perm, perm_any

from . import assets, library, library_push, promote, services
from .models import (
    Field,
    Form,
    FormAsset,
    FormVersion,
    LibraryItem,
    MasterList,
    MasterListItem,
    Page,
    Section,
    VersionCheck,
    ensure_draft,
)
from .rules import validate_version
from .serializers import (
    CheckSerializer,
    FieldSerializer,
    FormSerializer,
    LibraryItemDetailSerializer,
    LibraryItemSerializer,
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
    permission_classes = [perm(None, "master_lists.manage")]
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
    permission_classes = [perm(None, "master_lists.manage")]
    http_method_names = ["patch", "head", "options"]

    def perform_update(self, serializer):
        item = serializer.save()
        audit.record(self.request.user, "master_list.item_update", "master_list_item", item.id,
                     f"{item.list.key}.{item.key}")


class FormViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Form.objects.order_by("type", "key").prefetch_related("versions")
    serializer_class = FormSerializer
    permission_classes = [perm("forms.view", "forms.edit")]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]  # delete: the draft

    def get_queryset(self):
        qs = super().get_queryset()
        wanted = self.request.query_params.get("type")
        return qs.filter(type=wanted) if wanted else qs

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        form = services.create_form(request.user, key=d["key"], name=d["name"])
        return Response(self.get_serializer(form).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        """Name, active, and who sees its submissions decide access: audited (F-062)."""
        before = {k: getattr(serializer.instance, k) for k in serializer.validated_data}
        form = serializer.save()
        changed = sorted(k for k, v in before.items() if getattr(form, k) != v)
        if changed:
            audit.record(self.request.user, "form.update", "form", form.id,
                         f"Changed {', '.join(changed)} of {form.key}")

    @action(detail=True, methods=["delete"], url_path="draft")
    def discard_draft(self, request, pk=None):
        services.discard_draft(request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], permission_classes=[perm("forms.edit")])
    def duplicate(self, request, pk=None):
        """A copy of this custom form (newest version) as a new form with its own key and name:
        library links, ratings, Key Checks and PDF template come along; it starts as a draft."""
        d = request.data if isinstance(request.data, dict) else {}
        out = services.duplicate_form(request.user, self.get_object(), d.get("key"), d.get("name"))
        return Response(out, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def drafts(self, request, pk=None):
        draft = services.create_draft(request.user, self.get_object())
        return Response({"id": draft.id, "number": draft.number}, status=status.HTTP_201_CREATED)


class VersionDetail(generics.RetrieveAPIView):
    queryset = FormVersion.objects.all()
    serializer_class = VersionTreeSerializer
    permission_classes = [perm("forms.view")]


class ReorderVersion(generics.GenericAPIView):
    permission_classes = [perm("forms.edit")]

    def post(self, request, pk):
        v = services.reorder(request.user, pk, request.data)
        return Response({"row_version": v.row_version})


class PageCreate(generics.CreateAPIView):
    serializer_class = PageSerializer
    permission_classes = [perm("forms.edit")]

    def perform_create(self, serializer):
        version = get_object_or_404(FormVersion, pk=self.kwargs["pk"])
        order = serializer.validated_data.get("order", _next_order(Page.objects.filter(
            version=version)))
        serializer.save(version=version, order=order)


class PageDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Page.objects.all()
    serializer_class = PageSerializer
    permission_classes = [perm("forms.view", "forms.edit")]
    http_method_names = ["get", "patch", "delete", "head", "options"]


class SectionCreate(generics.CreateAPIView):
    serializer_class = SectionSerializer
    permission_classes = [perm("forms.edit")]

    def perform_create(self, serializer):
        page = get_object_or_404(Page, pk=self.kwargs["pk"])
        order = serializer.validated_data.get("order", _next_order(page.sections.all()))
        serializer.save(page=page, version_id=page.version_id, order=order)


class SectionDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Section.objects.all()
    serializer_class = SectionSerializer
    permission_classes = [perm("forms.view", "forms.edit")]
    http_method_names = ["get", "patch", "delete", "head", "options"]


class FieldCreate(generics.CreateAPIView):
    serializer_class = FieldSerializer
    permission_classes = [perm("forms.edit")]

    def perform_create(self, serializer):
        section = get_object_or_404(Section, pk=self.kwargs["pk"])
        ensure_draft(section.version_id)
        library.ensure_not_locked(section)
        order = serializer.validated_data.get("order", _next_order(section.fields.all()))
        serializer.save(section=section, version_id=section.version_id, order=order)


class FieldDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Field.objects.select_related("section", "library_item")
    serializer_class = FieldSerializer
    permission_classes = [perm("forms.view", "forms.edit")]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def perform_destroy(self, instance):
        ensure_draft(instance.version_id)
        library.ensure_not_locked(instance.section)  # fields of a linked section stay put
        instance.delete()


class CheckCreate(generics.CreateAPIView):
    serializer_class = CheckSerializer
    permission_classes = [perm("forms.edit")]

    def perform_create(self, serializer):
        version = get_object_or_404(FormVersion, pk=self.kwargs["pk"])
        serializer.save(version=version)


class CheckDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = VersionCheck.objects.all()
    serializer_class = CheckSerializer
    permission_classes = [perm("forms.view", "forms.edit")]
    http_method_names = ["get", "patch", "delete", "head", "options"]


class ValidateVersion(generics.GenericAPIView):
    queryset = FormVersion.objects.select_related("form")
    permission_classes = [perm("forms.edit")]

    def post(self, request, pk):
        issues = validate_version(self.get_object())
        return Response({"issues": [i.__dict__ for i in issues]})


class LibraryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    permission_classes = [perm("library.view", "library.edit")]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        return LibraryItemDetailSerializer if self.action == "retrieve" else LibraryItemSerializer

    def get_queryset(self):
        p = self.request.query_params
        qs = LibraryItem.objects.order_by("kind", "key")
        if not p.get("include_archived"):
            qs = qs.filter(archived=False)
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        if p.get("q"):
            qs = qs.filter(Q(key__icontains=p["q"]) | Q(name__icontains=p["q"]))
        return qs if self.action == "list" else LibraryItem.objects.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.action == "list":
            ctx["used_in"] = library.used_in_counts()
        return ctx

    def create(self, request, *args, **kwargs):
        d = request.data
        item = library.create_item(request.user, kind=d.get("kind"), key=d.get("key", ""),
                                   name=d.get("name"), definition=d.get("definition"))
        return Response(LibraryItemSerializer(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        d = request.data
        item = library.update_item(request.user, self.get_object(), definition=d.get("definition"),
                                   archived=d.get("archived"), name=d.get("name"),
                                   revision=d.get("revision"))
        return Response(LibraryItemSerializer(item).data)

    def destroy(self, request, *args, **kwargs):
        library.delete_item(request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="push-preview",
            permission_classes=[perm("library.edit")])
    def push_preview(self, request, pk=None):
        return Response(library_push.preview(request.user, self.get_object()))

    @action(detail=True, methods=["post"], url_path="push",
            permission_classes=[perm("library.edit")])
    def push(self, request, pk=None):
        d = request.data
        return Response(library_push.push(
            request.user, self.get_object(), revision=d.get("revision"),
            publish=d.get("publish") is True, confirm=d.get("confirm") is True))

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        from apps.accounts.models import User

        revs = list(self.get_object().revisions.all())
        names = {u.username: u.shown_name
                 for u in User.objects.filter(username__in={r.by for r in revs})}
        return Response([{"revision": r.revision, "name": r.name, "definition": r.definition,
                          "changed_keys": r.changed_keys, "by": names.get(r.by, r.by),
                          "by_login": r.by, "at": r.at} for r in revs])


class _FromLibraryBody(serializers.Serializer):
    library_item = serializers.IntegerField()
    link = serializers.BooleanField(default=True)


class FieldFromLibrary(generics.GenericAPIView):
    permission_classes = [perm("forms.edit")]
    serializer_class = _FromLibraryBody

    def post(self, request, pk):
        body = _FromLibraryBody(data=request.data)
        body.is_valid(raise_exception=True)
        section = get_object_or_404(Section, pk=pk)
        item = get_object_or_404(LibraryItem, pk=body.validated_data["library_item"])
        field = library.add_field(request.user, section, item, body.validated_data["link"])
        return Response(FieldSerializer(field).data, status=status.HTTP_201_CREATED)


class SectionFromLibrary(generics.GenericAPIView):
    permission_classes = [perm("forms.edit")]
    serializer_class = _FromLibraryBody

    def post(self, request, pk):
        body = _FromLibraryBody(data=request.data)
        body.is_valid(raise_exception=True)
        page = get_object_or_404(Page, pk=pk)
        item = get_object_or_404(LibraryItem, pk=body.validated_data["library_item"])
        section = library.add_section(request.user, page, item, body.validated_data["link"])
        return Response(SectionSerializer(section).data, status=status.HTTP_201_CREATED)


class _LinkAction(generics.GenericAPIView):
    """accept-update / unlink / save-to-library on a field or a section."""

    permission_classes = [perm("forms.edit")]
    model: type[Field] | type[Section] = Field
    result: type[serializers.ModelSerializer] = FieldSerializer

    def obj(self, pk):
        return get_object_or_404(self.model.objects.select_related("library_item"), pk=pk)


class _OnField(_LinkAction):
    model, result = Field, FieldSerializer


class _OnSection(_LinkAction):
    model, result = Section, SectionSerializer


def _accept(self, request, pk):
    return Response(self.result(library.accept_update(request.user, self.obj(pk))).data)


def _unlink(self, request, pk):
    return Response(self.result(library.unlink(request.user, self.obj(pk))).data)


def _save(self, request, pk):
    item = library.save_to_library(request.user, self.obj(pk), key=request.data.get("key"),
                                   name=request.data.get("name"))
    return Response(LibraryItemSerializer(item).data, status=status.HTTP_201_CREATED)


SAVE_PERMS = [perm("forms.edit", ("forms.edit", "library.edit"))]


class FieldAcceptUpdate(_OnField):
    post = _accept


class SectionAcceptUpdate(_OnSection):
    post = _accept


class FieldUnlink(_OnField):
    post = _unlink


class SectionUnlink(_OnSection):
    post = _unlink


class FieldSaveToLibrary(_OnField):
    permission_classes = SAVE_PERMS
    post = _save


class SectionSaveToLibrary(_OnSection):
    permission_classes = SAVE_PERMS
    post = _save


class _PublishBody(serializers.Serializer):
    row_version = serializers.IntegerField()


class PublishVersion(generics.GenericAPIView):
    permission_classes = [perm("forms.publish")]
    serializer_class = _PublishBody

    def post(self, request, pk):
        body = _PublishBody(data=request.data)
        body.is_valid(raise_exception=True)
        v = services.publish_version(request.user, pk, body.validated_data["row_version"])
        return Response({"id": v.id, "number": v.number, "status": v.status,
                         "published_at": v.published_at, "row_version": v.row_version,
                         "warnings": services.publish_warnings(v)})


class VersionSettings(generics.GenericAPIView):
    """A custom form's two switches: begins with the start form, ends with the end form."""
    permission_classes = [perm("forms.view", "forms.edit")]

    def patch(self, request, pk):
        version = services.save_version_settings(request.user, pk, request.data)
        return Response({"use_start": version.use_start, "use_end": version.use_end,
                         "row_version": version.row_version})


class RatingConfigView(generics.GenericAPIView):
    permission_classes = [perm("forms.view", "forms.edit")]

    def patch(self, request, pk):
        config = request.data.get("config")
        if config is None:
            raise serializers.ValidationError({"config": "This field is required."})
        version = services.save_rating_config(request.user, pk, config)
        return Response({"rating_config": version.rating_config,
                         "row_version": version.row_version})


class KeyChecksView(generics.GenericAPIView):
    """The draft's Key Checks, saved as a whole ordered list (like the rating config)."""

    permission_classes = [perm("forms.view", "forms.edit")]

    def patch(self, request, pk):
        items = request.data.get("key_checks")
        version = services.save_key_checks(request.user, pk, items)
        return Response({"key_checks": items, "row_version": version.row_version})


class PromoteExport(generics.GenericAPIView):
    permission_classes = [perm("forms.promote")]
    # a download link: Safari and Firefox ask for HTML and saved the browsable page (F-11)
    renderer_classes = [JSONRenderer]

    def get(self, request):
        if not request.query_params.get("version"):
            raise serializers.ValidationError({"version": "This query parameter is required."})
        version = get_object_or_404(FormVersion.objects.select_related("form"),
                                    pk=request.query_params["version"])
        response = Response(promote.export_bundle(version))
        response["Content-Disposition"] = (f'attachment; filename="{version.form.key}'
                                           f'-v{version.number}.json"')
        return response


class PromoteImport(generics.GenericAPIView):
    permission_classes = [perm("forms.promote")]

    def post(self, request):
        key, name = request.query_params.get("as_new_key"), request.query_params.get("as_new_name")
        as_new = {"key": key, "name": name} if key is not None or name is not None else None
        return Response(promote.import_bundle(request.user, request.data, as_new=as_new),
                        status=status.HTTP_201_CREATED)


class FormAssetUpload(generics.GenericAPIView):
    """POST a picture (multipart field 'file'); returns the id to put in an image field."""
    permission_classes = [perm("forms.edit")]

    def post(self, request):
        file = request.FILES.get("file")
        if file is None:
            raise serializers.ValidationError({"file": "Choose a picture."})
        asset = assets.create_asset(request.user, file.read(assets.MAX_BYTES + 1))
        return Response({"id": str(asset.id), "url": f"/api/v1/form-assets/{asset.id}"},
                        status=status.HTTP_201_CREATED)


class InspectionTypes(APIView):
    """The custom forms by name: what Ops pick when they book, and what labels show everywhere.
    `available` is true while a form is on and has a published version."""
    permission_classes = [perm_any("forms.view", "bookings.view", "submissions.fill")]

    def get(self, request):
        rows = Form.objects.filter(type="custom").exclude(inspection_type="").order_by("name")
        live = set(FormVersion.objects.filter(status="published").values_list("form_id",
                                                                              flat=True))
        return Response([{"key": f.inspection_type, "label": f.name,
                          "available": f.is_active and f.id in live} for f in rows])


class FormAssetShow(APIView):
    """Anyone signed in may see a form's pictures (they are part of the form)."""

    def get(self, request, pk):
        from django.http import HttpResponseRedirect

        return HttpResponseRedirect(assets.url(get_object_or_404(FormAsset, pk=pk)))
