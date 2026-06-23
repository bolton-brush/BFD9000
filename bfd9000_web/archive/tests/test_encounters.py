"""API tests for encounter endpoints."""
# pyright: reportUninitializedInstanceVariable=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportAny=false
# ruff: noqa: S106

from __future__ import annotations

from typing import TYPE_CHECKING, override

from BFD9000.conf import AuthUser
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status

from archive.constants import SYSTEM_IDENTIFIER_LANCASTER_SUBJECT, SYSTEM_PROCEDURE
from archive.models import Coding, Encounter, Identifier, Subject

from .base import CleanupAPITestCase


class EncounterTests(CleanupAPITestCase):
    """Validate encounter CRUD and derived fields."""

    if TYPE_CHECKING:
        user: AuthUser
        subject: Subject
        procedure: Coding

    @override
    def setUp(self) -> None:
        # Create user for authentication
        self.user = AuthUser.objects.create_user(
            username="testuser", password="testpassword"
        )

        # Add necessary permissions
        for model in [Subject, Encounter]:
            content_type = ContentType.objects.get_for_model(model)
            permissions = Permission.objects.filter(content_type=content_type)
            self.user.user_permissions.add(*permissions)

        self.client.force_authenticate(user=self.user)

        # Create test subject
        self.subject = Subject.objects.create(
            humanname_family="Doe",
            humanname_given="John",
            gender="male",
            birth_date="2000-01-01",
        )

        # Create procedure coding
        self.procedure, _ = Coding.objects.get_or_create(
            system=SYSTEM_PROCEDURE,
            code="ortho-visit",
            defaults={"display": "Orthodontic Visit"},
        )

    def test_create_encounter(self) -> None:
        """Should create encounter for subject"""
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        data = {
            "actual_period_start": "2020-01-01",
            "procedure_code": self.procedure.id,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["actual_period_start"], "2020-01-01")
        self.assertIn("age_at_encounter", response.data)
        # Age should be approximately 20 years
        self.assertAlmostEqual(response.data["age_at_encounter"], 20.0, delta=1.0)

    def test_create_encounter_missing_procedure(self) -> None:
        """Should return 400 if procedure_code is missing"""
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        data = {
            "actual_period_start": "2020-01-01"
            # Missing procedure_code
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_encounter_invalid_subject(self) -> None:
        """Should return 404 for non-existent subject"""
        url = reverse("archive:subject-encounters-list", kwargs={"subject_pk": 99999})
        data = {
            "actual_period_start": "2020-01-01",
            "procedure_code": self.procedure.id,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_encounters_for_subject(self) -> None:
        """Should list all encounters for a subject"""
        # Create encounters using the API
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        _ = self.client.post(
            url,
            {"actual_period_start": "2020-01-01", "procedure_code": self.procedure.id},
            format="json",
        )
        _ = self.client.post(
            url,
            {"actual_period_start": "2021-01-01", "procedure_code": self.procedure.id},
            format="json",
        )

        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 2)

    def test_list_encounters_sorted_by_date_desc(self) -> None:
        """Encounter list should be deterministically ordered newest-first."""
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        _ = self.client.post(
            url,
            {
                "actual_period_start": "2020-01-01",
                "procedure_code": self.procedure.id,
            },
            format="json",
        )
        _ = self.client.post(
            url,
            {
                "actual_period_start": "2021-01-01",
                "procedure_code": self.procedure.id,
            },
            format="json",
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["results"][0]["actual_period_start"], "2021-01-01"
        )
        self.assertEqual(
            response.data["results"][1]["actual_period_start"], "2020-01-01"
        )

    def test_global_encounter_list_with_subject_filter_is_ordered(self) -> None:
        """Global encounters endpoint should be ordered when paginated."""
        nested_url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        _ = self.client.post(
            nested_url,
            {
                "actual_period_start": "2020-01-01",
                "procedure_code": self.procedure.id,
            },
            format="json",
        )
        _ = self.client.post(
            nested_url,
            {
                "actual_period_start": "2021-01-01",
                "procedure_code": self.procedure.id,
            },
            format="json",
        )

        url = reverse("archive:encounter-list")
        response = self.client.get(
            url, {"subject": self.subject.id, "page": 1, "page_size": 20}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 2)
        self.assertEqual(
            response.data["results"][0]["actual_period_start"], "2021-01-01"
        )

    def test_encounter_subject_identifier_uses_official_identifier(self) -> None:
        """Encounter response should expose official subject identifier."""
        identifier, _ = Identifier.objects.get_or_create(
            system=SYSTEM_IDENTIFIER_LANCASTER_SUBJECT,
            value="L00004310",
            defaults={"use": "official"},
        )
        self.subject.identifiers.add(identifier)

        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        create_response = self.client.post(
            url,
            {
                "actual_period_start": "2020-01-01",
                "procedure_code": self.procedure.id,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        list_response = self.client.get(
            reverse("archive:encounter-list"), {"subject": self.subject.id}
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(list_response.data["results"]), 1)
        self.assertEqual(
            list_response.data["results"][0]["subject_identifier"], "L00004310"
        )

    def test_search_encounters_by_subject_identifier_prefix(self) -> None:
        """Search uses istartswith: prefix matches return results

        Also makes sure mid-string matches do not.

        """
        identifier, _ = Identifier.objects.get_or_create(
            system=SYSTEM_IDENTIFIER_LANCASTER_SUBJECT,
            value="SUB-4310-ALPHA",
            defaults={"use": "official"},
        )
        self.subject.identifiers.add(identifier)

        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        create_response = self.client.post(
            url,
            {
                "actual_period_start": "2020-01-01",
                "procedure_code": self.procedure.id,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        encounter_list_url = reverse("archive:encounter-list")

        # Prefix match — 'SUB' should return the encounter
        response = self.client.get(encounter_list_url, {"search": "SUB"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["subject"], self.subject.id)

        # Mid-string match — '4310' should return nothing (istartswith, not icontains)
        response = self.client.get(encounter_list_url, {"search": "4310"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_subject_ids = [r["subject"] for r in response.data["results"]]
        self.assertNotIn(self.subject.id, result_subject_ids)

    def test_get_encounter_detail(self) -> None:
        """Should retrieve specific encounter details"""
        # Create encounter via API
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        create_response = self.client.post(
            url,
            {"actual_period_start": "2020-01-01", "procedure_code": self.procedure.id},
            format="json",
        )
        encounter_id = create_response.data["id"]

        url = reverse("archive:encounter-detail", kwargs={"pk": encounter_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], encounter_id)
        self.assertEqual(response.data["actual_period_start"], "2020-01-01")
        self.assertIn("subject", response.data)

    def test_get_encounter_not_found(self) -> None:
        """Should return 404 for non-existent encounter"""
        url = reverse("archive:encounter-detail", kwargs={"pk": 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_encounter(self) -> None:
        """Should update encounter details"""
        # Create encounter via API
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        create_response = self.client.post(
            url,
            {"actual_period_start": "2020-01-01", "procedure_code": self.procedure.id},
            format="json",
        )
        encounter_id = create_response.data["id"]

        url = reverse("archive:encounter-detail", kwargs={"pk": encounter_id})
        data = {"actual_period_start": "2020-02-01"}
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["actual_period_start"], "2020-02-01")

    def test_delete_encounter(self) -> None:
        """Non-superuser should not delete encounter."""
        # Create encounter via API
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        create_response = self.client.post(
            url,
            {"actual_period_start": "2020-01-01", "procedure_code": self.procedure.id},
            format="json",
        )
        encounter_id = create_response.data["id"]

        url = reverse("archive:encounter-detail", kwargs={"pk": encounter_id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Verify encounter still exists
        self.assertTrue(Encounter.objects.filter(pk=encounter_id).exists())

    def test_superuser_can_delete_encounter(self) -> None:
        """Superuser should be able to delete encounter."""
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        create_response = self.client.post(
            url,
            {"actual_period_start": "2020-01-01", "procedure_code": self.procedure.id},
            format="json",
        )
        encounter_id = create_response.data["id"]

        superuser = AuthUser.objects.create_superuser(
            username="admin",
            password="adminpass",
            email="admin@example.com",
        )
        self.client.force_authenticate(user=superuser)
        detail_url = reverse("archive:encounter-detail", kwargs={"pk": encounter_id})
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Encounter.objects.filter(pk=encounter_id).exists())

    def test_regular_user_without_encounter_perms_cannot_create_encounter(self) -> None:
        """Regular authenticated user should not create encounter."""
        regular_user = AuthUser.objects.create_user(
            username="regular", password="testpassword"
        )
        self.client.force_authenticate(user=regular_user)

        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        data = {
            "actual_period_start": "2020-01-01",
            "procedure_code": self.procedure.id,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_encounter_age_calculation(self) -> None:
        """Should automatically calculate age_at_encounter from subject birth_date"""
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        data = {
            "actual_period_start": "2015-06-15",
            "procedure_code": self.procedure.id,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Subject born 2000-01-01, encounter 2015-06-15 = ~15.5 years
        self.assertAlmostEqual(response.data["age_at_encounter"], 15.5, delta=1.0)

    def test_unauthenticated_access(self) -> None:
        """Should return 401/403 if not authenticated"""
        self.client.logout()
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        response = self.client.get(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_encounter_has_age_calculated(self) -> None:
        """Encounter detail should include calculated age"""
        # Create encounter via API
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        create_response = self.client.post(
            url,
            {"actual_period_start": "2020-01-01", "procedure_code": self.procedure.id},
            format="json",
        )
        encounter_id = create_response.data["id"]

        url = reverse("archive:encounter-detail", kwargs={"pk": encounter_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check if age_at_encounter is calculated
        self.assertIn("age_at_encounter", response.data)
        self.assertIsNotNone(response.data["age_at_encounter"])

    def test_list_encounters_pagination(self) -> None:
        """Should support pagination for encounter lists"""
        # Create multiple encounters via API
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        for i in range(25):
            # Use sequential dates across multiple months/years
            year = 2020 + (i // 12)
            month = (i % 12) + 1
            _ = self.client.post(
                url,
                {
                    "actual_period_start": f"{year}-{month:02d}-01",
                    "procedure_code": self.procedure.id,
                },
                format="json",
            )

        # Get first page
        url = reverse(
            "archive:subject-encounters-list", kwargs={"subject_pk": self.subject.id}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)
        self.assertEqual(response.data["count"], 25)
        # Should have paginated results (max PAGE_SIZE=20)
        self.assertLessEqual(len(response.data["results"]), 20)

    def test_encounter_detail_computes_age_from_birthdate_when_duration_missing(
        self,
    ) -> None:
        """Should derive age_at_encounter from subject birth_date and encounter date."""
        encounter = Encounter.objects.create(
            subject=self.subject,
            actual_period_start="2020-06-15",
            procedure_code=self.procedure,
            procedure_occurrence_age=None,
        )

        url = reverse("archive:encounter-detail", kwargs={"pk": encounter.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 2000-01-01 to 2020-06-15 is about 20.45 years
        self.assertAlmostEqual(response.data["age_at_encounter"], 20.45, delta=0.05)
