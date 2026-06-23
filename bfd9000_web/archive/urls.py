"""URL configuration for the archive app.

This module defines both template routes for
HTML pages and API routes using DRF routers,
including nested routes for hierarchical resources
(e.g., subjects -> encounters -> records).
"""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from . import views

router = DefaultRouter()
router.register(r"codings", views.CodingViewSet)
router.register(r"identifiers", views.IdentifierViewSet)
router.register(r"addresses", views.AddressViewSet)
router.register(r"locations", views.LocationViewSet)
router.register(r"physical-locations", views.PhysicalLocationViewSet)
router.register(r"collections", views.CollectionViewSet)
router.register(r"subjects", views.SubjectViewSet)
router.register(r"encounters", views.EncounterViewSet)
router.register(r"imaging-studies", views.ImagingStudyViewSet)
router.register(r"endpoints", views.EndpointViewSet)
router.register(r"archive-locations", views.ArchiveLocationViewSet)
router.register(r"records", views.DigitalRecordViewSet)
router.register(r"physical-records", views.PhysicalRecordViewSet)
router.register(r"series", views.SeriesViewSet)
router.register(r"valuesets", views.ValuesetViewSet, basename="valuesets")

# Nested routers
subjects_router = routers.NestedDefaultRouter(router, r"subjects", lookup="subject")
subjects_router.register(
    r"encounters", views.EncounterViewSet, basename="subject-encounters"
)
subjects_router.register(
    r"records", views.DigitalRecordViewSet, basename="subject-records"
)
subjects_router.register(
    r"physical-records",
    views.PhysicalRecordViewSet,
    basename="subject-physical-records",
)

encounters_router = routers.NestedDefaultRouter(
    router, r"encounters", lookup="encounter"
)
encounters_router.register(
    r"records", views.DigitalRecordViewSet, basename="encounter-records"
)
encounters_router.register(
    r"physical-records",
    views.PhysicalRecordViewSet,
    basename="encounter-physical-records",
)

imaging_router = routers.NestedDefaultRouter(
    router, r"imaging-studies", lookup="imaging_study"
)
imaging_router.register(r"series", views.SeriesViewSet, basename="imagingstudy-series")

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
    path("api/", include(router.urls)),
    path("api/", include(subjects_router.urls)),
    path("api/", include(encounters_router.urls)),
    path("api/", include(imaging_router.urls)),
]
