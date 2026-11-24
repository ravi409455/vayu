from django.urls import path

from .views import AppDownloadView, AppLatestView, NotificationsView, PushTokenView, ReadView

urlpatterns = [
    path("devices/push-token", PushTokenView.as_view()),
    path("notifications", NotificationsView.as_view()),
    path("notifications/read", ReadView.as_view()),
    path("app/latest", AppLatestView.as_view()),
    path("app/download", AppDownloadView.as_view()),
]
