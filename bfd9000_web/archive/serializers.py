"""Serializers for the archive app.

This module defines the serializers for converting complex data types (models)
to and from native Python datatypes that can then be
easily rendered into JSON, XML, or other content types.
It includes specialized logic for file uploads and validation.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    NotRequired,
    TypedDict,
    cast,
    final,
    override,
)

import magic
import trimesh
from BFD9000.conf import AuthUser
from BFD9000.settings import StorageURIs
from django.core.files.base import ContentFile
from django.db import transaction
from rest_framework import serializers

from .constants import (
    RASTER_MIMES,
    RECORD_TYPE_MODALITY_MAP,
    SCAN_MIMES,
    SYSTEM_IDENTIFIER_BOLTON_SUBJECT,
    SYSTEM_MODALITY,
    SYSTEM_RECORD_TYPE,
)
from .media_utils import TransformOp, generate_thumbnail_webp_bytes
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
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from django.db.models import QuerySet
    from rest_framework.request import Request

    from archive.storage.django import ByteFile

    from .management.importers.base import Stringable


logger = logging.getLogger(__name__)
LATERAL_RECORD_TYPE_CODE = "L"


def _encode_patient_orientation(value: list[str] | None) -> str:
    if not value:
        return ""
    return "\\".join(value)


def _decode_patient_orientation(value: str) -> list[str]:
    if not value:
        return []
    return [part for part in value.split("\\") if part]


def _get_preferred_identifier(identifiers: Iterable[Identifier]) -> str | None:
    official_identifier: str | None = None
    bolton_identifier: str | None = None
    first_identifier: str | None = None

    for identifier in identifiers:
        if first_identifier is None:
            first_identifier = identifier.value
        if official_identifier is None and identifier.use == "official":
            official_identifier = identifier.value
        if (
            bolton_identifier is None
            and identifier.system == SYSTEM_IDENTIFIER_BOLTON_SUBJECT
        ):
            bolton_identifier = identifier.value

    return official_identifier or bolton_identifier or first_identifier


def _compute_age_years(encounter: Encounter, subject: Subject) -> float | None:
    """Return age in decimal years for the given encounter+subject

    Args:
        encounter: The encouner of which to calculate the age
        subject: The subject to calculate the age for

    Returns:
        Age in years as a float, or None if not computable

    """
    birth_date: datetime.date | None = getattr(subject, "birth_date", None)
    if encounter.procedure_occurrence_age:
        return round(encounter.procedure_occurrence_age.days / 365.25, 2)
    if encounter.actual_period_start and birth_date:
        return round((encounter.actual_period_start - birth_date).days / 365.25, 2)
    return None


@final
class CodingSerializer(serializers.ModelSerializer[Coding]):
    """Serializer for Coding model."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Meta class for CodingSerializer"""

        model: type = Coding
        fields: str = "__all__"


@final
class DeviceSerializer(serializers.ModelSerializer[Device]):
    """Serializer for Device model"""

    modalities: serializers.SerializerMethodField = serializers.SerializerMethodField()

    def get_modalities(self, obj: Device) -> list[dict[str, Any]]:  # pyright: ignore[reportExplicitAny]  # noqa: PLR6301
        """Get all coded modalities for a given device

        Args:
            obj: The device to query

        Returns:
            A list of dictionaries representing Codings

        """
        return [dict(c) for c in CodingSerializer(obj.modalities.all(), many=True).data]  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType, reportUnknownArgumentType]

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Meta class for DeviceSerializer"""

        model: type = Device
        fields: Sequence[str] = (
            "id",
            "serial_number",
            "display_name",
            "manufacturer",
            "model_number",
            "version",
            "modalities",
        )


@final
class IdentifierSerializer(serializers.ModelSerializer[Identifier]):
    """Serializer for Identifier model."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Serializer metadata."""

        model: type = Identifier
        fields: str = "__all__"


@final
class AddressSerializer(serializers.ModelSerializer[Address]):
    """Serializer for Address model."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Serializer metadata."""

        model: type = Address
        fields: str = "__all__"


@final
class LocationSerializer(serializers.ModelSerializer[Location]):
    """Serializer for Location model."""

    address = AddressSerializer(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Serializer metadata."""

        model: type = Location
        fields: str = "__all__"


@final
class CollectionSerializer(serializers.ModelSerializer[Collection]):
    """Serializer for Collection model."""

    address = AddressSerializer(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Serializer metadata."""

        model: type = Collection
        fields: str = "__all__"


@final
class SeriesSerializer(serializers.ModelSerializer[Series]):
    """Serializer for Series model."""

    modality = CodingSerializer(read_only=True)
    acquisition_location = LocationSerializer(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """SeriesSerialize Metadata"""

        model: type = Series
        fields: str = "__all__"


@final
class SubjectSerializer(serializers.ModelSerializer[Subject]):
    """Serializer for Subject model."""

    address = AddressSerializer(read_only=True)
    identifiers = IdentifierSerializer(many=True, read_only=True)
    ethnicity = CodingSerializer(read_only=True)
    skeletal_pattern = CodingSerializer(read_only=True)
    palatal_cleft = CodingSerializer(read_only=True)
    subject_identifier = serializers.SerializerMethodField()
    identifier_value = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    identifier_system = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    collection = serializers.SlugRelatedField(  # pyright: ignore[reportUnknownVariableType]
        slug_field="short_name",
        queryset=Collection.objects.all(),
        allow_null=True,
        required=False,
    )

    encounter_count = serializers.IntegerField(read_only=True)
    record_count = serializers.IntegerField(read_only=True)
    physical_record_count = serializers.IntegerField(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Serializer metadata."""

        model: type = Subject
        fields: str = "__all__"

    def get_subject_identifier(self, obj: Subject) -> str | None:  # noqa: PLR6301
        """Return the preferred identifier for subject display.

        Args:
            obj: The object to obtain the identifier for

        Returns:
            The preferred identifier for this object

        """
        return _get_preferred_identifier(obj.identifiers.all())

    @override
    def create(self, validated_data: dict[str, Any]) -> Subject:  # pyright: ignore[reportExplicitAny]
        identifier_value = cast(
            "str", validated_data.pop("identifier_value", "")
        ).strip()
        identifier_system = cast(
            "str", validated_data.pop("identifier_system", "")
        ).strip()

        if identifier_value and not identifier_system:
            raise serializers.ValidationError(
                {
                    "identifier_system": "identifier_system is required "
                    + "when identifier_value is provided."
                }
            )

        subject = super().create(validated_data)

        if identifier_value:
            identifier, _ = Identifier.objects.get_or_create(
                system=identifier_system,
                value=identifier_value,
                defaults={"use": "official"},
            )
            subject.identifiers.add(identifier)

        return subject


@final
class EncounterSerializer(serializers.ModelSerializer[Encounter]):
    """Serializer for Encounter model."""

    diagnosis = CodingSerializer(read_only=True)
    procedure_code = serializers.PrimaryKeyRelatedField(queryset=Coding.objects.all())  # pyright: ignore[reportUnknownVariableType]
    age_at_encounter = serializers.FloatField(required=False)
    subject = serializers.PrimaryKeyRelatedField(  # pyright: ignore[reportUnknownVariableType]
        queryset=Subject.objects.all(), required=False
    )
    subject_identifier = serializers.SerializerMethodField()

    record_count = serializers.IntegerField(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Serializer metadata."""

        model: type = Encounter
        fields: str = "__all__"
        extra_kwargs: dict[str, dict[str, Any]] = {  # pyright: ignore[reportExplicitAny]  # noqa: RUF012
            "procedure_occurrence_age": {"write_only": True}
        }

    def get_subject_identifier(self, obj: Encounter) -> str | None:  # noqa: PLR6301
        """Return the preferred identifier for the encounter subject.

        Args:
            obj: The object to obtain the identifier for

        Returns:
            The preferred identifier for this object

        """
        subject: Subject | None = getattr(obj, "subject", None)
        if not subject:
            return None
        return _get_preferred_identifier(subject.identifiers.all())

    @override
    def to_representation(self, instance: Encounter) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Convert instance to dictionary representation.

        Returns:
            The dictionary representation of an Encounter

        """
        ret = super().to_representation(instance)
        subject: Subject | None = getattr(instance, "subject", None)
        if subject:
            ret["age_at_encounter"] = _compute_age_years(instance, subject)
        else:
            ret["age_at_encounter"] = None
        return ret

    @override
    def create(self, validated_data: dict[str, Any]) -> Encounter:  # pyright: ignore[reportExplicitAny]
        """Create a new Encounter instance.

        Args:
            validated_data: A validated dictionary representing an Encounter

        Returns:
            An Encounter object constructed from the data

        """
        age = cast("float | None", validated_data.pop("age_at_encounter", None))
        if age is not None:
            validated_data["procedure_occurrence_age"] = datetime.timedelta(
                days=age * 365.25
            )
        return super().create(validated_data)

    @override
    def update(self, instance: Encounter, validated_data: dict[str, Any]) -> Encounter:  # pyright: ignore[reportExplicitAny]
        """Update an existing Encounter instance.

        Args:
            instance: The instance of Encounter to update
            validated_data: A valid dictionary representing an Encounter update

        Returns:
            The updated Encounter object

        """
        age = cast("float | None", validated_data.pop("age_at_encounter", None))
        if age is not None:
            validated_data["procedure_occurrence_age"] = datetime.timedelta(
                days=age * 365.25
            )
        return super().update(instance, validated_data)


@final
class ImagingStudySerializer(serializers.ModelSerializer[ImagingStudy]):
    """Serializer for ImagingStudy model."""

    identifiers = IdentifierSerializer(many=True, read_only=True)
    # Expose nested series under this study for read-only listing
    series = serializers.SerializerMethodField()
    scan_operator_username = serializers.SerializerMethodField()
    scan_operator_display = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Metadata for ImagingStudy"""

        model: type = ImagingStudy
        fields: str = "__all__"

    def get_series(self, obj: ImagingStudy) -> list[dict[str, Any]]:  # pyright: ignore[reportExplicitAny]
        """Returns a list of all associated Series for this study

        Args:
            obj: The study to query against

        Returns:
            List of all associated series

        """
        # Return list of series summaries
        qs: QuerySet[Series] | list[Series] = (
            obj.series.all().select_related("modality")
            if hasattr(obj, "series")
            else []
        )

        return SeriesSerializer(qs, many=True, context=self.context).data  # type: ignore # pyright: ignore[reportUnknownMemberType, reportReturnType, reportUnknownVariableType]

    def _latest_operator(self, obj: ImagingStudy) -> AuthUser | None:  # noqa: PLR6301
        # Use prefetched _operator_records if available (set by ImagingStudyViewSet)
        # to avoid N+1 queries when serializing lists.
        all_records: list[DigitalRecord] = []
        for series in obj.series.all():
            prefetched: list[DigitalRecord] | None = getattr(
                series, "_operator_records", None
            )
            if prefetched is not None:
                all_records.extend(prefetched)
            else:
                # Fallback for non-prefetched usage (e.g. detail view or tests)
                dr = (
                    DigitalRecord.objects.filter(series=series, operator__isnull=False)
                    .select_related("operator")
                    .order_by("-created_at")
                    .first()
                )
                if dr:
                    all_records.append(dr)
        if not all_records:
            return None
        # Sort in Python to get the latest across all series
        all_records.sort(key=lambda r: r.created_at, reverse=True)
        return all_records[0].operator

    def get_scan_operator_username(self, obj: ImagingStudy) -> str | None:
        """Finds the latest operator for an Imaging Study

        Returns:
            The latest operator's username

        """
        operator = self._latest_operator(obj)
        return getattr(operator, "username", None)

    def get_scan_operator_display(self, obj: ImagingStudy) -> str | None:
        """Finds the latest operator for an Imaging Study

        Returns:
            The latest operator's display name

        """
        operator = self._latest_operator(obj)
        if not operator:
            return None
        full_name = operator.get_full_name().strip()
        if full_name:
            return f"{full_name} ({operator.username})"
        return operator.username


@final
class EndpointSerializer(serializers.ModelSerializer[Endpoint]):
    """Serializer for Endpoint model."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Metadata for Endpoint"""

        model: type = Endpoint
        fields: Sequence[str] = (
            "id",
            "name",
            "status",
            "connection_type",
            "address",
            "config",
        )


@final
class ArchiveLocationSerializer(serializers.ModelSerializer[ArchiveLocation]):
    """Serializer for ArchiveLocation model."""

    endpoint = EndpointSerializer(read_only=True)
    endpoint_id = serializers.IntegerField(source="endpoint.id", read_only=True)
    digital_record = serializers.PrimaryKeyRelatedField[DigitalRecord](read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Metadata for ArchiveLocation"""

        model: type = ArchiveLocation
        fields: str = "__all__"


@final
class PhysicalLocationSerializer(serializers.ModelSerializer[PhysicalLocation]):
    """Serializer for PhysicalLocation model."""

    address = AddressSerializer(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Metadata for PhysicalLocation"""

        model: type = PhysicalLocation
        fields: str = "__all__"


@final
class PhysicalRecordSerializer(serializers.ModelSerializer[PhysicalRecord]):
    """Serializer for PhysicalRecord model."""

    record_type = CodingSerializer(read_only=True)
    identifiers = IdentifierSerializer(many=True, read_only=True)
    locations = PhysicalLocationSerializer(many=True, read_only=True)
    encounter_id = serializers.IntegerField(source="encounter.id", read_only=True)
    subject_id = serializers.IntegerField(source="encounter.subject.id", read_only=True)
    subject_identifier = serializers.SerializerMethodField()
    identifier_str = serializers.SerializerMethodField()
    age_at_encounter = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Metadata for PhysicalRecord"""

        model: type = PhysicalRecord
        fields: str = "__all__"

    def get_subject_identifier(self, obj: PhysicalRecord) -> str | None:  # noqa: PLR6301
        """Obtain the preferred identifier for a record

        Returns:
            The preferred identifier, if found

        """
        subject: Subject | None = getattr(obj.encounter, "subject", None)
        if not subject:
            return None
        return _get_preferred_identifier(subject.identifiers.all())

    def get_identifier_str(self, obj: PhysicalRecord) -> str:  # noqa: PLR6301
        """Return the Bolton-style record identifier. Delegates to the model property.

        Returns:
            the Bolton-style record identifier

        """
        return obj.bolton_record_id

    def get_age_at_encounter(self, obj: PhysicalRecord) -> float | None:  # noqa: PLR6301
        """Gets the age of a subject at an encounter

        Args:
            obj: The physical record of the patient encounter

        Returns:
            Decimal age in year as a float, if found

        """
        encounter: Encounter | None = getattr(obj, "encounter", None)
        if not encounter:
            return None
        subject: Subject | None = getattr(encounter, "subject", None)
        if not subject:
            return None
        return _compute_age_years(encounter, subject)


@final
class DigitalRecordSerializer(serializers.ModelSerializer[DigitalRecord]):
    """Serializer for DigitalRecord model."""

    identifiers = IdentifierSerializer(many=True, read_only=True)
    series_id = serializers.IntegerField(source="series.id", read_only=True)
    record_type = CodingSerializer(read_only=True)
    series_modality = CodingSerializer(source="series.modality", read_only=True)
    physical_record_id = serializers.PrimaryKeyRelatedField[PhysicalRecord](
        read_only=True, allow_null=True
    )
    device = DeviceSerializer(read_only=True)
    operator = serializers.StringRelatedField[AuthUser](read_only=True)

    encounter_id = serializers.IntegerField(
        source="series.imaging_study.encounter.id", read_only=True
    )
    encounter = serializers.IntegerField(
        source="series.imaging_study.encounter.id", read_only=True
    )
    imaging_study = serializers.IntegerField(
        source="series.imaging_study.id", read_only=True
    )
    subject_id = serializers.IntegerField(
        source="series.imaging_study.encounter.subject.id", read_only=True
    )
    subject_identifier = serializers.SerializerMethodField()
    identifier_str = serializers.SerializerMethodField()
    encounter_date = serializers.DateField(
        source="series.imaging_study.encounter.actual_period_start", read_only=True
    )
    actual_period_start_precision = serializers.CharField(
        source="series.imaging_study.encounter.actual_period_start_precision",
        read_only=True,
    )
    actual_period_start_uncertain = serializers.BooleanField(
        source="series.imaging_study.encounter.actual_period_start_uncertain",
        read_only=True,
    )
    age_at_encounter = serializers.SerializerMethodField()
    patient_orientation = serializers.SerializerMethodField()
    acquisition_datetime = serializers.DateTimeField(read_only=True)
    acquisition_date = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    archive_locations = ArchiveLocationSerializer(many=True, read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Metadata for DigitalRecord"""

        model: type = DigitalRecord
        fields: str = "__all__"

    def get_age_at_encounter(self, obj: DigitalRecord) -> float | None:  # noqa: PLR6301
        """Gets the age of a subject at an encounter

        Args:
            obj: The physical record of the patient encounter

        Returns:
            Decimal age in year as a float, if found

        """
        encounter: Encounter | None = getattr(
            obj.series.imaging_study, "encounter", None
        )
        if not encounter:
            return None
        subject: Subject | None = getattr(encounter, "subject", None)
        if not subject:
            return None
        return _compute_age_years(encounter, subject)

    def get_identifier_str(self, obj: DigitalRecord) -> str:  # noqa: PLR6301
        """Return the Bolton-style record identifier. Delegates to the model property.

        Returns:
            the Bolton-style record identifier

        """
        return obj.bolton_record_id

    def get_subject_identifier(self, obj: DigitalRecord) -> str | None:  # noqa: PLR6301
        """Return the preferred identifier for the digital record.

        Args:
            obj: The object to obtain the identifier for

        Returns:
            The preferred identifier for this object, if found

        """
        encounter: Encounter | None = getattr(
            obj.series.imaging_study, "encounter", None
        )
        subject: Subject | None = getattr(encounter, "subject", None)
        if not subject:
            return None
        return _get_preferred_identifier(subject.identifiers.all())

    def get_acquisition_date(self, obj: DigitalRecord) -> datetime.date | None:  # noqa: PLR6301
        """Return the acquisition date for the digital record.

        Args:
            obj: The object to obtain the acquisition date for

        Returns:
            The acquisition date for this object, if found

        """
        acquisition_datetime: datetime.datetime | None = getattr(
            obj, "acquisition_datetime", None
        )
        if not acquisition_datetime:
            return None
        return acquisition_datetime.date()

    def get_file_size(self, obj: DigitalRecord) -> int | None:  # noqa: PLR6301
        """Return the file size for the digital record.

        Args:
            obj: The object to obtain the file size for

        Returns:
            The file size for this object, if found

        """
        if getattr(obj, "source_file", None):
            try:
                return obj.display_size
            except Exception:
                return None
        return None

    def get_patient_orientation(self, obj: DigitalRecord) -> list[str]:  # noqa: PLR6301
        """Return the patient orientation for the digital record.

        Args:
            obj: The object to obtain the patient orientation for

        Returns:
            The patient orientation for this object

        """
        return _decode_patient_orientation(
            str(getattr(obj, "patient_orientation", "") or "")
        )

    def get_thumbnail_url(self, obj: DigitalRecord) -> str | None:  # noqa: PLR6301
        """Return the thumbnail url for the digital record.

        Args:
            obj: The object to obtain the thumbnail url for

        Returns:
            The thumbnail url for this object, if found

        """
        if (
            not obj.thumbnail
            or not obj.thumbnail.name
            or not obj.thumbnail.storage.exists(obj.thumbnail.name)
        ) and (obj.source_file):
            logger.warning(f"Thumbnail does not exist, regenerating for {obj.id}")
            name = obj.source_file.name or str(uuid.uuid4())
            thumb_bytes = generate_thumbnail_webp_bytes(
                obj.source_file,
                name,
                transform_ops=DigitalRecordUploadSerializer().validate_image_transform_ops(
                    obj.image_transform_ops  # pyright: ignore[reportAny]
                ),
            )
            if not thumb_bytes:
                logger.warning("No thumbnail made")
                return None

            with transaction.atomic():
                refreshed_obj = DigitalRecord.objects.select_for_update().get(id=obj.id)
                logger.info(f"Regeneration successful for {refreshed_obj.id}")
                refreshed_obj.thumbnail.save(  # pyright: ignore[reportUnknownMemberType]
                    f"{name}.jpg", ContentFile(thumb_bytes), save=True
                )
                obj.thumbnail = refreshed_obj.thumbnail

        try:
            return obj.thumbnail.url
        except Exception as e:
            logger.warning(f"Thumbnail fetch failed with {e}")
            return None

    def get_image_url(self, obj: DigitalRecord) -> str | None:  # noqa: PLR6301
        """Return the image url for the digital record.

        Args:
            obj: The object to obtain the image url for

        Returns:
            The image url for this object, if found

        """
        if getattr(obj, "source_file", None):
            try:
                return obj.source_file.url
            except Exception:
                return None
        return None


class DigitalRecordUploadValidatedDict(TypedDict):
    """The Validated Type of the input dictionary

    for creating a DigitalRecord

    """

    # Required Fields (No required=False, no allow_null=True)
    file: ByteFile
    record_type: Coding

    # Optional Fields (marked with required=False or allow_null=True)
    thumbnail_preview: NotRequired[ByteFile]
    modality: NotRequired[Coding | None]
    acquisition_date: NotRequired[datetime.date]
    patient_orientation: NotRequired[
        list[str]
    ]  # Output of validate_patient_orientation
    image_transform_ops: NotRequired[
        list[TransformOp]
    ]  # Output of validate_image_transform_ops
    encounter: NotRequired[Encounter]
    physical_record: NotRequired[PhysicalRecord | None]
    device_serial: NotRequired[str]
    device_manufacturer: NotRequired[str]
    device_model: NotRequired[str]


@dataclass
class DigitalRecordUploadParsedData:
    """Validated and reconstructed input data"""

    file: ByteFile
    rt_coding: Coding
    mod_coding: Coding
    thumbnail_preview: ByteFile | None
    acquisition_date: datetime.date | None
    patient_orientation: list[str] | None
    image_transform_ops: list[TransformOp]
    encounter: Encounter
    collection: Collection
    physical_record_input: PhysicalRecord | None
    device_serial: str
    device_manufacturer: str
    device_model: str

    @classmethod
    def from_validated_dict(
        cls,
        validated_data: DigitalRecordUploadValidatedDict,
        context_encounter: Callable[[], Encounter | None],
        infer_mod_coding: Callable[[Coding], Coding],
    ) -> DigitalRecordUploadParsedData:
        """Creates a validated Upload object from input data

        Returns:
            A validated upload object

        Raises:
            ValidationError: If encounter or collection does not exist

        """
        file = validated_data["file"]
        rt_coding = validated_data["record_type"]

        thumbnail_preview = validated_data.pop("thumbnail_preview", None)
        mod_coding = validated_data.pop("modality", None) or infer_mod_coding(rt_coding)
        acquisition_date = validated_data.pop("acquisition_date", None)
        patient_orientation = validated_data.pop(
            "patient_orientation",
            ["A", "F"] if rt_coding.code == LATERAL_RECORD_TYPE_CODE else None,
        )
        image_transform_ops = validated_data.pop("image_transform_ops", [])
        physical_record_input = validated_data.pop("physical_record", None)
        encounter = validated_data.pop(
            "encounter",
            physical_record_input.encounter
            if physical_record_input
            else context_encounter(),
        )
        if encounter is None:
            raise serializers.ValidationError(
                {
                    "encounter": "This field is required "
                    + "(either in URL, body, or via physical_record)."
                }
            )
        device_serial = validated_data.pop("device_serial", "").strip()
        device_manufacturer = validated_data.pop("device_manufacturer", "").strip()
        device_model = validated_data.pop("device_model", "").strip()
        subject = encounter.subject
        collection = subject.collection
        if collection is None:
            raise serializers.ValidationError(
                {
                    "collection": f"Subject {subject.id} must be assigned "
                    + "to a collection before uploading records."
                }
            )

        return cls(
            file=file,
            rt_coding=rt_coding,
            mod_coding=mod_coding,
            thumbnail_preview=thumbnail_preview,
            acquisition_date=acquisition_date,
            patient_orientation=patient_orientation,
            image_transform_ops=image_transform_ops,
            encounter=encounter,
            collection=collection,
            physical_record_input=physical_record_input,
            device_serial=device_serial,
            device_manufacturer=device_manufacturer,
            device_model=device_model,
        )


@final
class DigitalRecordUploadSerializer(serializers.ModelSerializer[DigitalRecord]):
    """Serializer for uploading digital records with files.

    Handles file validation, metadata extraction, and creation of related
    ImagingStudy, Series, PhysicalRecord,
    and DigitalRecord objects within a transaction.
    """

    file = serializers.FileField(write_only=True)
    thumbnail_preview = serializers.FileField(required=False, write_only=True)

    # Use SlugRelatedField for idiomatic lookup by 'code'
    record_type = serializers.SlugRelatedField(  # pyright: ignore[reportUnknownVariableType]
        slug_field="code",
        queryset=Coding.objects.filter(system=SYSTEM_RECORD_TYPE),
        write_only=True,
    )
    modality = serializers.SlugRelatedField(  # pyright: ignore[reportUnknownVariableType]
        slug_field="code",
        queryset=Coding.objects.filter(system=SYSTEM_MODALITY),
        required=False,
        allow_null=True,
        write_only=True,
    )

    acquisition_date = serializers.DateField(required=False, write_only=True)
    patient_orientation = serializers.ListField(
        child=serializers.CharField(max_length=1),
        min_length=2,
        max_length=2,
        required=False,
        write_only=True,
    )
    image_transform_ops = serializers.JSONField(required=False, write_only=True)

    # Allow encounter to be passed in body (for flat endpoint) or context (for nested)
    encounter = serializers.PrimaryKeyRelatedField(  # pyright: ignore[reportUnknownVariableType]
        queryset=Encounter.objects.all(), required=False, write_only=True
    )

    physical_record = serializers.PrimaryKeyRelatedField(  # pyright: ignore[reportUnknownVariableType]
        queryset=PhysicalRecord.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )

    # Device info from the acquisition scanner (optional)
    device_serial = serializers.CharField(
        required=False, allow_blank=True, write_only=True
    )
    device_manufacturer = serializers.CharField(
        required=False, allow_blank=True, write_only=True
    )
    device_model = serializers.CharField(
        required=False, allow_blank=True, write_only=True
    )

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Metadata for DigitalRecord (uploaded)"""

        model: type = DigitalRecord
        fields: Sequence[str] = (
            "id",
            "file",
            "thumbnail_preview",
            "record_type",
            "modality",
            "acquisition_date",
            "encounter",
            "physical_record",
            "patient_orientation",
            "image_transform_ops",
            "device_serial",
            "device_manufacturer",
            "device_model",
        )

    def validate_patient_orientation(self, value: list[Stringable]) -> list[str]:  # noqa: PLR6301
        """Validates patient orientation given an unknown input

        Args:
            value: The unknown value

        Returns:
            The verified patient orientation, if valid

        Raises:
            ValidationError: If value was not valid

        """
        valid = {"A", "P", "R", "L", "H", "F"}
        upper = [str(v).upper() for v in value]
        if any(v not in valid for v in upper):
            raise serializers.ValidationError(
                "patient_orientation values must be one of A, P, R, L, H, F"
            )
        return upper

    def validate_image_transform_ops(  # noqa: PLR6301
        self,
        value: str | list[dict[str, Any]],  # pyright: ignore[reportExplicitAny]
    ) -> list[TransformOp]:
        """Validates image transforms given an unknown input

        Args:
            value: The unknown value

        Returns:
            The verified image transforms, if valid

        Raises:
            ValidationError: If value was not valid

        """
        parse_val: Any = value  # pyright: ignore[reportExplicitAny]
        if isinstance(value, str):
            try:
                parse_val = json.loads(value)  # pyright: ignore[reportAny]
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError(
                    "image_transform_ops must be valid JSON"
                ) from exc

        if not isinstance(parse_val, list):
            raise serializers.ValidationError("image_transform_ops must be a list")

        normalized: list[TransformOp] = []
        for op in parse_val:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(op, dict):
                raise serializers.ValidationError("each transform op must be an object")

            try:
                rotation = int(op.get("rotation", 0))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError("rotation must be a number") from exc
            rotation %= 360
            if rotation not in {0, 90, 180, 270}:
                raise serializers.ValidationError(
                    "rotation must be one of 0, 90, 180, 270"
                )
            flip = bool(op.get("flip", False))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
            normalized.append({"rotation": rotation, "flip": flip})

        return normalized

    def _infer_modality(self, record_type: Coding) -> Coding:  # noqa: PLR6301
        record_type_code = str(getattr(record_type, "code", "") or "")
        modality_code = RECORD_TYPE_MODALITY_MAP.get(record_type_code)

        if not modality_code:
            raise serializers.ValidationError(
                {
                    "modality": f"""Unable to infer modality for record type {
                        record_type_code or "unknown"
                    }."""
                }
            )

        modality = Coding.objects.filter(
            system=SYSTEM_MODALITY, code=modality_code
        ).first()
        if modality is None:
            raise serializers.ValidationError(
                {
                    "modality": f"""Modality code {modality_code} not found in system {
                        SYSTEM_MODALITY
                    }."""
                }
            )
        return modality

    @override
    def to_representation(self, instance: DigitalRecord) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Convert instance to dictionary representation.

        Returns:
            The dictionary representation of an Encounter

        """
        # Return as dict, not DRF ReturnDict, for typing compatibility
        return dict(DigitalRecordSerializer(instance, context=self.context).data)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]

    def validate_file(  # noqa: PLR6301
        self, value: ByteFile
    ) -> ByteFile:
        """Validates a file given an unknown input

        Args:
            value: The unknown value

        Returns:
            The verified file, if valid

        Raises:
            ValidationError: If value was not valid

        """
        if (value.size or 0) > 100 * 1024 * 1024:
            logger.warning("Uploaded file was too large")
            raise serializers.ValidationError("File too large (max 100MB)")

        initial_pos: int = value.tell()  # pyright: ignore[reportAny]
        value.seek(0)  # pyright: ignore[reportAny]

        try:
            header_sample: bytes = value.read(2048)  # pyright: ignore[reportAny]
            mime_type = magic.from_buffer(header_sample, mime=True)
            value.seek(0)  # pyright: ignore[reportAny]
        except Exception as e:
            logger.error("Failed to validate file from MIME")
            raise e
        finally:
            with contextlib.suppress(Exception):
                value.seek(initial_pos)  # pyright: ignore[reportAny]
        if mime_type in RASTER_MIMES:
            return value

        if mime_type not in SCAN_MIMES:
            logger.error(f"Unsupported file format (Detected: {mime_type})")
            raise serializers.ValidationError(
                f"Unsupported file format (Detected: {mime_type})"
            )

        try:
            # Load the mesh using trimesh (executes structural verification checks)
            mesh = trimesh.load(value, file_type="stl")  # pyright: ignore[reportUnknownMemberType]

            if mesh.is_empty:
                raise serializers.ValidationError(
                    "The 3D asset contains no valid geometry."
                )

            # Export the original, unmodified mesh directly to a Binary STL byte buffer.
            # This automatically drops heavy ASCII layout text inflation.
            minimized_bytes = cast("bytes", mesh.export(file_type="stl"))  # type: ignore # pyright: ignore[reportCallIssue, reportUnknownMemberType]

            new_filename = (
                f"{getattr(value, 'name', str(uuid.uuid4())).rsplit('.', 1)[0]}.stl"
            )

            return ContentFile(minimized_bytes, name=new_filename)

        except Exception as mesh_err:
            logger.error("3D asset not valid")
            if isinstance(mesh_err, serializers.ValidationError):
                raise mesh_err
            raise serializers.ValidationError(
                "Structural validation failed. Asset does not contain valid 3D data."
            ) from mesh_err
        finally:
            with contextlib.suppress(Exception):
                value.seek(initial_pos)  # pyright: ignore[reportAny]

    @staticmethod
    def _resolve_physical_record(
        payload: DigitalRecordUploadParsedData, device: Device | None
    ) -> PhysicalRecord:
        """Resolve a physical record for a digital record

        Args:
            payload: The input arguments for the construction of the DR
            device: The device associated with the record

        Returns:
            The resolved PR

        Raises:
            ValidationError: if multiple PRs exist for an encounter

        """
        if payload.physical_record_input is not None:
            physical_record = payload.physical_record_input
            # If the user corrected the record_type in the UI,
            # propagate the correction to the PhysicalRecord
            # so the physical archive stays accurate.
            if physical_record.record_type != payload.rt_coding:
                physical_record.record_type = payload.rt_coding
                physical_record.save(update_fields=["record_type"])
            return physical_record

        pr_matches = list(
            PhysicalRecord.objects.filter(
                record_type=payload.rt_coding,
                encounter=payload.encounter,
            )
        )
        if len(pr_matches) > 1:
            raise serializers.ValidationError(
                {
                    "physical_record": (
                        "Multiple physical records exist for this "
                        + "encounter and record type. "
                        + "Provide 'physical_record' explicitly "
                        + "to identify which one to link."
                    )
                }
            )

        return (
            pr_matches[0]
            if pr_matches
            else PhysicalRecord.objects.create(
                record_type=payload.rt_coding,
                encounter=payload.encounter,
                operator="Unknown",
                device=device,
            )
        )

    # TODO: refactor this, it's way too complex and prone to erroring
    @override
    def create(self, validated_data: DigitalRecordUploadValidatedDict) -> DigitalRecord:
        """Create a new DigitalRecord instance.

        Will raise a ValidationError if any input data is invalid

        Args:
            validated_data: A validated dictionary representing a DigitalRecord

        Returns:
            A DigitalRecord object constructed from the data

        """
        input: DigitalRecordUploadParsedData = (
            DigitalRecordUploadParsedData.from_validated_dict(
                validated_data,
                lambda: self.context.get("encounter"),
                self._infer_modality,
            )
        )

        request: Request | None = self.context.get("request")
        operator = None
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            operator = request.user

        file_uuid = str(uuid.uuid4())
        ext = Path(input.file.name or "").suffix.lower()
        target_filename = f"{file_uuid}{ext}"

        thumb_bytes: bytes | None = None
        try:
            if input.thumbnail_preview is not None:
                thumb_bytes = generate_thumbnail_webp_bytes(
                    input.thumbnail_preview,
                    input.thumbnail_preview.name or "",
                    transform_ops=None,
                )
            else:
                input.file.seek(0)  # pyright: ignore[reportAny]
                thumb_bytes = generate_thumbnail_webp_bytes(
                    input.file,
                    target_filename,
                    transform_ops=input.image_transform_ops,
                )
        except Exception:
            logger.warning(
                "Thumbnail generation failed for %s", target_filename, exc_info=True
            )

        with transaction.atomic():
            # Resolve or auto-create Device by
            # (serial, manufacturer, model) when serial is provided
            device: Device | None = None
            if input.device_serial:
                display_name = (
                    " ".join(
                        filter(None, [input.device_manufacturer, input.device_model])
                    )
                    or input.device_serial
                )
                device, _ = Device.objects.get_or_create(
                    serial_number=input.device_serial,
                    manufacturer=input.device_manufacturer,
                    model_number=input.device_model,
                    defaults={
                        "display_name": display_name,
                    },
                )

            study, _ = ImagingStudy.objects.get_or_create(
                encounter=input.encounter, defaults={"collection": input.collection}
            )
            if study.collection != input.collection:
                study.collection = input.collection
                study.save(update_fields=["collection"])

            # Series is now identified only by modality+imaging_study
            series, _ = Series.objects.get_or_create(
                imaging_study=study,
                modality=input.mod_coding,
            )

            # PHYSICAL RECORD: Use explicitly provided one,
            # or get/create by (record_type, encounter)
            physical_record = self._resolve_physical_record(input, device)

            digital_record = DigitalRecord(
                series=series,
                physical_record=physical_record,
                record_type=input.rt_coding,
                acquisition_datetime=(
                    datetime.datetime.combine(
                        input.acquisition_date,
                        datetime.time.min,
                        tzinfo=datetime.UTC,
                    )
                    if input.acquisition_date
                    else None
                ),
                operator=operator,
                patient_orientation=_encode_patient_orientation(
                    input.patient_orientation
                ),
                image_transform_ops=input.image_transform_ops,
                device=device,
            )
            # Bind files natively using Django's clean backend stream handler
            input.file.seek(0)  # pyright: ignore[reportAny]
            digital_record.source_file.save(  # pyright: ignore[reportUnknownMemberType]
                f"{StorageURIs.BOX}://{target_filename}", input.file, save=False
            )

            if thumb_bytes:
                digital_record.thumbnail.save(  # pyright: ignore[reportUnknownMemberType]
                    f"{file_uuid}.jpg", ContentFile(thumb_bytes), save=False
                )

            # Run validators and save the record to the database
            digital_record.full_clean()
            digital_record.save()

            return digital_record
