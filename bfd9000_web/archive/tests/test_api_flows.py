"""End-to-end API flow tests for subjects, encounters, and records."""
# pyright: reportUninitializedInstanceVariable=false, reportUnknownMemberType=false, reportAny=false
# ruff: noqa: S106

from typing import TYPE_CHECKING

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from typing_extensions import override

from archive.constants import (
    SYSTEM_MODALITY,
    SYSTEM_ORIENTATION,
    SYSTEM_PROCEDURE,
    SYSTEM_RECORD_TYPE,
)
from archive.models import Coding, Collection, DigitalRecord, Encounter, Subject

from .base import CleanupAPITestCase


class ApiFlowTests(CleanupAPITestCase):
    """Exercise the happy-path API workflow."""

    if TYPE_CHECKING:
        user: User
        collection: Collection
        rt: Coding
        orient: Coding
        mod: Coding
        proc: Coding
        subject_data: dict[str, str]

    @override
    def setUp(self) -> None:
        # Create user for authentication
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )

        # Add necessary permissions
        models = [Subject, Encounter, DigitalRecord]
        for model in models:
            content_type = ContentType.objects.get_for_model(model)
            permissions = Permission.objects.filter(content_type=content_type)
            self.user.user_permissions.add(*permissions)

        self.client.force_authenticate(user=self.user)

        # Create necessary data
        self.collection, _ = Collection.objects.get_or_create(
            short_name="TEST",
            defaults={"full_name": "Test Collection"},
        )

        # Ensure codings exist
        self.rt, _ = Coding.objects.get_or_create(
            system=SYSTEM_RECORD_TYPE,
            code="L",
            defaults={"display": "Lateral Cephalogram"},
        )
        self.orient, _ = Coding.objects.get_or_create(
            system=SYSTEM_ORIENTATION,
            code="left",
            defaults={"display": "Left"},
        )
        self.mod, _ = Coding.objects.get_or_create(
            system=SYSTEM_MODALITY,
            code="RG",
            defaults={"display": "Radiography"},
        )
        self.proc, _ = Coding.objects.get_or_create(
            system=SYSTEM_PROCEDURE,
            code="ortho-visit",
            defaults={"display": "Orthodontic Visit"},
        )

        self.subject_data = {
            "humanname_family": "Doe",
            "humanname_given": "John",
            "gender": "male",
            "birth_date": "2000-01-01",
            "collection": "TEST",
        }

    def test_full_flow(self) -> None:
        """Create subject, encounter, and record then verify downloads."""
        # 1. Create Subject
        url = reverse("archive:subject-list")
        response = self.client.post(url, self.subject_data, format="json")
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Subject creation failed: {response.status_code} - {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        subject_id = response.data["id"]

        # 2. Create Encounter
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": subject_id}
        )
        encounter_data = {
            "actual_period_start": "2020-01-01",
            "procedure_code": self.proc.id,
            # age_at_encounter should be calculated: 20 years
        }
        response = self.client.post(url, encounter_data, format="json")
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Encounter creation failed: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        encounter_id = response.data["id"]
        self.assertAlmostEqual(response.data["age_at_encounter"], 20.0, delta=0.1)

        # 3. Upload Record
        url = reverse(
            "archive:encounter-records-list", kwargs={"encounter_pk": encounter_id}
        )

        # Create dummy PNG
        image_content = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        file = SimpleUploadedFile("test.png", image_content, content_type="image/png")

        data = {
            "file": file,
            "record_type": self.rt.code,
            "modality": "RG",
        }

        response = self.client.post(url, data, format="multipart")
        if response.status_code != status.HTTP_201_CREATED:
            print(response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        record_id = response.data["id"]

        # 4. Verify Record
        record: DigitalRecord = DigitalRecord.objects.get(pk=record_id)
        # New model: record belongs to a series -> imaging_study
        self.assertIsNotNone(record.series)
        self.assertIsNotNone(record.series.imaging_study)
        self.assertTrue(record.source_file or record.thumbnail)
        self.assertEqual(record.record_type.code, self.rt.code)

        # 5. Verify Image Download
        url = reverse("archive:digitalrecord-image", kwargs={"pk": record_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 6. Verify Thumbnail
        url = reverse("archive:digitalrecord-thumbnail", kwargs={"pk": record_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
