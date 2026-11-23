from django.urls import path
from rest_framework.routers import SimpleRouter

from .dashboards import DashboardSummary, DashboardVolume
from .views import BookingViewSet, InspectionDetail, InspectionOverrides

router = SimpleRouter(trailing_slash=False)
router.register("bookings", BookingViewSet, basename="booking")
urlpatterns = [path("inspections/<uuid:pk>", InspectionDetail.as_view()),
               path("inspections/<uuid:pk>/overrides", InspectionOverrides.as_view()),
               path("dashboards/volume", DashboardVolume.as_view()),
               path("dashboards/summary", DashboardSummary.as_view()), *router.urls]
