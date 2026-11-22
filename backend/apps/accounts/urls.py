from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
                    AuditLogViewSet,
                    ChangePasswordView,
                    DeviceCheckedRefreshView,
                    LoginView,
                    LogoutView,
                    MeView,
                    UserViewSet,
)

router = SimpleRouter(trailing_slash=False)
router.register("users", UserViewSet, basename="user")
router.register("audit-logs", AuditLogViewSet, basename="auditlog")

urlpatterns = [
    path("auth/login", LoginView.as_view()),
    path("auth/refresh", DeviceCheckedRefreshView.as_view()),
    path("auth/logout", LogoutView.as_view()),
    path("auth/me", MeView.as_view()),
    path("auth/change-password", ChangePasswordView.as_view()),
    *router.urls,
]
