"""URLs of the accounts API (auth/*, users, roles, permissions, audit log)."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AuditLogViewSet,
    ChangePasswordView,
    DeviceCheckedRefreshView,
    HeartbeatView,
    LoginView,
    LogoutView,
    MeView,
    MyPictureView,
    PermissionCatalogView,
    ProfileView,
    RolePermissionsView,
    RolesView,
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
    path("auth/me/profile", ProfileView.as_view()),
    path("auth/me/picture", MyPictureView.as_view()),
    path("auth/change-password", ChangePasswordView.as_view()),
    path("devices/heartbeat", HeartbeatView.as_view()),
    path("permissions", PermissionCatalogView.as_view()),
    path("roles", RolesView.as_view()),
    path("roles/<str:role>/permissions", RolePermissionsView.as_view()),
    *router.urls,
]
