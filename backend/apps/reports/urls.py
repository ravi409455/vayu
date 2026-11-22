from django.urls import path

from . import views

urlpatterns = [
    path("pdf-templates", views.Templates.as_view()),
    path("pdf-templates/<int:pk>/drafts", views.Drafts.as_view()),
    path("pdf-template-versions/<int:pk>", views.VersionDetail.as_view()),
    path("pdf-template-versions/<int:pk>/publish", views.Publish.as_view()),
    path("pdf-template-versions/<int:pk>/preview", views.Preview.as_view()),
    path("bookings/<uuid:pk>/report", views.BookingReport.as_view()),
    path("bookings/<uuid:pk>/report/regenerate", views.Regenerate.as_view()),
    path("problems/reports", views.Problems.as_view()),
    path("verify/<str:token>", views.Verify.as_view()),
]
