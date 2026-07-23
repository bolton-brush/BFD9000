"""API routes for the archive app"""

from __future__ import annotations

from functools import reduce
from typing import TYPE_CHECKING, cast

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedDefaultRouter

from archive import views
from archive.api.scan.scan import scan_patterns

if TYPE_CHECKING:
    from django.urls.resolvers import URLPattern, URLResolver

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
subjects_router = NestedDefaultRouter(router, r"subjects", lookup="subject")
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

encounters_router = NestedDefaultRouter(router, r"encounters", lookup="encounter")
encounters_router.register(
    r"records", views.DigitalRecordViewSet, basename="encounter-records"
)
encounters_router.register(
    r"physical-records",
    views.PhysicalRecordViewSet,
    basename="encounter-physical-records",
)

imaging_router = NestedDefaultRouter(router, r"imaging-studies", lookup="imaging_study")
imaging_router.register(r"series", views.SeriesViewSet, basename="imagingstudy-series")

urls = [
    *reduce(
        lambda acc, b: acc + b.urls,
        [router, subjects_router, encounters_router, imaging_router],
        cast("list[URLPattern | URLResolver]", []),
    ),
    path("scan/", include((scan_patterns, "scan"))),
]
