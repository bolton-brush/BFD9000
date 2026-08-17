"""API tests for subject endpoints."""
# pyright: reportUninitializedInstanceVariable=false, reportUnknownMemberType=false, reportAny=false
# ruff: noqa: S106

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, override

from BFD9000.conf import AuthUser
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status

from archive.constants import SYSTEM_IDENTIFIER_BOLTON_SUBJECT
from archive.models import Collection, Identifier, Subject

from .base import CleanupAPITestCase

if TYPE_CHECKING:
    from collections.abc import Container


class SubjectTests(CleanupAPITestCase):
    """Validate subject CRUD and search behavior."""

    if TYPE_CHECKING:
        user: AuthUser
        collection: Collection

    @override
    def setUp(self) -> None:
        # Create user for authentication
        self.user = AuthUser.objects.create_user(
            username="testuser", password="testpassword"
        )

        # Add necessary permissions
        content_type = ContentType.objects.get_for_model(Subject)
        permissions = Permission.objects.filter(content_type=content_type)
        self.user.user_permissions.add(*permissions)

        self.client.force_authenticate(user=self.user)

        # Create test data
        self.collection, _ = Collection.objects.get_or_create(
            short_name="BBC", defaults={"full_name": "Bolton-Brush Collection"}
        )

    def test_create_subject_minimal(self) -> None:
        """Should create subject with minimal required fields"""
        url = reverse("archive:api:subject-list")
        data = {
            "humanname_family": "Doe",
            "humanname_given": "John",
            "gender": "male",
            "birth_date": "2000-01-01",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["humanname_family"], "Doe")
        self.assertEqual(response.data["humanname_given"], "John")
        self.assertEqual(response.data["gender"], "male")
        self.assertEqual(response.data["birth_date"], "2000-01-01")

    def test_create_subject_full(self) -> None:
        """Should create subject with all optional fields"""
        url = reverse("archive:api:subject-list")
        data = {
            "humanname_family": "Smith",
            "humanname_given": "Jane",
            "gender": "female",
            "birth_date": "1995-05-15",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)

    def test_create_subject_with_identifier(self) -> None:
        """Should attach identifier when identifier fields are provided."""
        url = reverse("archive:api:subject-list")
        data = {
            "humanname_family": "Doe",
            "humanname_given": "John",
            "gender": "male",
            "birth_date": "2000-01-01",
            "identifier_value": "B0001",
            "identifier_system": SYSTEM_IDENTIFIER_BOLTON_SUBJECT,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        subject = Subject.objects.get(pk=response.data["id"])
        self.assertEqual(subject.identifiers.count(), 1)
        identifier = Identifier.objects.get(
            pk=cast("Identifier", subject.identifiers.first()).pk
        )
        self.assertEqual(identifier.value, "B0001")
        self.assertEqual(identifier.system, SYSTEM_IDENTIFIER_BOLTON_SUBJECT)

    def test_create_subject_missing_required_field(self) -> None:
        """Should return 400 if required fields are missing"""
        url = reverse("archive:api:subject-list")
        data = {
            "humanname_family": "Doe",
            # Missing humanname_given, gender, birth_date
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_subject_invalid_gender(self) -> None:
        """Should return 400 for invalid gender value"""
        url = reverse("archive:api:subject-list")
        data = {
            "humanname_family": "Doe",
            "humanname_given": "John",
            "gender": "invalid_gender",
            "birth_date": "2000-01-01",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_subjects(self) -> None:
        """Should list all subjects"""
        # Create test subjects
        _ = Subject.objects.create(
            humanname_family="Doe",
            humanname_given="John",
            gender="male",
            birth_date="2000-01-01",
        )
        _ = Subject.objects.create(
            humanname_family="Smith",
            humanname_given="Jane",
            gender="female",
            birth_date="1995-05-15",
        )

        url = reverse("archive:api:subject-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertGreaterEqual(len(response.data["results"]), 2)

    def test_get_subject_detail(self) -> None:
        """Should retrieve specific subject details"""
        subject = Subject.objects.create(
            humanname_family="Doe",
            humanname_given="John",
            gender="male",
            birth_date="2000-01-01",
        )

        url = reverse("archive:api:subject-detail", kwargs={"pk": subject.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], subject.id)
        self.assertEqual(response.data["humanname_family"], "Doe")
        self.assertEqual(response.data["humanname_given"], "John")

    def test_get_subject_not_found(self) -> None:
        """Should return 404 for non-existent subject"""
        url = reverse("archive:api:subject-detail", kwargs={"pk": 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_subject(self) -> None:
        """Should update subject details"""
        subject = Subject.objects.create(
            humanname_family="Doe",
            humanname_given="John",
            gender="male",
            birth_date="2000-01-01",
        )

        url = reverse("archive:api:subject-detail", kwargs={"pk": subject.id})
        data = {
            "humanname_family": "Updated",
            "humanname_given": "John",
            "gender": "male",
            "birth_date": "2000-01-01",
        }
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["humanname_family"], "Updated")

    def test_delete_subject(self) -> None:
        """Non-superuser should not delete subject."""
        subject = Subject.objects.create(
            humanname_family="Doe",
            humanname_given="John",
            gender="male",
            birth_date="2000-01-01",
        )

        url = reverse("archive:api:subject-detail", kwargs={"pk": subject.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Verify subject still exists
        self.assertTrue(Subject.objects.filter(pk=subject.id).exists())

    def test_superuser_can_delete_subject(self) -> None:
        """Superuser should be able to delete subject."""
        subject = Subject.objects.create(
            humanname_family="Doe",
            humanname_given="John",
            gender="male",
            birth_date="2000-01-01",
        )
        superuser = AuthUser.objects.create_superuser(
            username="admin",
            password="adminpass",
            email="admin@example.com",
        )

        self.client.force_authenticate(user=superuser)
        url = reverse("archive:api:subject-detail", kwargs={"pk": subject.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Subject.objects.filter(pk=subject.id).exists())

    def test_regular_user_without_subject_perms_cannot_create_subject(self) -> None:
        """Regular authenticated user should not create subject."""
        regular_user = AuthUser.objects.create_user(
            username="regular", password="testpassword"
        )
        self.client.force_authenticate(user=regular_user)

        url = reverse("archive:api:subject-list")
        data = {
            "humanname_family": "Doe",
            "humanname_given": "John",
            "gender": "male",
            "birth_date": "2000-01-01",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_search_subjects(self) -> None:
        """Search uses istartswith: prefix matches return results

        Also ensures mid-string matches do not.

        """
        subject_doe = Subject.objects.create(
            humanname_family="Doe",
            humanname_given="John",
            gender="male",
            birth_date="2000-01-01",
        )
        subject_smith = Subject.objects.create(
            humanname_family="Smith",
            humanname_given="Jane",
            gender="female",
            birth_date="1995-05-15",
        )

        id_doe, _ = Identifier.objects.get_or_create(
            system="http://example.com/ids",
            value="SRCH001",
            defaults={"use": "official"},
        )
        id_smith, _ = Identifier.objects.get_or_create(
            system="http://example.com/ids",
            value="SRCH002",
            defaults={"use": "official"},
        )
        subject_doe.identifiers.add(id_doe)
        subject_smith.identifiers.add(id_smith)

        base_url = reverse("archive:api:subject-list")

        # Prefix 'SRCH' matches both
        response = self.client.get(base_url + "?search=SRCH")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [r["id"] for r in response.data["results"]]
        self.assertIn(subject_doe.id, returned_ids)
        self.assertIn(subject_smith.id, returned_ids)

        # Prefix 'SRCH001' matches only subject_doe
        response = self.client.get(base_url + "?search=SRCH001")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [r["id"] for r in response.data["results"]]
        self.assertIn(subject_doe.id, returned_ids)
        self.assertNotIn(subject_smith.id, returned_ids)

        # Mid-string match 'RCH' should return nothing (istartswith, not icontains)
        response = self.client.get(base_url + "?search=RCH")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [r["id"] for r in response.data["results"]]
        self.assertNotIn(subject_doe.id, returned_ids)
        self.assertNotIn(subject_smith.id, returned_ids)

    def test_filter_subjects_by_gender(self) -> None:
        """Should filter subjects by gender"""
        _ = Subject.objects.create(
            humanname_family="Doe",
            humanname_given="John",
            gender="male",
            birth_date="2000-01-01",
        )
        _ = Subject.objects.create(
            humanname_family="Smith",
            humanname_given="Jane",
            gender="female",
            birth_date="1995-05-15",
        )

        url = reverse("archive:api:subject-list") + "?gender=male"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # All results should be male
        for item in response.data["results"]:
            self.assertEqual(item["gender"], "male")

    def test_unauthenticated_access(self) -> None:
        """Should return 401/403 if not authenticated"""
        self.client.logout()
        url = reverse("archive:api:subject-list")
        response = self.client.get(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_subject_with_encounters_count(self) -> None:
        """Should return encounter count in list view"""
        subject = Subject.objects.create(
            humanname_family="Doe",
            humanname_given="John",
            gender="male",
            birth_date="2000-01-01",
        )

        url = reverse("archive:api:subject-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Find our subject in results
        subject_data = next(
            (item for item in response.data["results"] if item["id"] == subject.id),
            None,
        )
        self.assertIsNotNone(subject_data)
        self.assertIn("encounter_count", cast("Container[Any]", subject_data))  # pyright: ignore[reportExplicitAny]
        self.assertIn("record_count", cast("Container[Any]", subject_data))  # pyright: ignore[reportExplicitAny]
