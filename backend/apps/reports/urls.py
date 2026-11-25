"""URLs of the reports API."""
from django.urls import path

from . import media_links, views

urlpatterns = [
    path("pdf-templates", views.Templates.as_view()),
    path("pdf-templates/<int:pk>/drafts", views.Drafts.as_view()),
    path("pdf-templates/<int:pk>/copy", views.CopyTemplate.as_view()),
    path("pdf-templates/<int:pk>/import", views.ImportTemplate.as_view()),
    path("pdf-template-versions/<int:pk>", views.VersionDetail.as_view()),
    path("pdf-template-versions/<int:pk>/export", views.ExportTemplate.as_view()),
    path("pdf-pictures", views.Pictures.as_view()),
    path("pdf-pictures/<uuid:pk>", views.Picture.as_view()),
    path("pdf-shared", views.SharedItems.as_view()),
    path("pdf-shared/<int:pk>", views.SharedItemDetail.as_view()),
    path("pdf-template-versions/<int:pk>/publish", views.Publish.as_view()),
    path("pdf-template-versions/<int:pk>/preview", views.Preview.as_view()),
    path("pdf-template-versions/<int:pk>/checks", views.Checks.as_view()),
    path("bookings/<uuid:pk>/report", views.BookingReport.as_view()),
    path("bookings/<uuid:pk>/report/download", views.Download.as_view()),
    path("bookings/<uuid:pk>/report/regenerate", views.Regenerate.as_view()),
    path("bookings/<uuid:pk>/report/shared", views.Shared.as_view()),
    path("problems/reports", views.Problems.as_view()),
    path("verify/<str:token>", views.Verify.as_view()),
    path("verify/<str:token>/<str:link>", media_links.ReportMedia.as_view()),
]
