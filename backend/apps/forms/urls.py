from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("master-lists", views.MasterListViewSet, basename="masterlist")
router.register("master-list-items", views.MasterListItemViewSet, basename="masterlistitem")
router.register("forms", views.FormViewSet, basename="form")

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
    *router.urls,
]
