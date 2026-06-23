"""Role-based API permission tests."""
# pyright: reportUnknownMemberType=false, reportUninitializedInstanceVariable=false, reportAny=false
# ruff: noqa: S106

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

from BFD9000.conf import AuthUser
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from archive.constants import (
    SYSTEM_MODALITY,
    SYSTEM_ORIENTATION,
    SYSTEM_PROCEDURE,
    SYSTEM_RECORD_TYPE,
)
from archive.models import Coding, Collection, Encounter, Subject

from .base import CleanupAPITestCase


class RolePermissionTests(CleanupAPITestCase):
    """Verify regular, curator, and superuser boundaries."""

    if TYPE_CHECKING:
        collection: Collection
        subject: Subject
        procedure: Coding
        encounter: Encounter
        record_type: Coding
        orientation: Coding
        modality: Coding
        image_content: bytes

    @override
    def setUp(self) -> None:
        self.collection, _ = Collection.objects.get_or_create(
            short_name="TEST",
            defaults={"full_name": "Test Collection"},
        )
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
        self.encounter = Encounter.objects.create(
            subject=self.subject,
            actual_period_start=datetime(2020, 1, 1, tzinfo=UTC).date(),
            procedure_code=self.procedure,
        )
        self.record_type, _ = Coding.objects.get_or_create(
            system=SYSTEM_RECORD_TYPE,
            code="L",
            defaults={"display": "Lateral Cephalogram"},
        )
        self.orientation, _ = Coding.objects.get_or_create(
            system=SYSTEM_ORIENTATION,
            code="left",
            defaults={"display": "Left"},
        )
        self.modality, _ = Coding.objects.get_or_create(
            system=SYSTEM_MODALITY,
            code="RG",
            defaults={"display": "Radiography"},
        )
        self.image_content = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def test_regular_user_cannot_manage_subject_encounter_but_can_create_record(
        self,
    ) -> None:
        """Ensure that users cannot modify encounters but are able to make records"""
        user = AuthUser.objects.create_user(username="regular", password="testpassword")
        self.client.force_authenticate(user=user)

        subject_response = self.client.post(
            reverse("archive:subject-list"),
            {
                "humanname_family": "Smith",
                "humanname_given": "Jane",
                "gender": "female",
                "birth_date": "1999-01-01",
            },
            format="json",
        )
        self.assertEqual(subject_response.status_code, status.HTTP_403_FORBIDDEN)

        encounter_response = self.client.post(
            reverse(
                "archive:subject-encounters-list",
                kwargs={"subject_pk": self.subject.id},
            ),
            {
                "actual_period_start": "2021-01-01",
                "procedure_code": self.procedure.id,
            },
            format="json",
        )
        self.assertEqual(encounter_response.status_code, status.HTTP_403_FORBIDDEN)

        record_response = self.client.post(
            reverse(
                "archive:encounter-records-list",
                kwargs={"encounter_pk": self.encounter.id},
            ),
            {
                "file": SimpleUploadedFile(
                    "test.png", self.image_content, content_type="image/png"
                ),
                "record_type": self.record_type.code,
                "orientation": self.orientation.code,
                "modality": self.modality.code,
            },
            format="multipart",
        )
        self.assertEqual(record_response.status_code, status.HTTP_201_CREATED)

    def test_curator_can_manage_subject_encounter_but_not_delete_anything(self) -> None:
        """Ensures curators can manage encounters but not delete"""
        user = AuthUser.objects.create_user(username="curator", password="testpassword")
        curator_group, _ = Group.objects.get_or_create(name="Curator")
        curator_group.permissions.add(
            Permission.objects.get(codename="add_subject"),
            Permission.objects.get(codename="change_subject"),
            Permission.objects.get(codename="add_encounter"),
            Permission.objects.get(codename="change_encounter"),
        )
        user.groups.add(curator_group)
        self.client.force_authenticate(user=user)

        create_subject = self.client.post(
            reverse("archive:subject-list"),
            {
                "humanname_family": "Curator",
                "humanname_given": "Created",
                "gender": "female",
                "birth_date": "2001-02-02",
            },
            format="json",
        )
        self.assertEqual(create_subject.status_code, status.HTTP_201_CREATED)
        subject_id = create_subject.data["id"]

        update_subject = self.client.patch(
            reverse("archive:subject-detail", kwargs={"pk": subject_id}),
            {"humanname_family": "CuratorUpdated"},
            format="json",
        )
        self.assertEqual(update_subject.status_code, status.HTTP_200_OK)

        delete_subject = self.client.delete(
            reverse("archive:subject-detail", kwargs={"pk": subject_id})
        )
        self.assertEqual(delete_subject.status_code, status.HTTP_403_FORBIDDEN)

        create_encounter = self.client.post(
            reverse(
                "archive:subject-encounters-list",
                kwargs={"subject_pk": self.subject.id},
            ),
            {
                "actual_period_start": "2021-03-03",
                "procedure_code": self.procedure.id,
            },
            format="json",
        )
        self.assertEqual(create_encounter.status_code, status.HTTP_201_CREATED)
        encounter_id = create_encounter.data["id"]

        update_encounter = self.client.patch(
            reverse("archive:encounter-detail", kwargs={"pk": encounter_id}),
            {"actual_period_start": "2021-03-04"},
            format="json",
        )
        self.assertEqual(update_encounter.status_code, status.HTTP_200_OK)

        delete_encounter = self.client.delete(
            reverse("archive:encounter-detail", kwargs={"pk": encounter_id})
        )
        self.assertEqual(delete_encounter.status_code, status.HTTP_403_FORBIDDEN)

        created_record = self.client.post(
            reverse(
                "archive:encounter-records-list",
                kwargs={"encounter_pk": self.encounter.id},
            ),
            {
                "file": SimpleUploadedFile(
                    "test.png", self.image_content, content_type="image/png"
                ),
                "record_type": self.record_type.code,
                "orientation": self.orientation.code,
                "modality": self.modality.code,
            },
            format="multipart",
        )
        self.assertEqual(created_record.status_code, status.HTTP_201_CREATED)

        delete_record = self.client.delete(
            reverse(
                "archive:digitalrecord-detail", kwargs={"pk": created_record.data["id"]}
            )
        )
        self.assertEqual(delete_record.status_code, status.HTTP_403_FORBIDDEN)
