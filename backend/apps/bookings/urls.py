from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import BookingViewSet, InspectionDetail

router = SimpleRouter(trailing_slash=False)
router.register("bookings", BookingViewSet, basename="booking")
urlpatterns = [path("inspections/<uuid:pk>", InspectionDetail.as_view()), *router.urls]
