from django.urls import path

from . import views

urlpatterns = [
    path("media/initiate", views.Initiate.as_view()),
    path("media/<uuid:pk>", views.Detail.as_view()),
    path("media/<uuid:pk>/complete", views.Complete.as_view()),
    path("media/<uuid:pk>/url", views.Url.as_view()),
    path("media/<uuid:pk>/attach", views.Attach.as_view()),
    path("problems/stuck-uploads", views.StuckUploads.as_view()),
    path("bookings/<uuid:pk>/media", views.BookingMedia.as_view()),
    path("bookings/<uuid:pk>/media-zip", views.RequestZip.as_view()),
    path("bookings/<uuid:pk>/missing-files", views.MissingFiles.as_view()),
    path("bookings/<uuid:pk>/finish", views.Finish.as_view()),
    path("zips/<str:token>", views.ZipDownload.as_view()),
]
