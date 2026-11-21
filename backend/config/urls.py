"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.urls import include, path, re_path
from django.views.static import serve


def root_info_view(request):
    """Root endpoint serving service discovery & health check info."""
    endpoints = {
        "admin": "/admin/",
        "api_nodes": "/api/nodes/",
        "api_latest_reading": "/api/nodes/<node_id>/latest/",
        "api_history": "/api/nodes/<node_id>/history/?limit=100",
        "api_overview": "/api/overview/",
        "api_perf": "/api/perf/?run=<run_id>",
    }
    if getattr(settings, "LWB_PUBLIC", False):
        endpoints.pop("admin")  # not registered in public mode
    return JsonResponse(
        {
            "status": "healthy",
            "service": "lwb-backend",
            "version": "1.0.0",
            "endpoints": endpoints,
        }
    )


def dashboard_view(request):
    """Serve the built React dashboard (frontend/dist) without Node.js."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponse(
            "Dashboard chua duoc build (frontend/dist/index.html). API: /api/",
            content_type="text/plain; charset=utf-8", status=503)
    return HttpResponse(index.read_bytes(), content_type="text/html; charset=utf-8")


urlpatterns = [
    path("", dashboard_view, name="dashboard"),
    re_path(r"^assets/(?P<path>.*)$", serve, {"document_root": settings.FRONTEND_DIST / "assets"}),
    path("favicon.svg", serve, {"path": "favicon.svg", "document_root": settings.FRONTEND_DIST}),
    path("icons.svg", serve, {"path": "icons.svg", "document_root": settings.FRONTEND_DIST}),
    path("manifest.webmanifest", serve, {"path": "manifest.webmanifest", "document_root": settings.FRONTEND_DIST}),
    path("icon-192.png", serve, {"path": "icon-192.png", "document_root": settings.FRONTEND_DIST}),
    path("icon-512.png", serve, {"path": "icon-512.png", "document_root": settings.FRONTEND_DIST}),
    path("api/info/", root_info_view, name="root-info"),
    path("favicon.ico", lambda request: HttpResponse(status=204), name="favicon"),
    path("api/", include("telemetry.urls")),
]
# Public mode (LWB_PUBLIC=1, shared via Tailscale Funnel): no Django admin on the internet.
if not getattr(settings, "LWB_PUBLIC", False):
    urlpatterns.insert(-1, path("admin/", admin.site.urls))
