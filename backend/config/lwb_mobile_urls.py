from django.urls import include, path
urlpatterns = [path('api/mobile/v1/', include('telemetry.mobile_v1.urls'))]
