"""URL routes for the 9020 proxy"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "scan"

urlpatterns = [
    path("xray-class/", views.classify_xray_proxy, name="classify_xray"),
    path(
        "lateral-fliprot/",
        views.classify_lateral_fliprot_proxy,
        name="classify_lateral_fliprot",
    ),
    path(
        "frontal-fliprot/",
        views.classify_frontal_fliprot_proxy,
        name="classify_frontal_fliprot",
    ),
    path("xray-info/", views.get_xray_info_proxy, name="get_xray_info"),
]
