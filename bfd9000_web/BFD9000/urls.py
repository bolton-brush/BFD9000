"""URL configuration for BFD9000 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/

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

import django_cas_ng.views
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from BFD9000.conf import settings


def logout_view(request: HttpRequest) -> HttpResponse:
    """Log out on any request method and redirect to login.

    Args:
        request: A generic HTTP Request

    Returns:
        A redirect to login

    """
    logout(request)
    return redirect("login")


def login_view(request: HttpRequest) -> HttpResponse:
    """Simply shows the basic login page

    Args:
        request: A generic HTTP Request

    Returns:
        The login page

    """
    next_url = request.GET.get("next", "")
    return render(request, "archive/login.html", {"next": next_url})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", login_view, name="login"),
    path(
        "login/local/",
        auth_views.LoginView.as_view(template_name="archive/login_local.html"),
        name="login_local",
    ),
    path("logout/", logout_view, name="logout"),
    path("", include("archive.urls")),
    # CAS support
    path("cas/login", django_cas_ng.views.LoginView.as_view(), name="cas_ng_login"),
    path(
        "cas/logout",
        django_cas_ng.views.LogoutView.as_view(),
        name="cas_ng_logout",
    ),
    path(
        "cas/callback",
        django_cas_ng.views.CallbackView.as_view(),
        name="cas_ng_proxy_callback",
    ),
    # OpenAPI Schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # Redoc UI
    path(
        "api/schema/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
