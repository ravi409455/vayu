from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("master-lists", views.MasterListViewSet, basename="masterlist")
router.register("master-list-items", views.MasterListItemViewSet, basename="masterlistitem")
router.register("forms", views.FormViewSet, basename="form")
router.register("library", views.LibraryViewSet, basename="library")

urlpatterns = [
    path("form-versions/<int:pk>", views.VersionDetail.as_view()),
    path("form-versions/<int:pk>/pages", views.PageCreate.as_view()),
    path("pages/<int:pk>", views.PageDetail.as_view()),
    path("pages/<int:pk>/sections", views.SectionCreate.as_view()),
    path("sections/<int:pk>", views.SectionDetail.as_view()),
    path("sections/<int:pk>/fields", views.FieldCreate.as_view()),
    path("fields/<int:pk>", views.FieldDetail.as_view()),
    path("form-versions/<int:pk>/checks", views.CheckCreate.as_view()),
    path("checks/<int:pk>", views.CheckDetail.as_view()),
    path("form-versions/<int:pk>/validate", views.ValidateVersion.as_view()),
    path("form-versions/<int:pk>/publish", views.PublishVersion.as_view()),
    path("form-versions/<int:pk>/rating-config", views.RatingConfigView.as_view()),
    path("sections/<int:pk>/fields/from-library", views.FieldFromLibrary.as_view()),
    path("pages/<int:pk>/sections/from-library", views.SectionFromLibrary.as_view()),
    path("fields/<int:pk>/accept-update", views.FieldAcceptUpdate.as_view()),
    path("fields/<int:pk>/unlink", views.FieldUnlink.as_view()),
    path("fields/<int:pk>/save-to-library", views.FieldSaveToLibrary.as_view()),
    path("sections/<int:pk>/accept-update", views.SectionAcceptUpdate.as_view()),
    path("sections/<int:pk>/unlink", views.SectionUnlink.as_view()),
    path("sections/<int:pk>/save-to-library", views.SectionSaveToLibrary.as_view()),
    *router.urls,
]
