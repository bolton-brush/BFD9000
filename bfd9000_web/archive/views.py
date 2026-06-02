"""Views for the archive app.

This module defines the ViewSets for the API, handling CRUD operations
for subjects, encounters, records, and related medical entities.
It also includes custom actions for file serving and valueset retrieval.
"""

import pathlib
from typing import TYPE_CHECKING, Any, TypeVar, cast, final, override

from BFD9000.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.db.models import (
    CharField,
    Count,
    Model,
    OuterRef,
    Prefetch,
    QuerySet,
    Subquery,
)
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import render
from django.views.decorators.http import require_POST
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from PIL import Image
from rest_framework import filters, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .constants import (
    SYSTEM_IDENTIFIER_BOLTON_SUBJECT,
    SYSTEM_IDENTIFIER_LANCASTER_SUBJECT,
)
from .filters import DigitalRecordFilter
from .media_utils import convert_tiff_to_png_bytes
from .models import (
    Address,
    ArchiveLocation,
    Coding,
    Collection,
    DigitalRecord,
    Encounter,
    Endpoint,
    Identifier,
    ImagingStudy,
    Location,
    PhysicalLocation,
    PhysicalRecord,
    Series,
    Subject,
    ValueSet,
)
from .permissions import CuratorOrSuperuserEditPermission, RecordPermission
from .serializers import (
    AddressSerializer,
    ArchiveLocationSerializer,
    CodingSerializer,
    CollectionSerializer,
    DigitalRecordSerializer,
    DigitalRecordUploadSerializer,
    EncounterSerializer,
    EndpointSerializer,
    IdentifierSerializer,
    ImagingStudySerializer,
    LocationSerializer,
    PhysicalLocationSerializer,
    PhysicalRecordSerializer,
    SeriesSerializer,
    SubjectSerializer,
)

if TYPE_CHECKING:
    from datetime import date

    from django.contrib.auth.models import User
    from django.db.models.fields.files import FieldFile, ImageFieldFile

MAX_TIFF_PREVIEW_BYTES = 100 * 1024 * 1024
MAX_TIFF_PREVIEW_PIXELS = 100_000_000
Image.MAX_IMAGE_PIXELS = MAX_TIFF_PREVIEW_PIXELS


@final
class ValuesetViewSet(viewsets.ViewSet):
    """API endpoint that allows valuesets to be viewed.

    Provides a read-only interface for retrieving standard codes and options
    used throughout the application (e.g., sex, modalities, orientations).
    """

    # NOTE: This viewset is read-only and not tied to a specific model/queryset,
    # so DjangoModelPermissions (the project-wide default) are not applicable.
    # We intentionally use IsAuthenticated here to
    # require login but not model-level perms.
    permission_classes = (IsAuthenticated,)

    def list(self, request: Request) -> Response:  # noqa: PLR6301
        """List values for a specific valueset type.

        Args:
            request: The HTTP request containing the 'type' query parameter.

        Returns:
            Response: A list of dictionaries with 'id' and 'display' keys.

        """
        valueset_type = cast("str", request.query_params.get("type"))
        if not valueset_type:
            return Response({"error": "Missing 'type' parameter"}, status=400)

        data: list[dict[str, str]] = []

        if valueset_type == "sex_options":
            data = [{"id": k, "display": v} for k, v in Subject.GENDER_CHOICES]

        elif valueset_type == "collections":
            colls = Collection.objects.all()
            data = [{"id": c.short_name, "display": c.full_name} for c in colls]

        else:
            valueset = ValueSet.objects.filter(slug=valueset_type).first()
            if valueset:
                codings = Coding.objects.filter(value_sets=valueset).order_by("code")
                data = [{"id": c.code, "display": c.display} for c in codings]
                return Response(data)

            return Response(
                {"error": f"Unknown valueset type: {valueset_type}"}, status=404
            )

        return Response(data)


@final
class CodingViewSet(viewsets.ModelViewSet[Coding]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for Coding model.

    Handles standard medical codes (SNOMED, DICOM, etc.).
    """

    queryset = Coding.objects.all()
    serializer_class = CodingSerializer
    filterset_fields = ("system", "code")


@final
class IdentifierViewSet(viewsets.ModelViewSet[Identifier]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for Identifier model.

    Handles identifiers associated with subjects and other entities.
    """

    queryset = Identifier.objects.all()
    serializer_class = IdentifierSerializer
    filterset_fields = ("system", "value", "use")


@final
class AddressViewSet(viewsets.ModelViewSet[Address]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for Address model."""

    queryset = Address.objects.all()
    serializer_class = AddressSerializer


@final
class LocationViewSet(viewsets.ModelViewSet[Location]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for Location model.

    Represents physical locations where encounters or scans occur.
    """

    queryset = Location.objects.all()
    serializer_class = LocationSerializer


@final
class CollectionViewSet(viewsets.ModelViewSet[Collection]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for Collection model.

    Manages collections of records (e.g., specific studies or datasets).
    """

    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer
    filterset_fields = ("short_name",)


@final
class SubjectViewSet(viewsets.ModelViewSet[Subject]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for Subject model.

    Manages patient/subject information including demographics.
    Subjects are ordered by their preferred display identifier (official →
    Bolton system → first), resolved at the database level via correlated
    subqueries to match the serializer's ``subject_identifier`` field.
    """

    permission_classes = (CuratorOrSuperuserEditPermission,)
    queryset = (
        Subject.objects.prefetch_related("identifiers")
        .annotate(
            encounter_count=Count("encounters", distinct=True),
            record_count=Count(
                "encounters__imaging_study__series__digital_records", distinct=True
            ),
            physical_record_count=Count("encounters__physical_records", distinct=True),
            official_identifier=Subquery(
                Identifier.objects.filter(
                    subjects=OuterRef("pk"),
                    use="official",
                )
                .order_by("pk")
                .values("value")[:1],
                output_field=CharField[str, str](),
            ),
        )
        .order_by("official_identifier", "id")
    )
    serializer_class = SubjectSerializer
    filterset_fields = (
        "identifiers__value",
        "gender",
        "ethnicity__code",
        "skeletal_pattern__code",
        "palatal_cleft__code",
        "collection__short_name",
    )
    search_fields = ("^identifiers__value",)


@final
class EncounterViewSet(viewsets.ModelViewSet[Encounter]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for Encounter model.

    Manages clinical encounters or visits.
    """

    permission_classes = (CuratorOrSuperuserEditPermission,)
    queryset = (
        Encounter.objects.select_related("subject")
        .prefetch_related("subject__identifiers")
        .annotate(
            record_count=Count("imaging_study__series__digital_records", distinct=True)
        )
        .order_by("-actual_period_start", "-id")
    )
    serializer_class = EncounterSerializer
    filterset_fields = (
        "subject",
        "actual_period_start",
    )
    search_fields = ("^subject__identifiers__value",)

    @override
    def perform_create(self, serializer: EncounterSerializer) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Custom creation logic to handle subject association and age calculation.

        Raises:
            ValidationError: If subject field is not present

        """
        # The validated_data is a dict mirroring the Encounter class
        vd: dict[str, Any] = serializer.validated_data  # pyright: ignore[reportAny, reportExplicitAny]
        # Subject is now a dict mirroring the Subject class
        subject: dict[str, Any] | None = vd.get("subject")  # pyright: ignore[reportExplicitAny]
        subject_obj: Subject | None = None

        # If not in body, check URL
        if not subject:
            subject_pk: str | None = self.kwargs.get("subject_pk")
            if subject_pk:
                subject_obj = get_object_or_404(Subject, pk=subject_pk)
            else:
                raise serializers.ValidationError(
                    {"subject": "This field is required."}
                )

        # Calculate age_at_encounter if not provided
        if "age_at_encounter" not in vd:
            encounter_date: date | None = vd.get("actual_period_start")

            if subject_obj and subject_obj.birth_date and encounter_date:
                # Calculate duration
                delta = encounter_date - subject_obj.birth_date
                _ = serializer.save(subject=subject_obj, procedure_occurrence_age=delta)
                return

        _ = serializer.save(subject=subject_obj)


@final
class ImagingStudyViewSet(viewsets.ModelViewSet[ImagingStudy]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for ImagingStudy model.

    Manages the technical details of an imaging session.
    """

    queryset = ImagingStudy.objects.prefetch_related(
        Prefetch(
            "series__digital_records",
            queryset=DigitalRecord.objects.filter(operator__isnull=False)
            .select_related("operator")
            .order_by("-created_at"),
            to_attr="_operator_records",
        )
    )
    serializer_class = ImagingStudySerializer
    filterset_fields = ("encounter", "collection")


@final
class SeriesViewSet(viewsets.ModelViewSet[Series]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for Series model.

    Exposes series grouped under imaging studies. Standard CRUD.
    Requires authentication to prevent unauthenticated enumeration of all series.
    """

    queryset = Series.objects.select_related(
        "imaging_study", "modality"
    ).prefetch_related("digital_records")
    serializer_class = SeriesSerializer
    permission_classes = (IsAuthenticated,)


@final
class EndpointViewSet(viewsets.ModelViewSet[Endpoint]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for archive Endpoint definitions."""

    queryset = Endpoint.objects.all()
    serializer_class = EndpointSerializer
    filterset_fields = ("status", "connection_type")
    search_fields = ("name", "address")


@final
class ArchiveLocationViewSet(viewsets.ModelViewSet[ArchiveLocation]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for archived storage locations of digital records."""

    queryset = ArchiveLocation.objects.select_related("digital_record", "endpoint")
    serializer_class = ArchiveLocationSerializer
    filterset_fields = (
        "digital_record",
        "endpoint",
        "status",
        "endpoint__connection_type",
    )
    search_fields = (
        "assigned_id",
        "digital_record__id",
        "endpoint__name",
        "endpoint__address",
    )


@final
class BoltonRecordSearchFilter(filters.SearchFilter):
    """SearchFilter subclass that applies .distinct() only when a search query is active

    Prevents duplicate rows from the identifiers M2M JOIN on non-search requests,
    while ensuring correct results when searching via identifiers__value.
    """

    _T = TypeVar("_T", bound=Model)

    @override
    def filter_queryset(
        self, request: Request, queryset: QuerySet[_T], view: APIView
    ) -> QuerySet[_T]:
        search_terms = self.get_search_terms(request)
        if search_terms:
            queryset = queryset.distinct()
        return super().filter_queryset(request, queryset, view)


@final
class PhysicalLocationViewSet(viewsets.ModelViewSet[PhysicalLocation]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for PhysicalLocation — archive storage slots."""

    queryset = PhysicalLocation.objects.select_related("address")
    serializer_class = PhysicalLocationSerializer
    filterset_fields = ("cabinet", "shelf")
    search_fields = ("cabinet", "shelf", "slot", "raw")


@final
class PhysicalRecordViewSet(viewsets.ModelViewSet[PhysicalRecord]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for PhysicalRecord model.

    Manages original physical artifacts (films, models, charts) linked to encounters.
    """

    queryset = PhysicalRecord.objects.select_related(
        "encounter__subject",
        "record_type",
        "device",
    ).prefetch_related(
        "encounter__subject__identifiers",
        "locations",
        "identifiers",
    )
    serializer_class = PhysicalRecordSerializer
    filterset_fields = ("encounter", "record_type")
    filter_backends = (BoltonRecordSearchFilter, filters.OrderingFilter)
    search_fields = ("^identifiers__value",)

    @override
    def get_queryset(self) -> QuerySet[PhysicalRecord]:
        qs = super().get_queryset()
        encounter_pk = self.kwargs.get("encounter_pk")
        if encounter_pk:
            qs = qs.filter(encounter__id=encounter_pk)
        subject_pk = self.kwargs.get("subject_pk")
        if subject_pk:
            qs = qs.filter(encounter__subject__id=subject_pk)
        return qs


@final
class DigitalRecordViewSet(viewsets.ModelViewSet[DigitalRecord]):  # pyright: ignore[reportUninitializedInstanceVariable]
    """ViewSet for DigitalRecord model.

    Manages the high-level digital record entries
    that link encounters to imaging studies.
    Supports file uploads via a specialized serializer.
    """

    permission_classes = (RecordPermission,)
    queryset = DigitalRecord.objects.select_related(
        "series__imaging_study__encounter",
        "series__modality",
        "record_type",
        "physical_record",
        "device",
    ).prefetch_related(
        "series__imaging_study__encounter__subject__identifiers",
        "archive_locations__endpoint",
        "identifiers",
    )
    serializer_class = DigitalRecordSerializer
    filterset_class = DigitalRecordFilter
    filter_backends = (BoltonRecordSearchFilter, filters.OrderingFilter)
    search_fields = ("^identifiers__value",)

    @override
    def get_serializer_class(self) -> type[serializers.Serializer[DigitalRecord]]:
        if self.action == "create":
            return DigitalRecordUploadSerializer
        return DigitalRecordSerializer

    @override
    def get_serializer_context(self) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        context = dict(super().get_serializer_context())
        if self.action == "create":
            # If nested, get encounter
            encounter_pk = self.kwargs.get("encounter_pk")
            if encounter_pk:
                encounter = get_object_or_404(Encounter, pk=encounter_pk)
                context["encounter"] = encounter
        return context

    @override
    def get_queryset(self) -> QuerySet[DigitalRecord]:
        qs = super().get_queryset()
        # Filter by nested encounter if present (via series -> imaging_study)
        encounter_pk = self.kwargs.get("encounter_pk")
        if encounter_pk:
            qs = qs.filter(series__imaging_study__encounter__id=encounter_pk)

        # Filter by nested subject if present
        subject_pk = self.kwargs.get("subject_pk")
        if subject_pk:
            qs = qs.filter(series__imaging_study__encounter__subject__id=subject_pk)

        # Query param filter for record_type
        record_type = cast(
            "int | None",
            cast("QueryDict", self.request.query_params).get("record_type"),
        )
        if record_type:
            qs = qs.filter(record_type__id=record_type)

        return qs

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def image(
        self,
        request: Request,
        pk: int | None = None,
        **_kwargs: Any,  # pyright: ignore[reportExplicitAny, reportAny]  # noqa: ANN401
    ) -> Response | FileResponse:
        """Get image for digital record

        Returns:
            Error response if no image or FileResponse if an image was found

        """
        del request, pk, _kwargs
        digital_record = self.get_object()
        source_file: FieldFile | None = getattr(digital_record, "source_file", None)
        if not source_file:
            return Response({"error": "No image file available"}, status=404)
        return FileResponse(source_file.open("rb"))

    @extend_schema(responses={(200, "image/jpeg"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def thumbnail(
        self,
        request: Request,
        pk: int | None = None,
        **_kwargs: Any,  # pyright: ignore[reportAny, reportExplicitAny]  # noqa: ANN401
    ) -> HttpResponse | JsonResponse | FileResponse:
        """Get thumbnail for digital record

        Returns:
            Error response if no image or FileResponse if an image was found

        """
        del request, pk, _kwargs
        digital_record = self.get_object()

        file: ImageFieldFile | None = getattr(digital_record, "thumbnail", None)

        if file:
            try:
                return FileResponse(file.open("rb"), content_type="image/jpeg")
            except Exception:  # noqa: S110
                pass

        fallback_path: str | None = finders.find("archive/img/no-thumbnail.jpg")
        if fallback_path:
            with pathlib.Path(fallback_path).open("rb") as f:
                return HttpResponse(f.read(), content_type="image/jpeg")
        return JsonResponse(
            {"error": "No thumbnail or fallback available."}, status=404
        )

    @action(detail=True, methods=["get"])
    def dicom(self, request: Request, pk: int | None = None, **kwargs: Any) -> Response:  # pyright: ignore[reportAny, reportExplicitAny]  # noqa: ANN401, PLR6301
        """Get DICOM download

        !NOT IMPLEMENTED

        Returns:
            The DICOM download

        """
        del request, pk, kwargs
        return Response({"error": "DICOM download not implemented"}, status=404)


@login_required
def index(request: Request) -> HttpResponse:
    """Render the main archive dashboard.

    Returns:
        The index page

    """
    return render(request, "archive/index.html")


@login_required
def subjects(request: Request) -> HttpResponse:
    """Render the subject list page.

    Returns:
        The subject list page

    """
    return render(request, "archive/subjects.html")


@login_required
def subject_detail(request: Request, subject_id: int) -> HttpResponse:
    """Render the subject detail page.

    Returns:
        The subject detail page

    """
    return render(request, "archive/subject_detail.html", {"subject_id": subject_id})


@login_required
def subject_create(request: Request) -> HttpResponse:
    """Render the subject creation form.

    Returns:
        The subject creation form

    """
    return render(
        request,
        "archive/subject_create.html",
        {
            "bolton_identifier_system": SYSTEM_IDENTIFIER_BOLTON_SUBJECT,
            "lancaster_identifier_system": SYSTEM_IDENTIFIER_LANCASTER_SUBJECT,
        },
    )


@login_required
def encounters(request: Request) -> HttpResponse:
    """Render the encounter list page.

    Returns:
        The encounter list page

    """
    return render(request, "archive/encounters.html")


@login_required
def encounter_create(request: Request) -> HttpResponse:
    """Render the encounter creation form.

    Returns:
        The encounter creation form

    """
    return render(request, "archive/encounter_create.html")


@login_required
def records(request: Request) -> HttpResponse:
    """Render the record list page.

    Returns:
        The record list page

    """
    return render(request, "archive/records.html")


@login_required
def physical_records(request: Request) -> HttpResponse:
    """Render the physical record list page.

    Returns:
        The physical record list page

    """
    return render(request, "archive/physical_records.html")


@login_required
def record_detail(request: Request, record_id: str) -> HttpResponse:
    """Render the record detail page.

    Returns:
        The record detail page

    """
    return render(request, "archive/record_detail.html", {"record_id": record_id})


@login_required
def scan(request: Request) -> HttpResponse:
    """Render the scan workflow page.

    Returns:
        The scan workflow page

    """
    # We know the user is logged in due to the decorator
    user: User = cast("User", request.user)
    full_name = user.get_full_name().strip()
    operator_display = f"{full_name} ({user.username})" if full_name else user.username  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return render(
        request,
        "archive/scan.html",
        {
            "operator_display": operator_display,
            "scanner_api_base": settings.SCANNER_API_BASE,
            "scanner_device_id": settings.SCANNER_DEVICE_ID,
            "ai_base_url": settings.BFD9020_BASE_URL,
        },
    )


@login_required
@require_POST
def scan_tiff_preview(request: HttpRequest) -> HttpResponse:
    """Convert TIFF upload into a PNG preview for browser rendering and AI.

    Returns:
        An HTTP response with the png or a JSON error if something went wrong

    """
    upload = request.FILES.get("file")
    if not upload:
        return JsonResponse({"error": "Missing file"}, status=400)

    if (upload.size or 0) > MAX_TIFF_PREVIEW_BYTES:
        return JsonResponse({"error": "File too large"}, status=400)

    ext = pathlib.Path(upload.name or "").suffix.lower()
    if ext not in {".tif", ".tiff"}:
        return JsonResponse({"error": "Only TIFF files are supported"}, status=400)

    try:
        png_bytes = convert_tiff_to_png_bytes(upload)
        return HttpResponse(png_bytes, content_type="image/png")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return JsonResponse({"error": f"Failed to convert TIFF: {exc}"}, status=400)
