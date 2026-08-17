"""Synthetic data generator for testing"""
# ruff: noqa: S311

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING

from django.db import transaction

from archive.constants import (
    SYSTEM_PROCEDURE,
    SYSTEM_RECORD_TYPE,
)
from archive.models import (
    Coding,
    Collection,
    Encounter,
    Identifier,
    PhysicalLocation,
    PhysicalRecord,
    Subject,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


class DynamicSyntheticDataGenerator:
    """A Class for creating synthetic testing data"""

    # --- Configurable Generative Defaults ---
    DEFAULT_NUM_SUBJECTS_PER_COLLECTION = 100
    DEFAULT_COLLECTIONS = ("Magni", "Hans", "Wilfred", "Alwyn", "Stone")

    # --- Identifiers and Namespaces ---
    BASE_SYSTEM_ID_PREFIX = "SYSTEM_IDENTIFIER_"
    SYSTEM_OFFICIAL_SUFFIX = "_OFFICIAL"
    SYSTEM_SECONDARY_SUFFIX = "_SECONDARY"

    IDENTIFIER_USE_OFFICIAL = "official"
    IDENTIFIER_USE_SECONDARY = "secondary"

    # --- Terminology and Coding Systems ---
    SKELETAL_SYSTEM = "http://snomed.info/sct"
    RACE_SYSTEM = "urn:oid:2.16.840.1.113883.6.238"

    PROCEDURE_CODE_VALUE = "historical-import-encounter"
    PROCEDURE_DISPLAY_VALUE = "Historical imported encounter"

    # --- Demographics and Precision Options ---
    GENDERS = ("male", "female", "unknown")
    PRECISION_DAY = "day"
    PRECISION_MONTH = "month"
    PRECISION_YEAR = "year"
    PRECISION_CHOICES = (PRECISION_DAY, PRECISION_MONTH, PRECISION_YEAR)

    # --- Value Sets Mapping ---
    SKELETAL_CODES = MappingProxyType(
        {
            "248292005": "Class I",
            "248293000": "Class II",
            "248294006": "Class III",
        }
    )

    RACE_CODES = MappingProxyType(
        {
            "2106-3": "White",
            "2054-5": "Black or African American",
        }
    )

    REQUIRED_RECORD_TYPE_CODES = ("SM", "L", "F", "P", "H", "RE", "RF", "FM", "SU")

    # --- Structural Pre-seed Constants ---
    MOCK_CABINETS = ("1", "5", "12")
    MOCK_SHELVES = ("A", "C")
    MOCK_SLOTS = ("10", "22")

    # --- Date Generation Anchors ---
    BASE_BIRTH_DATE = date(1995, 6, 15)
    DATE_OFFSET_RANGE = 3650  # ~10 years variance

    MIN_ENCOUNTERS_PER_SUBJECT = 2
    MAX_ENCOUNTERS_PER_SUBJECT = 5
    ENCOUNTER_YEAR_MULTIPLIERS = (1, 2)
    DAYS_IN_YEAR = 365

    @classmethod
    def seed_required_codings(
        cls,
    ) -> tuple[Coding, list[Coding], list[Coding], list[Coding]]:
        """Pre-populates necessary database lookup metadata rows securely.

        Returns:
            Codings for procedure, skeletals, races, and a cache for record types

        """
        procedure_code, _ = Coding.objects.get_or_create(
            system=SYSTEM_PROCEDURE,
            code=cls.PROCEDURE_CODE_VALUE,
            defaults={"display": cls.PROCEDURE_DISPLAY_VALUE},
        )

        skeletal_objs = [
            Coding.objects.get_or_create(
                system=cls.SKELETAL_SYSTEM, code=c, defaults={"display": d}
            )[0]
            for c, d in cls.SKELETAL_CODES.items()
        ]
        race_objs = [
            Coding.objects.get_or_create(
                system=cls.RACE_SYSTEM, code=c, defaults={"display": d}
            )[0]
            for c, d in cls.RACE_CODES.items()
        ]

        record_type_cache = {}
        for code in cls.REQUIRED_RECORD_TYPE_CODES:
            obj, _ = Coding.objects.get_or_create(
                system=SYSTEM_RECORD_TYPE,
                code=code,
                defaults={"display": f"Record Type {code}"},
            )
            record_type_cache[code] = obj

        return procedure_code, skeletal_objs, race_objs, record_type_cache

    @classmethod
    def execute(  # noqa: PLR0914
        cls,
        collections_list: Iterable[str] | None = None,
        subjects_per_collection: int | None = None,
    ) -> None:
        """Generates mock pipelines dynamically for any string iterable of collections.

        Args:
            collections_list: A list of collection names to generate
            subjects_per_collection: Number of subjects to create per collection

        """
        # Resolve arguments against class constants
        collections = (
            collections_list
            if collections_list is not None
            else cls.DEFAULT_COLLECTIONS
        )
        num_subjects = (
            subjects_per_collection
            if subjects_per_collection is not None
            else cls.DEFAULT_NUM_SUBJECTS_PER_COLLECTION
        )

        print(
            f"Beginning pipeline data population across {
                len(collections)
            } dynamic collections..."
        )

        with transaction.atomic():
            procedure_code, skeletal_objs, race_objs, record_type_cache = (
                cls.seed_required_codings()
            )

            # Pre-seed physical storage parameters
            mock_locations = []
            for cabinet in cls.MOCK_CABINETS:
                for shelf in cls.MOCK_SHELVES:
                    for slot in cls.MOCK_SLOTS:
                        loc, _ = PhysicalLocation.objects.get_or_create(
                            cabinet=cabinet,
                            shelf=shelf,
                            slot=slot,
                            defaults={"raw": f"{cabinet}-{shelf}-{slot}"},
                        )
                        mock_locations.append(loc)

            for col_name in collections:
                short_name = col_name.strip().upper()
                full_name = f"{col_name.strip()} Synthetic Generated Collection"

                collection_obj, _ = Collection.objects.get_or_create(
                    short_name=short_name, defaults={"full_name": full_name}
                )

                # Dynamic identification systems mapping
                system_id_official = f"{cls.BASE_SYSTEM_ID_PREFIX}{short_name}{
                    cls.SYSTEM_OFFICIAL_SUFFIX
                }"
                system_id_secondary = f"{cls.BASE_SYSTEM_ID_PREFIX}{short_name}{
                    cls.SYSTEM_SECONDARY_SUFFIX
                }"

                print(
                    f" -> Processing collection '{short_name}': Generating {
                        num_subjects
                    } subjects..."
                )

                for i in range(1, num_subjects + 1):
                    # Localized timeline variance variables per Subject
                    shared_birth = cls.BASE_BIRTH_DATE + timedelta(
                        days=random.randint(
                            -cls.DATE_OFFSET_RANGE, cls.DATE_OFFSET_RANGE
                        )
                    )
                    shared_gender = random.choice(cls.GENDERS)

                    # Create core profile
                    subject = Subject.objects.create(
                        gender=shared_gender,
                        birth_date=shared_birth,
                        collection=collection_obj,
                        ethnicity=random.choice([*race_objs, None]),
                        skeletal_pattern=random.choice([*skeletal_objs, None]),
                        humanname_family=f"{col_name}Family{i}",
                        humanname_given=f"Subject{i}",
                        notes=f"Generated profiling data for row index {i} under {
                            short_name
                        }.",
                    )

                    # Unique identifier definitions
                    id_val_1 = f"{short_name[:3]}-{1000 + i}"
                    id_val_2 = f"{short_name[:3]}SEC-{5000 + i}"

                    id_official = Identifier.objects.create(
                        system=system_id_official,
                        value=id_val_1,
                        use=cls.IDENTIFIER_USE_OFFICIAL,
                    )
                    id_secondary = Identifier.objects.create(
                        system=system_id_secondary,
                        value=id_val_2,
                        use=cls.IDENTIFIER_USE_SECONDARY,
                    )
                    subject.identifiers.add(id_official, id_secondary)

                    # --- INDEPENDENT ENCOUNTER PIPELINE LOOP ---
                    num_encounters = random.randint(
                        cls.MIN_ENCOUNTERS_PER_SUBJECT, cls.MAX_ENCOUNTERS_PER_SUBJECT
                    )

                    for k in range(1, num_encounters + 1):
                        year_jump = (
                            cls.DAYS_IN_YEAR
                            * k
                            * random.choice(cls.ENCOUNTER_YEAR_MULTIPLIERS)
                        )
                        enc_date = shared_birth + timedelta(days=year_jump)

                        precision = random.choice(cls.PRECISION_CHOICES)

                        if precision == cls.PRECISION_DAY:
                            uncertain = False
                            raw_string = enc_date.isoformat()
                        elif precision == cls.PRECISION_MONTH:
                            uncertain = True
                            raw_string = (
                                f"{enc_date.strftime('%m')}/?/{enc_date.strftime('%Y')}"
                            )
                        else:  # PRECISION_YEAR
                            uncertain = True
                            raw_string = enc_date.strftime("%Y")

                        encounter = Encounter.objects.create(
                            subject=subject,
                            actual_period_start=enc_date,
                            actual_period_start_raw=raw_string,
                            actual_period_start_precision=precision,
                            actual_period_start_uncertain=uncertain,
                            procedure_code=procedure_code,
                        )

                        if random.choice([True, False]):
                            chosen_code = random.choice(cls.REQUIRED_RECORD_TYPE_CODES)
                            acq_dt = datetime.combine(
                                enc_date, datetime.min.time(), tzinfo=UTC
                            )

                            pr = PhysicalRecord.objects.create(
                                encounter=encounter,
                                record_type=record_type_cache[chosen_code],
                                acquisition_datetime=acq_dt,
                                notes=f"Independent specimen asset mapping. Type: {
                                    chosen_code
                                }",
                            )
                            # Binds 1 or 2 randomized locations out of the shared pool
                            pr.locations.set(
                                random.sample(mock_locations, random.randint(1, 2))
                            )

        print("Database population complete across all dynamic lists.")


if __name__ == "__main__":
    DynamicSyntheticDataGenerator.execute()
