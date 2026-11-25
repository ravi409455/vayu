"""The project's URLs: every app's API under /api/v1."""
from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("apps.platform.urls")),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.forms.urls")),
    path("api/v1/", include("apps.bookings.urls")),
    path("api/v1/", include("apps.media.urls")),
    path("api/v1/", include("apps.reports.urls")),
    path("api/v1/", include("apps.integrations.urls")),
    path("api/v1/", include("apps.notify.urls")),
]
