"""URL configuration for the archive app.

This module defines both template routes for
HTML pages and API routes using DRF routers,
including nested routes for hierarchical resources
(e.g., subjects -> encounters -> records).
"""

from __future__ import annotations

from django.urls import include, path

from . import views

# Django expects `app_name` for namespacing URLs.
# pylint: disable=invalid-name
app_name = "archive"

urlpatterns = [
    # Template views for HTML pages
    path("", views.index, name="index"),
    path("subjects/", views.subjects, name="subjects"),
    path("subject/<int:subject_id>/", views.subject_detail, name="subject_detail"),
    path("subjects/create/", views.subject_create, name="subject_create"),
    path("encounters/", views.encounters, name="encounters"),
    path("encounters/create/", views.encounter_create, name="encounter_create"),
    path("records/", views.records, name="records"),
    path("records/create/", views.scan, name="record_create"),
    path("records/<str:record_id>/", views.record_detail, name="record_detail"),
    path("physical-records/", views.physical_records, name="physical_records"),
    path("api/scan/tiff-preview/", views.scan_tiff_preview, name="scan_tiff_preview"),
    # API routes
    path("api/", include("archive.api.urls", namespace="api")),
]
