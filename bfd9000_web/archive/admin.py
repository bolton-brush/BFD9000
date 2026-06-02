"""Admin configuration for archive models."""

from typing import TYPE_CHECKING, cast, final, override

from django.contrib import admin
from django.db.models import Model
from django.forms import ModelForm
from django.http import HttpRequest
from django_stubs_ext import FieldsetSpec

from .models import (
    Address,
    ArchiveLocation,
    Coding,
    Collection,
    Device,
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
    TimestampedModel,
)

if TYPE_CHECKING:
    from BFD9000.settings import AUTH_USER_MODEL


class TimestampedAdmin(admin.ModelAdmin[TimestampedModel]):
    """Base admin class with automatic user tracking for created_by and modified_by"""

    readonly_fields = (  # pyright: ignore[reportUnannotatedClassAttribute]
        "created_at",
        "updated_at",
        "created_by",
        "modified_by",
    )

    @override
    def save_model(
        self,
        request: HttpRequest,
        obj: TimestampedModel,
        form: ModelForm[TimestampedModel],
        change: bool,
    ) -> None:
        """Automatically set created_by and modified_by based on the current user

        Args:
            request: The request of which user modified the model
            obj: The model that was create/modified
            form: ?
            change: If the model is being modified (or created)

        """
        if not change:  # Creating new object
            obj.created_by = cast("AUTH_USER_MODEL", request.user)
        obj.modified_by = cast("AUTH_USER_MODEL", request.user)
        super().save_model(request, obj, form, change)

    @override
    def get_fieldsets(
        self, request: HttpRequest, obj: TimestampedModel | None = None
    ) -> FieldsetSpec:
        """Add audit fields section to all admin forms

        Args:
            request: The request which contains the fields
            obj: The object to update

        Returns:
            All fields for this request

        """
        fieldsets = super().get_fieldsets(request, obj)

        # Convert to list if it's a tuple
        fieldsets = list(fieldsets) if fieldsets else []

        # Add audit section if not already present
        if fieldsets and not any("Audit Information" in str(fs) for fs in fieldsets):
            fieldsets.append(
                (
                    None,
                    {
                        "fields": [
                            "created_at",
                            "created_by",
                            "updated_at",
                            "modified_by",
                        ],
                        "classes": ["collapse"],
                    },
                )
            )

        return fieldsets


@final
@admin.register(Coding)
class CodingAdmin(TimestampedAdmin):
    """Admin settings for Coding entries."""

    list_display = ("system", "code", "display", "version", "created_at")
    list_filter = ("system",)
    search_fields = ("system", "code", "display", "meaning")
    fieldsets = (
        (None, {"fields": ("system", "version", "code", "display", "meaning")}),
    )


@final
@admin.register(Identifier)
class IdentifierAdmin(TimestampedAdmin):
    """Admin settings for Identifier entries."""

    list_display = ("system", "value", "use", "created_at")
    list_filter = ("use",)
    search_fields = ("system", "value")
    fieldsets = ((None, {"fields": ("use", "system", "value")}),)


@final
@admin.register(Address)
class AddressAdmin(TimestampedAdmin):
    """Admin settings for Address entries."""

    list_display = ("line1", "city", "state", "country", "postal_code")
    list_filter = ("country", "state")
    search_fields = ("line1", "line2", "city", "state", "postal_code")
    fieldsets = (
        (None, {"fields": ("use", "type")}),
        (
            "Address Details",
            {
                "fields": (
                    "line1",
                    "line2",
                    "city",
                    "district",
                    "state",
                    "postal_code",
                    "country",
                )
            },
        ),
    )


@final
@admin.register(Collection)
class CollectionAdmin(TimestampedAdmin):
    """Admin settings for collections/datasets."""

    list_display = (
        "short_name",
        "full_name",
        "curator",
        "institution",
        "start_date",
        "end_date",
    )
    list_filter = ("start_date", "end_date")
    search_fields = ("short_name", "full_name", "curator", "institution", "description")
    fieldsets = (
        (None, {"fields": ("short_name", "full_name", "description")}),
        ("Responsible Parties", {"fields": ("curator", "institution", "address")}),
        ("Timeframe", {"fields": ("start_date", "end_date")}),
    )


@final
@admin.register(Subject)
class SubjectAdmin(TimestampedAdmin):
    """Admin settings for subjects/patients."""

    list_display = (
        "humanname_family",
        "humanname_given",
        "gender",
        "birth_date",
        "created_at",
    )
    list_filter = ("gender", "birth_date")
    search_fields = ("humanname_family", "humanname_given")
    filter_horizontal = ("identifiers",)
    fieldsets = (
        (
            "Personal Information",
            {"fields": ("humanname_family", "humanname_given", "gender", "birth_date")},
        ),
        ("Contact", {"fields": ("address",)}),
        (
            "Medical Information",
            {"fields": ("ethnicity", "skeletal_pattern", "palatal_cleft")},
        ),
        ("Identifiers", {"fields": ("identifiers",)}),
    )


@final
@admin.register(Encounter)
class EncounterAdmin(TimestampedAdmin):
    """Admin settings for encounters/visits."""

    list_display = (
        "subject",
        "actual_period_start",
        "actual_period_end",
        "procedure_code",
        "created_at",
    )
    list_filter = ("actual_period_start", "actual_period_end")
    search_fields = ("subject__humanname_family", "subject__humanname_given")
    autocomplete_fields = ("subject",)
    fieldsets = (
        (None, {"fields": ("subject",)}),
        ("Timeframe", {"fields": ("actual_period_start", "actual_period_end")}),
        (
            "Medical Details",
            {
                "fields": (
                    "diagnosis",
                    "procedure_code",
                    "procedure_occurrence_age",
                )
            },
        ),
    )


@final
@admin.register(Location)
class LocationAdmin(TimestampedAdmin):
    """Admin settings for scan locations."""

    list_display = ("name", "address", "created_at")
    search_fields = ("name",)
    fieldsets = ((None, {"fields": ("name", "address")}),)


@final
@admin.register(ImagingStudy)
class ImagingStudyAdmin(TimestampedAdmin):
    """Admin settings for imaging studies."""

    list_display = (
        "encounter",
        "collection",
        "study_instance_uid",
        "created_at",
    )
    list_filter = ("collection", "created_at")
    search_fields = (
        "encounter__subject__humanname_family",
        "encounter__subject__humanname_given",
        "study_instance_uid",
    )
    autocomplete_fields = ("encounter",)
    filter_horizontal = ("identifiers",)
    fieldsets = (
        (None, {"fields": ("encounter", "collection")}),
        (
            "Study Details",
            {"fields": ("study_instance_uid", "description", "endpoint")},
        ),
        ("Identifiers", {"fields": ("identifiers",)}),
    )


@final
@admin.register(Series)
class SeriesAdmin(TimestampedAdmin):
    """Admin settings for series."""

    list_display = (
        "imaging_study",
        "modality",
        "series_instance_uid",
        "created_at",
    )
    list_filter = ("modality", "created_at")
    search_fields = (
        "series_instance_uid",
        "description",
        "imaging_study__encounter__subject__humanname_family",
        "imaging_study__encounter__subject__humanname_given",
    )
    autocomplete_fields = ("imaging_study", "modality", "acquisition_location")
    fieldsets = (
        (None, {"fields": ("imaging_study", "series_instance_uid")}),
        ("Classification", {"fields": ("modality", "description")}),
        ("Acquisition", {"fields": ("acquisition_location",)}),
    )


@final
@admin.register(PhysicalLocation)
class PhysicalLocationAdmin(admin.ModelAdmin[PhysicalLocation]):
    """Admin settings for physical locations."""

    list_display = ("id", "cabinet", "shelf", "slot", "address", "raw")
    list_filter = ("cabinet", "shelf")
    search_fields = ("cabinet", "shelf", "slot", "raw")
    autocomplete_fields = ("address",)


@final
@admin.register(PhysicalRecord)
class PhysicalRecordAdmin(admin.ModelAdmin[PhysicalRecord]):
    """Admin settings for physical records."""

    list_display = (
        "id",
        "encounter",
        "record_type_display",
        "acquisition_datetime",
        "operator",
    )
    list_filter = ("record_type",)
    search_fields = (
        "id",
        "encounter__subject__humanname_family",
        "encounter__subject__humanname_given",
    )
    autocomplete_fields = ("encounter", "record_type", "device")
    filter_horizontal = ("identifiers", "locations")
    fieldsets = (
        (None, {"fields": ("encounter", "record_type", "identifiers")}),
        ("Acquisition", {"fields": ("acquisition_datetime", "operator", "device")}),
        ("Physical Locations", {"fields": ("locations",)}),
    )

    def record_type_display(self, obj: PhysicalRecord) -> str:  # noqa: PLR6301
        """Get the record type display code for a Physical Record

        Args:
            obj: The physical record

        Returns:
            The record type display code

        """
        return obj.record_type.code if obj.record_type else "—"

    record_type_display.short_description = "Record Type"  # pyright: ignore[reportFunctionMemberAccess]


@final
class ArchiveLocationInline(admin.TabularInline[ArchiveLocation, Model]):
    """Admin settings for archive locations."""

    model = ArchiveLocation
    extra = 0
    readonly_fields = ("assigned_id", "status", "archived_at", "endpoint")
    can_delete = False


@final
@admin.register(DigitalRecord)
class DigitalRecordAdmin(admin.ModelAdmin[DigitalRecord]):
    """Admin settings for digital records."""

    list_display = (
        "id",
        "series",
        "record_type_display",
        "acquisition_datetime",
        "operator",
    )
    list_filter = ("record_type", "series__modality")
    search_fields = (
        "id",
        "sop_instance_uid",
        "series__imaging_study__encounter__subject__humanname_family",
        "series__imaging_study__encounter__subject__humanname_given",
    )
    autocomplete_fields = (
        "series",
        "record_type",
        "physical_record",
        "operator",
        "device",
    )
    filter_horizontal = ("identifiers",)
    readonly_fields = ("sop_instance_uid",)
    inlines = (ArchiveLocationInline,)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "sop_instance_uid",
                    "series",
                    "physical_record",
                    "record_type",
                    "identifiers",
                )
            },
        ),
        ("Acquisition", {"fields": ("acquisition_datetime", "operator", "device")}),
        (
            "Image Processing",
            {"fields": ("patient_orientation", "image_transform_ops")},
        ),
        ("Files", {"fields": ("source_file", "thumbnail")}),
    )

    def record_type_display(self, obj: DigitalRecord) -> str:  # noqa: PLR6301
        """Get the record type display code for a Digital Record

        Args:
            obj: The digital record

        Returns:
            The record type display code

        """
        return obj.record_type.code if obj.record_type else "—"

    record_type_display.short_description = "Record Type"  # pyright: ignore[reportFunctionMemberAccess]


@final
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin[Device]):
    """Admin settings for device endpoints."""

    list_display = ("display_name", "manufacturer", "model_number", "version")
    search_fields = ("display_name", "manufacturer", "model_number", "serial_number")
    filter_horizontal = ("modalities", "identifiers")


@final
@admin.register(Endpoint)
class EndpointAdmin(TimestampedAdmin):
    """Admin settings for archive endpoints."""

    list_display = ("name", "connection_type", "status", "address", "created_at")
    list_filter = ("status", "connection_type")
    list_editable = ("status",)
    search_fields = ("name", "address")
    fieldsets = (
        (None, {"fields": ("name", "connection_type", "status")}),
        ("Connection", {"fields": ("address",)}),
        ("Configuration", {"fields": ("config", "credentials_encrypted")}),
    )


@final
@admin.register(ArchiveLocation)
class ArchiveLocationAdmin(TimestampedAdmin):
    """Admin settings for archived record locations."""

    list_display = (
        "digital_record",
        "endpoint",
        "assigned_id",
        "status",
        "archived_at",
        "created_at",
    )
    list_filter = ("status", "endpoint__connection_type", "endpoint__status")
    search_fields = (
        "assigned_id",
        "digital_record__id",
        "endpoint__name",
        "endpoint__address",
    )
    autocomplete_fields = ("digital_record", "endpoint")
    fieldsets = (
        (None, {"fields": ("digital_record", "endpoint", "assigned_id")}),
        ("State", {"fields": ("status", "archived_at")}),
    )
