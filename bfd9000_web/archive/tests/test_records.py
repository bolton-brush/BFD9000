"""API tests for record endpoints and uploads."""
# pyright: reportUninitializedInstanceVariable=false, reportUnknownMemberType=false, reportAny=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
# ruff: noqa: S106 S101

from __future__ import annotations

import datetime
import io
import re
from typing import TYPE_CHECKING, Any, override

from BFD9000.conf import AuthUser
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image
from rest_framework import status

from archive.constants import (
    SYSTEM_IDENTIFIER_BOLTON_SUBJECT,
    SYSTEM_MODALITY,
    SYSTEM_ORIENTATION,
    SYSTEM_PROCEDURE,
    SYSTEM_RECORD_TYPE,
)
from archive.models import (
    Coding,
    Collection,
    Device,
    DigitalRecord,
    Encounter,
    Endpoint,
    Identifier,
    ImagingStudy,
    PhysicalRecord,
    Series,
    Subject,
)

from .base import CleanupAPITestCase

if TYPE_CHECKING:
    from rest_framework.response import Response

# A valid Fernet key for use in tests that need ENDPOINT_CREDENTIALS_KEY.
_TEST_FERNET_KEY = "pszJ39pBGFbjGZk8cM-MOzccZh0T0M8MTmVVitw4_8Y="


class RecordTests(CleanupAPITestCase):
    """Validate record creation, upload, and retrieval behavior."""

    if TYPE_CHECKING:
        user: AuthUser
        collection: Collection
        subject: Subject
        procedure: Coding
        encounter: Encounter
        rt_lateral: Coding
        orient_left: Coding
        mod_rg: Coding
        image_content: bytes
        tiff_content: bytes

    @override
    def setUp(self) -> None:
        # Create user for authentication
        self.user = AuthUser.objects.create_user(
            username="testuser",
            password="testpassword",
            first_name="Test",
            last_name="User",
        )

        # Add necessary permissions
        for model in [Subject, Encounter, DigitalRecord, ImagingStudy]:
            content_type = ContentType.objects.get_for_model(model)
            permissions = Permission.objects.filter(content_type=content_type)
            self.user.user_permissions.add(*permissions)

        self.client.force_authenticate(user=self.user)

        # Create collection (required for record creation)
        self.collection, _ = Collection.objects.get_or_create(
            short_name="TEST", defaults={"full_name": "Test Collection"}
        )

        # Create test subject and encounter
        self.subject = Subject.objects.create(
            humanname_family="Doe",
            humanname_given="John",
            gender="male",
            birth_date="2000-01-01",
            collection=self.collection,
        )

        self.procedure, _ = Coding.objects.get_or_create(
            system=SYSTEM_PROCEDURE,
            code="ortho-visit",
            defaults={"display": "Orthodontic Visit"},
        )

        # Create encounter via API
        self.encounter = Encounter.objects.create(
            subject=self.subject,
            actual_period_start="2020-01-01",
            procedure_occurrence_age=datetime.timedelta(days=20 * 365.25),
            procedure_code=self.procedure,
        )

        # Create codings
        self.rt_lateral, _ = Coding.objects.get_or_create(
            system=SYSTEM_RECORD_TYPE,
            code="L",
            defaults={"display": "Lateral Cephalogram"},
        )
        self.orient_left, _ = Coding.objects.get_or_create(
            system=SYSTEM_ORIENTATION, code="left", defaults={"display": "Left"}
        )
        self.mod_rg, _ = Coding.objects.get_or_create(
            system=SYSTEM_MODALITY, code="RG", defaults={"display": "Radiography"}
        )

        # Create a valid PNG image
        self.image_content = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        tiff_buf = io.BytesIO()
        Image.new("RGB", (1, 1), color=(255, 255, 255)).save(tiff_buf, format="TIFF")
        self.tiff_content = tiff_buf.getvalue()

    @override_settings(ENDPOINT_CREDENTIALS_KEY=_TEST_FERNET_KEY)
    def test_endpoint_credentials_round_trip(self) -> None:
        """Endpoint credentials should encrypt and decrypt through model helpers."""
        endpoint = Endpoint.objects.create(
            name="Drive-A",
            status=Endpoint.Status.ACTIVE,
            connection_type=Endpoint.ConnectionType.DRIVE,
            address="https://drive.example.org",
        )
        payload = {"token": "secret-token", "user": "archive-bot"}
        endpoint.set_credentials(payload)
        endpoint.save()

        endpoint.refresh_from_db()
        self.assertNotEqual(endpoint.credentials_encrypted, "")
        self.assertNotIn("secret-token", endpoint.credentials_encrypted)
        self.assertEqual(endpoint.get_credentials(), payload)

    def _upload_png(self, extra_fields: dict[str, Any]) -> Response:  # pyright: ignore[reportExplicitAny]
        """Helper: POST a minimal valid PNG record upload, merging extra_fields.

        Returns:
            The response for uploading the png

        """
        upload = SimpleUploadedFile(
            "test.png", self.image_content, content_type="image/png"
        )
        data = {
            "file": upload,
            "record_type": self.rt_lateral.code,
            "encounter": self.encounter.pk,
        }
        data.update(extra_fields)
        url = reverse("archive:api:digitalrecord-list")
        return self.client.post(url, data, format="multipart")

    def test_upload_with_device_creates_device_and_links_records(self) -> None:
        """Uploading with device fields creates a Device

        Also links it to DigitalRecord and PhysicalRecord.

        """
        response = self._upload_png(
            {
                "device_serial": "SN-001",
                "device_manufacturer": "Acme",
                "device_model": "XRay3000",
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # Device should have been created
        self.assertEqual(
            Device.objects.filter(
                serial_number="SN-001", manufacturer="Acme", model_number="XRay3000"
            ).count(),
            1,
        )
        device = Device.objects.get(
            serial_number="SN-001", manufacturer="Acme", model_number="XRay3000"
        )
        self.assertEqual(device.manufacturer, "Acme")
        self.assertEqual(device.display_name, "Acme XRay3000")

        # DigitalRecord should reference the device
        record_id = response.data["id"]
        digital_record = DigitalRecord.objects.get(pk=record_id)
        self.assertEqual(digital_record.device_id, device.pk)

        # PhysicalRecord should also reference the device
        self.assertIsNotNone(digital_record.physical_record)
        physical_record: PhysicalRecord = digital_record.physical_record  # pyright: ignore[reportAssignmentType]
        self.assertEqual(physical_record.device_id, device.pk)

    def test_upload_with_same_device_serial_reuses_device(self) -> None:
        """Uploading twice with the same serial+model reuses the existing Device

        (no duplicates).

        """
        for _ in range(2):
            upload = SimpleUploadedFile(
                "test.png", self.image_content, content_type="image/png"
            )
            _ = self.client.post(
                reverse("archive:api:digitalrecord-list"),
                {
                    "file": upload,
                    "record_type": self.rt_lateral.code,
                    "encounter": self.encounter.pk,
                    "device_serial": "SN-REUSE",
                    "device_manufacturer": "Acme",
                    "device_model": "XRay3000",
                },
                format="multipart",
            )

        self.assertEqual(
            Device.objects.filter(
                serial_number="SN-REUSE", manufacturer="Acme", model_number="XRay3000"
            ).count(),
            1,
            "Expected only one Device row for the same "
            + "serial+manufacturer+model combination.",
        )

    def test_upload_without_device_fields_succeeds_with_null_device(self) -> None:
        """Uploading without device fields succeeds

        ALso checks that device is null on both records.

        """
        response = self._upload_png({})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        record_id = response.data["id"]
        digital_record = DigitalRecord.objects.get(pk=record_id)
        self.assertIsNone(digital_record.device_id)

        self.assertIsNotNone(digital_record.physical_record)
        physical_record: PhysicalRecord = digital_record.physical_record  # pyright: ignore[reportAssignmentType]
        self.assertIsNone(physical_record.device_id)


class RecordIdentifierStrTests(CleanupAPITestCase):
    """Tests for the identifier_str computed field on DigitalRecord API responses."""

    if TYPE_CHECKING:
        user: AuthUser
        collection: Collection
        subject: Subject
        encounter: Encounter
        study: ImagingStudy
        rt_lateral: Coding
        series: Series
        digital_record: DigitalRecord

    @override
    def setUp(self) -> None:
        self.user = AuthUser.objects.create_user(
            username="idstruser",
            password="testpassword",
        )
        for model in [Subject, Encounter, DigitalRecord, ImagingStudy]:
            content_type = ContentType.objects.get_for_model(model)
            permissions = Permission.objects.filter(content_type=content_type)
            self.user.user_permissions.add(*permissions)
        self.client.force_authenticate(user=self.user)

        self.collection, _ = Collection.objects.get_or_create(
            short_name="IDSTR",
            defaults={"full_name": "Identifier Str Test Collection"},
        )

        self.subject = Subject.objects.create(
            humanname_family="Test",
            humanname_given="Subject",
            gender="male",
            birth_date="2000-06-15",
            collection=self.collection,
        )
        bolton_identifier, _ = Identifier.objects.get_or_create(
            system=SYSTEM_IDENTIFIER_BOLTON_SUBJECT,
            value="B001",
            defaults={"use": "official"},
        )
        self.subject.identifiers.add(bolton_identifier)

        procedure, _ = Coding.objects.get_or_create(
            system=SYSTEM_PROCEDURE,
            code="ortho-visit",
            defaults={"display": "Orthodontic Visit"},
        )

        # Age: 8 years 6 months ≈ 8.5 years
        age_days = int(8 * 365.25 + 6 * 30.4375)
        self.encounter = Encounter.objects.create(
            subject=self.subject,
            actual_period_start="2009-01-01",
            procedure_occurrence_age=datetime.timedelta(days=age_days),
            procedure_code=procedure,
        )

        self.study = ImagingStudy.objects.create(
            encounter=self.encounter,
            collection=self.collection,
        )

        self.rt_lateral, _ = Coding.objects.get_or_create(
            system=SYSTEM_RECORD_TYPE,
            code="L",
            defaults={"display": "Lateral Cephalogram"},
        )
        mod_rg, _ = Coding.objects.get_or_create(
            system=SYSTEM_MODALITY,
            code="RG",
            defaults={"display": "Radiography"},
        )
        self.series = Series.objects.create(
            imaging_study=self.study,
            modality=mod_rg,
        )
        self.digital_record = DigitalRecord.objects.create(
            series=self.series,
            record_type=self.rt_lateral,
        )

    def test_identifier_str_present_in_detail(self) -> None:
        """identifier_str must appear in the detail endpoint response."""
        url = reverse("archive:api:digitalrecord-list") + f"{self.digital_record.pk}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("identifier_str", data)

    def test_identifier_str_format(self) -> None:
        """identifier_str must follow <subject_id><record_type><sex><age><seq> schema"""
        url = reverse("archive:api:digitalrecord-list") + f"{self.digital_record.pk}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        identifier_str: str = data["identifier_str"]
        # Must match schema: <subject_identifier><record_type><sex><age><seq:02d>
        #
        # B001 (Bolton ID) + L (record type) + M (male)
        # + NNyNNm (age) + NN (2-digit seq)
        pattern = r"^B001LM\d{2}y\d{2}m\d{2}$"
        self.assertRegex(
            identifier_str,
            pattern,
            msg=f"identifier_str {identifier_str!r} does not match "
            + f"expected pattern {pattern!r}",
        )
        # Also verify the age encodes approximately 8y 6m (total months 102)
        age_match = re.search(r"(\d{2})y(\d{2})m\d{2}$", identifier_str)
        self.assertIsNotNone(age_match, "Age portion missing from identifier_str")
        assert age_match is not None  # for type narrowing
        years, months = int(age_match.group(1)), int(age_match.group(2))
        total_months = years * 12 + months
        # Allow ±1 month tolerance for floating-point round-trip in age computation
        self.assertAlmostEqual(
            total_months,
            102,
            delta=1,
            msg=f"Expected ~102 total months (8y6m), got {total_months}",
        )

    def test_identifier_str_in_list(self) -> None:
        """identifier_str must be present in the list endpoint results."""
        url = reverse("archive:api:digitalrecord-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        our = [r for r in results if r["id"] == self.digital_record.pk]
        self.assertEqual(len(our), 1)
        self.assertIn("identifier_str", our[0])
        self.assertNotEqual(our[0]["identifier_str"], "")

    def test_identifier_str_missing_age(self) -> None:
        """Ensure identifier_str with no age data omits the age portion and keeps seq"""
        self.encounter.procedure_occurrence_age = None
        self.encounter.actual_period_start = None
        self.encounter.save()
        url = reverse("archive:api:digitalrecord-list") + f"{self.digital_record.pk}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # No age — should still have subject+type+sex+seq but no age component
        self.assertEqual(data["identifier_str"], "B001LM01")

    def test_identifier_str_female(self) -> None:
        """Sex code F for female subjects."""
        self.subject.gender = "female"
        self.subject.save()
        url = reverse("archive:api:digitalrecord-list") + f"{self.digital_record.pk}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("identifier_str", data)
        self.assertTrue(data["identifier_str"].startswith("B001L"))
        self.assertIn("F", data["identifier_str"])

    def test_identifier_str_second_record_has_seq_02(self) -> None:
        """A second record with the same encounter and record_type gets sequence 02."""
        second_record = DigitalRecord.objects.create(
            series=self.series,
            record_type=self.rt_lateral,
        )
        url = reverse("archive:api:digitalrecord-list") + f"{second_record.pk}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(
            data["identifier_str"].endswith("02"),
            "Expected identifier_str to end with '02', "
            + f"got: {data['identifier_str']!r}",
        )


class ImagingStudyOperatorPrefetchTests(CleanupAPITestCase):
    """Tests ImagingStudy queries"""

    if TYPE_CHECKING:
        user: AuthUser
        collection: Collection
        procedure: Coding
        record_type: Coding

    @override
    def setUp(self) -> None:
        self.user = AuthUser.objects.create_user(
            username="perfuser",
            password="pass",
            first_name="Perf",
            last_name="User",
        )
        self.client.force_authenticate(user=self.user)

        self.collection = Collection.objects.create(
            short_name="PERF", full_name="Performance Test Collection"
        )
        self.procedure, _ = Coding.objects.get_or_create(
            system=SYSTEM_PROCEDURE,
            code="ortho-visit",
            defaults={"display": "Orthodontic Visit"},
        )
        self.record_type, _ = Coding.objects.get_or_create(
            system=SYSTEM_RECORD_TYPE,
            code="L",
            defaults={"display": "Lateral Cephalogram"},
        )

        self.studies: list[ImagingStudy] = []

        for i in range(3):
            subject = Subject.objects.create(
                humanname_family=f"Doe{i}",
                humanname_given=f"Jane{i}",
                gender="male",
                birth_date=f"1990-01-0{i + 1}",
                collection=self.collection,
            )
            encounter = Encounter.objects.create(
                subject=subject,
                actual_period_start=f"2022-01-0{i + 1}",
                procedure_code=self.procedure,
            )
            study = ImagingStudy.objects.create(
                encounter=encounter, collection=self.collection
            )
            self.studies.append(study)
            series = Series.objects.create(imaging_study=study)
            operator = AuthUser.objects.create_user(
                username=f"operator{i}",
                first_name=f"Op{i}",
                last_name="X",
                password="pass",
            )
            _ = DigitalRecord.objects.create(
                series=series, operator=operator, record_type=self.record_type
            )

    def test_list_returns_all_studies_with_operator(self) -> None:
        """Response contains all 3 studies with correct scan_operator_username values"""
        resp = self.client.get("/api/imaging-studies/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = (
            data["results"] if isinstance(data, dict) and "results" in data else data
        )
        study_ids = {s.id for s in self.studies}
        our_results = [r for r in results if r["id"] in study_ids]
        self.assertEqual(len(our_results), 3)
        expected_usernames = {f"operator{i}" for i in range(3)}
        returned_usernames = {rec["scan_operator_username"] for rec in our_results}
        self.assertEqual(expected_usernames, returned_usernames)

    def test_list_query_count_is_bounded(self) -> None:
        """Checks query count for the list endpoint is not growing linearly

        In comparison with the number of ImagingStudy objects, number of queries
        should not increase hyperlinearly (i.e., no N+1 on operator lookup).
        With 3 studies the total should stay well under 15 queries.
        """
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get("/api/imaging-studies/")
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(
            len(ctx.captured_queries),
            15,
            f"Too many queries ({len(ctx.captured_queries)}): "
            + str([q["sql"][:120] for q in ctx.captured_queries]),
        )
