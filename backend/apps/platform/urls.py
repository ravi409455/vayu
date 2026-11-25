from django.urls import path

from .views import HealthView, SettingView

urlpatterns = [path("health", HealthView.as_view()),
               path("settings/<str:key>", SettingView.as_view())]
