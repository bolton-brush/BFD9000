"""API tests for valueset endpoints."""
# pyright: reportUnknownMemberType=false, reportUninitializedInstanceVariable=false, reportAny=false
# ruff: noqa: S106

from typing import TYPE_CHECKING, override

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status

from archive.constants import (
    SYSTEM_IDENTIFIER_IMAGE_TYPE,
    SYSTEM_MODALITY,
    SYSTEM_ORIENTATION,
    SYSTEM_PROCEDURE,
    SYSTEM_RECORD_TYPE,
)
from archive.models import Coding, Collection, ValueSet, ValueSetConcept

from .base import CleanupAPITestCase


class ValuesetTests(CleanupAPITestCase):
    """Validate valueset responses and filtering."""

    if TYPE_CHECKING:
        user: User
        collection: Collection
        collection2: Collection
        record_types_valueset: ValueSet
        orientations_valueset: ValueSet
        modalities_valueset: ValueSet
        procedures_valueset: ValueSet
        image_types_valueset: ValueSet
        rt_lateral: Coding
        rt_pa: Coding
        orient_left: Coding
        orient_right: Coding
        mod_rg: Coding
        mod_m3d: Coding
        mod_docd: Coding
        proc_visit: Coding
        image_type_l: Coding

    @override
    def setUp(self) -> None:
        # Create user for authentication
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.client.force_authenticate(user=self.user)

        # Create test data with multiple codings per system for better testing
        self.collection, _ = Collection.objects.get_or_create(
            short_name="TEST",
            defaults={"full_name": "Test Collection"},
        )
        self.collection2, _ = Collection.objects.get_or_create(
            short_name="TEST2",
            defaults={"full_name": "Test Collection 2"},
        )

        self.record_types_valueset, _ = ValueSet.objects.get_or_create(
            slug="record_types",
            defaults={
                "url": "https://orthodontics.case.edu/fhir/cwru-ortho-record-types",
                "name": "CWRUOrthoRecordTypes",
                "title": "CWRU Ortho Record Types",
            },
        )
        self.orientations_valueset, _ = ValueSet.objects.get_or_create(
            slug="orientations",
            defaults={
                "url": "https://orthodontics.case.edu/fhir/ValueSet/orientations",
                "name": "Orientations",
                "title": "Orientations",
            },
        )
        self.modalities_valueset, _ = ValueSet.objects.get_or_create(
            slug="modalities",
            defaults={
                "url": "https://orthodontics.case.edu/fhir/ValueSet/modalities",
                "name": "Modalities",
                "title": "Modalities",
            },
        )
        self.procedures_valueset, _ = ValueSet.objects.get_or_create(
            slug="procedures",
            defaults={
                "url": "https://orthodontics.case.edu/fhir/ValueSet/procedures",
                "name": "Procedures",
                "title": "Procedures",
            },
        )
        self.image_types_valueset, _ = ValueSet.objects.get_or_create(
            slug="image_types",
            defaults={
                "url": "https://orthodontics.case.edu/fhir/ValueSet/image-types",
                "name": "ImageTypes",
                "title": "Image types",
            },
        )

        # Record types (CWRU codes)
        self.rt_lateral, _ = Coding.objects.get_or_create(
            system=SYSTEM_RECORD_TYPE,
            code="L",
            defaults={"display": "Lateral Cephalogram"},
        )
        _ = ValueSetConcept.objects.get_or_create(
            valueset=self.record_types_valueset,
            coding=self.rt_lateral,
        )
        self.rt_pa, _ = Coding.objects.get_or_create(
            system=SYSTEM_RECORD_TYPE,
            code="F",
            defaults={"display": "Frontal Cephalogram"},
        )
        _ = ValueSetConcept.objects.get_or_create(
            valueset=self.record_types_valueset,
            coding=self.rt_pa,
        )

        # Orientations (using SNOMED codes from migration)
        self.orient_left, _ = Coding.objects.get_or_create(
            system=SYSTEM_ORIENTATION,
            code="399173006",
            defaults={"display": "Left lateral projection"},
        )
        _ = ValueSetConcept.objects.get_or_create(
            valueset=self.orientations_valueset,
            coding=self.orient_left,
        )
        self.orient_right, _ = Coding.objects.get_or_create(
            system=SYSTEM_ORIENTATION,
            code="399198007",
            defaults={"display": "Right lateral projection"},
        )
        _ = ValueSetConcept.objects.get_or_create(
            valueset=self.orientations_valueset,
            coding=self.orient_right,
        )

        # Modalities
        self.mod_rg, _ = Coding.objects.get_or_create(
            system=SYSTEM_MODALITY,
            code="RG",
            defaults={"display": "Radiographic imaging"},
        )
        _ = ValueSetConcept.objects.get_or_create(
            valueset=self.modalities_valueset,
            coding=self.mod_rg,
        )
        self.mod_m3d, _ = Coding.objects.get_or_create(
            system=SYSTEM_MODALITY,
            code="M3D",
            defaults={"display": "3D Manufacturing Modeling System"},
        )
        _ = ValueSetConcept.objects.get_or_create(
            valueset=self.modalities_valueset,
            coding=self.mod_m3d,
        )
        self.mod_docd, _ = Coding.objects.get_or_create(
            system=SYSTEM_MODALITY,
            code="DOCD",
            defaults={"display": "Document Digitizer Equipment"},
        )
        _ = ValueSetConcept.objects.get_or_create(
            valueset=self.modalities_valueset,
            coding=self.mod_docd,
        )

        # Procedures
        self.proc_visit, _ = Coding.objects.get_or_create(
            system=SYSTEM_PROCEDURE,
            code="ortho-visit",
            defaults={"display": "Orthodontic Visit"},
        )
        _ = ValueSetConcept.objects.get_or_create(
            valueset=self.procedures_valueset,
            coding=self.proc_visit,
        )

        self.image_type_l, _ = Coding.objects.get_or_create(
            system=SYSTEM_IDENTIFIER_IMAGE_TYPE,
            code="L",
            defaults={"display": "Lateral"},
        )
        _ = ValueSetConcept.objects.get_or_create(
            valueset=self.image_types_valueset,
            coding=self.image_type_l,
        )

    def test_missing_type_parameter(self) -> None:
        """Should return 400 if 'type' parameter is missing"""
        url = reverse("archive:valuesets-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Missing 'type' parameter")

    def test_unknown_valueset_type(self) -> None:
        """Should return 404 if 'type' parameter is unknown"""
        url = reverse("archive:valuesets-list") + "?type=unknown_type"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_sex_options(self) -> None:
        """Should return sex options with correct structure"""
        url = reverse("archive:valuesets-list") + "?type=sex_options"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data), 0)

        # Verify structure
        for item in response.data:
            self.assertIn("id", item)
            self.assertIn("display", item)
            self.assertEqual(len(item), 2, "Should only have 'id' and 'display' fields")
            self.assertIsInstance(item["id"], str)
            self.assertIsInstance(item["display"], str)

        # Verify expected values exist
        ids = [item["id"] for item in response.data]
        self.assertIn("male", ids)
        self.assertIn("female", ids)

    def test_collections(self) -> None:
        """Should return collections with correct structure"""
        url = reverse("archive:valuesets-list") + "?type=collections"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify structure
        for item in response.data:
            self.assertIn("id", item)
            self.assertIn("display", item)
            self.assertEqual(len(item), 2, "Should only have 'id' and 'display' fields")

        # Should find our test collections
        ids = [item["id"] for item in response.data]
        self.assertIn("TEST", ids)
        self.assertIn("TEST2", ids)

        # Verify display names
        test_item = next(item for item in response.data if item["id"] == "TEST")
        self.assertEqual(test_item["display"], "Test Collection")

    def test_record_types(self) -> None:
        """Should return record types with correct structure"""
        url = reverse("archive:valuesets-list") + "?type=record_types"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify structure
        for item in response.data:
            self.assertIn("id", item)
            self.assertIn("display", item)
            self.assertEqual(len(item), 2, "Should only have 'id' and 'display' fields")

        # Verify expected values (CWRU codes)
        ids = [item["id"] for item in response.data]
        self.assertIn("L", ids)  # Lateral Cephalogram
        self.assertIn("F", ids)  # Frontal Cephalogram

    def test_orientations(self) -> None:
        """Should return orientations with correct structure"""
        url = reverse("archive:valuesets-list") + "?type=orientations"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify structure
        for item in response.data:
            self.assertIn("id", item)
            self.assertIn("display", item)
            self.assertEqual(len(item), 2, "Should only have 'id' and 'display' fields")

        # Verify expected values (SNOMED codes)
        ids = [item["id"] for item in response.data]
        self.assertIn("399173006", ids)  # Left lateral projection
        self.assertIn("399198007", ids)  # Right lateral projection

    def test_modalities(self) -> None:
        """Should return modalities with correct structure"""
        url = reverse("archive:valuesets-list") + "?type=modalities"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify structure
        for item in response.data:
            self.assertIn("id", item)
            self.assertIn("display", item)
            self.assertEqual(len(item), 2, "Should only have 'id' and 'display' fields")

        # Verify expected values
        ids = [item["id"] for item in response.data]
        self.assertIn("RG", ids)
        self.assertIn("M3D", ids)
        self.assertIn("DOCD", ids)
        self.assertNotIn("SI", ids)

    def test_procedures(self) -> None:
        """Should return procedures with correct structure"""
        url = reverse("archive:valuesets-list") + "?type=procedures"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify structure
        for item in response.data:
            self.assertIn("id", item)
            self.assertIn("display", item)
            self.assertEqual(len(item), 2, "Should only have 'id' and 'display' fields")

        # Verify expected values
        ids = [item["id"] for item in response.data]
        self.assertIn("ortho-visit", ids)

    def test_image_types(self) -> None:
        """Should return image types with correct structure."""
        url = reverse("archive:valuesets-list") + "?type=image_types"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for item in response.data:
            self.assertIn("id", item)
            self.assertIn("display", item)
            self.assertEqual(len(item), 2)

        ids = [item["id"] for item in response.data]
        self.assertIn("L", ids)

    def test_cross_contamination_orientations_vs_collections(self) -> None:
        """Orientations should not contain collection codes"""
        url_orient = reverse("archive:valuesets-list") + "?type=orientations"
        url_coll = reverse("archive:valuesets-list") + "?type=collections"

        response_orient = self.client.get(url_orient)
        response_coll = self.client.get(url_coll)

        orient_ids = {item["id"] for item in response_orient.data}
        coll_ids = {item["id"] for item in response_coll.data}

        # No overlap should exist
        overlap = orient_ids.intersection(coll_ids)
        self.assertEqual(
            len(overlap),
            0,
            f"Found overlap between orientations and collections: {overlap}",
        )

    def test_cross_contamination_orientations_vs_modalities(self) -> None:
        """Orientations should not contain modality codes"""
        url_orient = reverse("archive:valuesets-list") + "?type=orientations"
        url_mod = reverse("archive:valuesets-list") + "?type=modalities"

        response_orient = self.client.get(url_orient)
        response_mod = self.client.get(url_mod)

        orient_ids = {item["id"] for item in response_orient.data}
        mod_ids = {item["id"] for item in response_mod.data}

        # No overlap should exist
        overlap = orient_ids.intersection(mod_ids)
        self.assertEqual(
            len(overlap),
            0,
            f"Found overlap between orientations and modalities: {overlap}",
        )

    def test_cross_contamination_modalities_vs_collections(self) -> None:
        """Modalities should not contain collection codes"""
        url_mod = reverse("archive:valuesets-list") + "?type=modalities"
        url_coll = reverse("archive:valuesets-list") + "?type=collections"

        response_mod = self.client.get(url_mod)
        response_coll = self.client.get(url_coll)

        mod_ids = {item["id"] for item in response_mod.data}
        coll_ids = {item["id"] for item in response_coll.data}

        # No overlap should exist - modalities use DICOM codes,
        # collections use custom IDs
        overlap = mod_ids.intersection(coll_ids)
        self.assertEqual(
            len(overlap),
            0,
            f"Found overlap between modalities and collections: {overlap}",
        )

    def test_unauthenticated_access(self) -> None:
        """Should return 401/403 if not authenticated"""
        self.client.logout()
        url = reverse("archive:valuesets-list") + "?type=sex_options"
        response = self.client.get(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )
