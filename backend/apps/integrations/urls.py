from django.urls import path

from . import ext_views, views

urlpatterns = [
    path("integrations", views.IntegrationList.as_view()),
    path("integrations/events", views.EventCatalog.as_view()),
    path("integrations/render-sample", views.RenderSample.as_view()),
    path("integrations/<uuid:pk>", views.IntegrationDetail.as_view()),
    path("integrations/<uuid:pk>/rotate-secret", views.RotateSecret.as_view()),
    path("integrations/<uuid:pk>/test", views.TestSend.as_view()),
    path("integrations/<uuid:pk>/deliveries", views.DeliveryList.as_view()),
    path("deliveries/<uuid:pk>/resend", views.Resend.as_view()),
    path("api-keys", views.ApiKeyList.as_view()),
    path("api-keys/<uuid:pk>", views.ApiKeyDetail.as_view()),
    path("api-keys/<uuid:pk>/revoke", views.ApiKeyRevoke.as_view()),
    path("schema", views.SchemaView.as_view(), name="schema"),
    path("docs", views.DocsView.as_view(url_name="schema")),
    # the REST API for other systems (API key authentication)
    path("ext/bookings", ext_views.Bookings.as_view()),
    path("ext/bookings/bulk", ext_views.BulkBookings.as_view()),
    path("ext/bookings/<str:ref>", ext_views.BookingDetail.as_view()),
    path("ext/bookings/<str:ref>/inspection", ext_views.BookingInspection.as_view()),
]
