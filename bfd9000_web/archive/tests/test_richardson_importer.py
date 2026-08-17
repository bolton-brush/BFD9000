"""Tests for the Richardson collection importer."""
# pyright: reportUninitializedInstanceVariable=false, reportOptionalMemberAccess=false, reportPrivateUsage=false
# ruff: noqa: S101, DTZ001

from __future__ import annotations

import io
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

import openpyxl
from django.core.management.base import CommandError as DjangoCommandError
from django.test import TestCase

from archive.constants import (
    SYSTEM_IDENTIFIER_RICHARDSON_OLD,
    SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT,
    SYSTEM_PROCEDURE,
    SYSTEM_RECORD_TYPE,
)
from archive.management.importers.richardson import RichardsonImporter
from archive.models import Coding, Encounter, PhysicalLocation, PhysicalRecord, Subject

if TYPE_CHECKING:
    from collections.abc import Sequence

    from openpyxl.cell import _CellGetValue
    from openpyxl.worksheet.worksheet import Worksheet

SNOMED = "http://snomed.info/sct"


def _make_importer(
    *, dry_run: bool = False, include_names: bool = False
) -> RichardsonImporter:
    return RichardsonImporter(
        dry_run=dry_run,
        include_names=include_names,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )


def _make_workbook(
    subject_rows: Sequence[tuple[_CellGetValue, ...]],
    main_rows: Sequence[tuple[_CellGetValue, ...]],
) -> Path:
    """Build a minimal Richardson workbook and save it to a temp file.

    Subject Info layout: rows 0-3 are blank/header; data rows start at index 4.
    Main layout: rows 0-1 are blank header rows; data rows start at index 2.

    Returns:
        The Path to the saved temp file.

    """
    wb = openpyxl.Workbook()

    # ---- Subject Info sheet ----
    ws_si = wb.active
    ws_si.title = "Subject Info"
    # Rows 0-3 blank (4 padding rows so data aligns with index 4)
    for _ in range(4):
        ws_si.append([])
    for row in subject_rows:
        ws_si.append(list(row))

    # ---- Main sheet ----
    ws_main = cast("Worksheet", wb.create_sheet("Main"))
    # Rows 0-1 blank (2 padding rows so data aligns with index 2)
    for _ in range(2):
        ws_main.append([])
    for row in main_rows:
        ws_main.append(list(row))

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.close()
        wb.save(tmp.name)
        return Path(tmp.name)


class RichardsonImporterTestCase(TestCase):  # noqa: PLR0904
    """Base test case that seeds required Coding objects."""

    @override
    def setUp(self) -> None:
        # Skeletal pattern codings (SNOMED) — may already exist from seed migration
        for code, display in [
            ("248292005", "Class I"),
            ("248293000", "Class II"),
            ("248294006", "Class III"),
        ]:
            _ = Coding.objects.get_or_create(
                system=SNOMED, code=code, defaults={"display": display}
            )

        # Record type codings — seeded by import_valuesets in production;
        # create here for tests
        for code, display in [
            ("SM", "Complete Study Model"),
            ("L", "Lateral Cephalogram"),
            ("F", "Frontal Cephalogram"),
            ("OB", "Oblique Cephalogram"),
            ("H", "Radiograph of Hand & Wrist"),
            ("OC", "Occlusal Dental Plain Radiograph"),
            ("UK", "Unknown Record Type"),
            ("PH", "Photograph of Patient"),
            ("RT", "Record of Cephalometric Tracing"),
        ]:
            _ = Coding.objects.get_or_create(
                system=SYSTEM_RECORD_TYPE, code=code, defaults={"display": display}
            )

        # Procedure coding used by BaseImporter._get_or_create_procedure
        _ = Coding.objects.get_or_create(
            system=SYSTEM_PROCEDURE,
            code="historical-import-encounter",
            defaults={"display": "Historical imported encounter"},
        )

    # ------------------------------------------------------------------
    # Subject creation
    # ------------------------------------------------------------------

    def test_subject_created_from_subject_info(self) -> None:
        """A subject row creates a Subject with gender, birth_date, skeletal_pattern."""
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                "FA30",
                None,
                "F",
                "I",
            ),
        ]
        path = _make_workbook(subject_rows, [])
        importer = _make_importer()
        importer.run(path)

        subject = Subject.objects.get(
            identifiers__system=SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT,
            identifiers__value="R001",
        )
        self.assertEqual(subject.birth_date, date(1966, 8, 8))
        self.assertEqual(subject.gender, "female")
        self.assertIsNotNone(subject.skeletal_pattern)
        self.assertEqual(
            subject.skeletal_pattern.code,
            "248292005",
        )  # Class I

    def test_official_and_secondary_identifiers(self) -> None:
        """R number → official identifier; old Richardson number → secondary."""
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                "FA30",
                None,
                "F",
                "I",
            ),
        ]
        path = _make_workbook(subject_rows, [])
        _make_importer().run(path)

        subject = Subject.objects.get(
            identifiers__system=SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT,
            identifiers__value="R001",
        )
        official = subject.identifiers.filter(
            system=SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT, value="R001"
        ).first()
        secondary = subject.identifiers.filter(
            system=SYSTEM_IDENTIFIER_RICHARDSON_OLD, value="FA30"
        ).first()
        self.assertIsNotNone(official)
        self.assertEqual(official.use, "official")
        self.assertIsNotNone(secondary)
        self.assertEqual(secondary.use, "secondary")

    def test_no_secondary_identifier_when_old_id_missing(self) -> None:
        """When old Richardson number is blank, only one identifier is attached."""
        subject_rows = [
            (
                "R002",
                "DOE, JANE",
                datetime(1964, 3, 1, tzinfo=None),
                None,
                None,
                "F",
                "II",
            ),
        ]
        path = _make_workbook(subject_rows, [])
        _make_importer().run(path)

        subject = Subject.objects.get(
            identifiers__system=SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT,
            identifiers__value="R002",
        )
        self.assertEqual(subject.identifiers.count(), 1)
        self.assertFalse(
            subject.identifiers.filter(system=SYSTEM_IDENTIFIER_RICHARDSON_OLD).exists()
        )

    def test_subject_notes_from_misc_column(self) -> None:
        """The misc column in Subject Info populates Subject.notes."""
        subject_rows = [
            (
                "R006",
                "BAGWELL, MARCUS",
                datetime(1962, 2, 20, tzinfo=None),
                "FA1",
                "WATER DAMAGED",
                "M",
                "I",
            ),
        ]
        path = _make_workbook(subject_rows, [])
        _make_importer().run(path)

        subject = Subject.objects.get(
            identifiers__system=SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT,
            identifiers__value="R006",
        )
        self.assertEqual(subject.notes, "WATER DAMAGED")

    def test_include_names_populates_name_fields(self) -> None:
        """Ensures names populate name fields for a Subject

        With --include-names, family and given name are parsed from 'LAST, FIRST' format

        """
        subject_rows = [
            (
                "R001",
                "SMITH, JOHN",
                datetime(1965, 5, 10, tzinfo=None),
                None,
                None,
                "M",
                "I",
            ),
        ]
        path = _make_workbook(subject_rows, [])
        _make_importer(include_names=True).run(path)

        subject = Subject.objects.get(
            identifiers__system=SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT,
            identifiers__value="R001",
        )
        self.assertEqual(subject.humanname_family, "SMITH")
        self.assertEqual(subject.humanname_given, "JOHN")

    def test_names_not_populated_without_flag(self) -> None:
        """Without --include-names, name fields stay None."""
        subject_rows = [
            (
                "R001",
                "SMITH, JOHN",
                datetime(1965, 5, 10, tzinfo=None),
                None,
                None,
                "M",
                "I",
            ),
        ]
        path = _make_workbook(subject_rows, [])
        _make_importer(include_names=False).run(path)

        subject = Subject.objects.get(
            identifiers__system=SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT,
            identifiers__value="R001",
        )
        self.assertIsNone(subject.humanname_family)
        self.assertIsNone(subject.humanname_given)

    # ------------------------------------------------------------------
    # Encounter creation
    # ------------------------------------------------------------------

    def test_encounter_created_from_main_row(self) -> None:
        """A Main sheet row produces one Encounter for (subject, date)."""
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                "FA30",
                None,
                "F",
                "I",
            ),
        ]
        main_rows = [
            (
                None,
                None,
                "R001",
                "F",
                datetime(1966, 8, 8, tzinfo=None),
                "I",
                "study models",
                "None",
                datetime(1972, 2, 15, tzinfo=None),
                "5-6",
                None,
                None,
                "1-A-3",
                None,
            ),
        ]
        path = _make_workbook(subject_rows, main_rows)
        _make_importer().run(path)

        subject = Subject.objects.get(
            identifiers__system=SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT,
            identifiers__value="R001",
        )
        self.assertEqual(Encounter.objects.filter(subject=subject).count(), 1)
        enc = Encounter.objects.get(subject=subject)
        self.assertEqual(enc.actual_period_start, date(1972, 2, 15))
        self.assertEqual(enc.actual_period_start_precision, "day")

    def test_same_date_rows_share_encounter(self) -> None:
        """Ensure two records on the same date share one Encounter."""
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                "FA30",
                None,
                "F",
                "I",
            ),
        ]
        main_rows = [
            (
                None,
                None,
                "R001",
                "F",
                datetime(1966, 8, 8, tzinfo=None),
                "I",
                "study models",
                "None",
                datetime(1972, 8, 8, tzinfo=None),
                "6-0",
                None,
                None,
                "1-A-4",
                None,
            ),
            (
                None,
                None,
                "R001",
                "F",
                datetime(1966, 8, 8, tzinfo=None),
                "I",
                "Radiographs",
                "Lateral",
                datetime(1972, 8, 8, tzinfo=None),
                "6-0",
                None,
                None,
                None,
                None,
            ),
        ]
        path = _make_workbook(subject_rows, main_rows)
        _make_importer().run(path)

        subject = Subject.objects.get(
            identifiers__system=SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT,
            identifiers__value="R001",
        )
        self.assertEqual(Encounter.objects.filter(subject=subject).count(), 1)
        enc = Encounter.objects.get(subject=subject)
        self.assertEqual(PhysicalRecord.objects.filter(encounter=enc).count(), 2)

    # ------------------------------------------------------------------
    # PhysicalRecord fields
    # ------------------------------------------------------------------

    def test_physical_record_box_and_notes(self) -> None:
        """Box and notes are populated on PhysicalRecord from Main cols 12 and 13."""
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                "FA30",
                None,
                "F",
                "I",
            ),
        ]
        main_rows = [
            (
                None,
                None,
                "R001",
                "F",
                datetime(1966, 8, 8, tzinfo=None),
                "I",
                "study models",
                "None",
                datetime(1972, 2, 15, tzinfo=None),
                "5-6",
                None,
                None,
                "1-A-3",
                "only have upper arch",
            ),
        ]
        path = _make_workbook(subject_rows, main_rows)
        _make_importer().run(path)

        rec = PhysicalRecord.objects.first()
        self.assertIsNotNone(rec)
        self.assertEqual(rec.notes, "only have upper arch")
        # Location should be parsed into a PhysicalLocation M2M entry
        self.assertEqual(rec.locations.count(), 1)
        loc = rec.locations.first()
        assert loc is not None
        self.assertEqual(loc.cabinet, "1")
        self.assertEqual(loc.shelf, "A")
        self.assertEqual(loc.slot, "3")

    # ------------------------------------------------------------------
    # Record type mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _run_single_record(modality: str, projection: str) -> PhysicalRecord:
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                None,
                None,
                "F",
                "I",
            ),
        ]
        main_rows = [
            (
                None,
                None,
                "R001",
                None,
                None,
                None,
                modality,
                projection,
                datetime(1972, 8, 8, tzinfo=None),
                None,
                None,
                None,
                None,
                None,
            ),
        ]
        path = _make_workbook(subject_rows, main_rows)
        _make_importer().run(path)
        return cast("PhysicalRecord", PhysicalRecord.objects.first())

    def test_record_type_lateral(self) -> None:
        """Tests various record types"""
        rec = self._run_single_record("Radiographs", "Lateral")
        self.assertEqual(rec.record_type.code, "L")

    def test_record_type_frontal(self) -> None:
        """Tests various record types"""
        rec = self._run_single_record("Radiographs", "Frontal/PA")
        self.assertEqual(rec.record_type.code, "F")

    def test_record_type_oblique(self) -> None:
        """Tests various record types"""
        rec = self._run_single_record("Radiographs", "Oblique")
        self.assertEqual(rec.record_type.code, "OB")

    def test_record_type_hand_wrist(self) -> None:
        """Tests various record types"""
        rec = self._run_single_record("Radiographs", "Hand/Wrist")
        self.assertEqual(rec.record_type.code, "H")

    def test_record_type_occlusal(self) -> None:
        """Tests various record types"""
        rec = self._run_single_record("Radiographs", "Occlusal")
        self.assertEqual(rec.record_type.code, "OC")

    def test_record_type_study_models(self) -> None:
        """Tests various record types"""
        rec = self._run_single_record("study models", "None")
        self.assertEqual(rec.record_type.code, "SM")

    def test_record_type_picture(self) -> None:
        """Tests various record types"""
        rec = self._run_single_record("Picture", "None")
        self.assertEqual(rec.record_type.code, "PH")

    def test_record_type_tracing_lateral(self) -> None:
        """Tests various record types"""
        rec = self._run_single_record("Tracings", "Lateral")
        self.assertEqual(rec.record_type.code, "RT")

    def test_record_type_unknown_radiograph_no_projection(self) -> None:
        """A radiograph with no/None projection maps to UK (unknown)."""
        rec = self._run_single_record("Radiographs", "None")
        self.assertEqual(rec.record_type.code, "UK")

    def test_record_type_default_unknown(self) -> None:
        """An unrecognised (modality, projection) combo defaults to UK."""
        rec = self._run_single_record("Weird Modality", "Weird Projection")
        self.assertEqual(rec.record_type.code, "UK")

    # ------------------------------------------------------------------
    # Duplicate records
    # ------------------------------------------------------------------

    def test_duplicate_records_allowed(self) -> None:
        """Two identical (subject, date, record_type) rows produce two records."""
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                None,
                None,
                "F",
                "I",
            ),
        ]
        main_rows = [
            (
                None,
                None,
                "R001",
                None,
                None,
                None,
                "Picture",
                "None",
                datetime(1974, 6, 13, tzinfo=None),
                None,
                None,
                None,
                None,
                None,
            ),
            (
                None,
                None,
                "R001",
                None,
                None,
                None,
                "Picture",
                "None",
                datetime(1974, 6, 13, tzinfo=None),
                None,
                None,
                None,
                None,
                None,
            ),
        ]
        path = _make_workbook(subject_rows, main_rows)
        _make_importer().run(path)

        self.assertEqual(PhysicalRecord.objects.count(), 2)

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def test_dry_run_does_not_persist(self) -> None:
        """With dry_run=True nothing is written to the database."""
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                "FA30",
                None,
                "F",
                "I",
            ),
        ]
        main_rows = [
            (
                None,
                None,
                "R001",
                None,
                None,
                None,
                "Radiographs",
                "Lateral",
                datetime(1972, 8, 8, tzinfo=None),
                None,
                None,
                None,
                None,
                None,
            ),
        ]
        path = _make_workbook(subject_rows, main_rows)
        _make_importer(dry_run=True).run(path)

        self.assertEqual(Subject.objects.count(), 0)
        self.assertEqual(Encounter.objects.count(), 0)
        self.assertEqual(PhysicalRecord.objects.count(), 0)

    # ------------------------------------------------------------------
    # Error cases
    # ------------------------------------------------------------------

    def test_missing_record_type_coding_raises(self) -> None:
        """If a required record_type Coding is absent, ensure raised

        Ensures CommandError mentions import_valuesets.

        """
        # Remove one required Coding to trigger the error
        _ = Coding.objects.filter(system=SYSTEM_RECORD_TYPE, code="UK").delete()

        path = _make_workbook([], [])
        importer = _make_importer()
        with self.assertRaises(DjangoCommandError) as ctx:
            importer.run(path)
        self.assertIn("import_valuesets", str(ctx.exception))

    def test_header_repeat_rows_skipped(self) -> None:
        """Rows where col 6 is 'modality' are treated as header repeats and skipped."""
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                None,
                None,
                "F",
                "I",
            ),
        ]
        # First row is a header-repeat, second is a real record
        main_rows = [
            (
                None,
                None,
                "R001",
                None,
                None,
                None,
                "modality",
                "projection",
                datetime(1972, 8, 8, tzinfo=None),
                None,
                None,
                None,
                None,
                None,
            ),
            (
                None,
                None,
                "R001",
                None,
                None,
                None,
                "Radiographs",
                "Lateral",
                datetime(1972, 8, 8, tzinfo=None),
                None,
                None,
                None,
                None,
                None,
            ),
        ]
        path = _make_workbook(subject_rows, main_rows)
        _make_importer().run(path)

        self.assertEqual(PhysicalRecord.objects.count(), 1)

    def test_row_with_unknown_r_number_skipped(self) -> None:
        """A Main row referencing an R number not in Subject Info is skipped."""
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                None,
                None,
                "F",
                "I",
            ),
        ]
        main_rows = [
            (
                None,
                None,
                "R999",
                None,
                None,
                None,
                "Radiographs",
                "Lateral",
                datetime(1972, 8, 8, tzinfo=None),
                None,
                None,
                None,
                None,
                None,
            ),
        ]
        path = _make_workbook(subject_rows, main_rows)
        importer = _make_importer()
        importer.run(path)

        self.assertEqual(PhysicalRecord.objects.count(), 0)

    def test_idempotent_subject_import(self) -> None:
        """Running the import twice does not duplicate subjects or identifiers."""
        subject_rows = [
            (
                "R001",
                "ADAMS, LORNA",
                datetime(1966, 8, 8, tzinfo=None),
                "FA30",
                None,
                "F",
                "I",
            ),
        ]
        path = _make_workbook(subject_rows, [])
        _make_importer().run(path)
        _make_importer().run(path)

        self.assertEqual(Subject.objects.count(), 1)
        subject = Subject.objects.first()
        self.assertEqual(
            subject.identifiers.filter(
                system=SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT
            ).count(),
            1,
        )


class ParseBoxLocationTests(RichardsonImporterTestCase):
    """Unit tests for RichardsonImporter._parse_box_locations()."""

    if TYPE_CHECKING:
        importer: RichardsonImporter

    @override
    def setUp(self) -> None:
        super().setUp()
        self.importer = _make_importer()

    def test_simple_single_slot(self) -> None:
        """'1-A-3' → one location: cabinet=1, shelf=A, slot=3."""
        locs = self.importer._parse_box_locations("1-A-3")
        self.assertEqual(len(locs), 1)
        loc = locs[0]
        self.assertIsInstance(loc, PhysicalLocation)
        self.assertEqual(loc.cabinet, "1")
        self.assertEqual(loc.shelf, "A")
        self.assertEqual(loc.slot, "3")

    def test_two_slots_same_shelf(self) -> None:
        """'1-A-16/17' → two locations: (1,A,16) and (1,A,17)."""
        locs = self.importer._parse_box_locations("1-A-16/17")
        self.assertEqual(len(locs), 2)
        cabinets = {loc.cabinet for loc in locs}
        shelves = {loc.shelf for loc in locs}
        slots = {loc.slot for loc in locs}
        self.assertEqual(cabinets, {"1"})
        self.assertEqual(shelves, {"A"})
        self.assertEqual(slots, {"16", "17"})

    def test_two_slots_spanning_shelves(self) -> None:
        """'1-A-30/B-1' → two locations: (1,A,30) and (1,B,1)."""
        locs = self.importer._parse_box_locations("1-A-30/B-1")
        self.assertEqual(len(locs), 2)
        by_shelf = {loc.shelf: loc for loc in locs}
        self.assertIn("A", by_shelf)
        self.assertIn("B", by_shelf)
        self.assertEqual(by_shelf["A"].slot, "30")
        self.assertEqual(by_shelf["B"].slot, "1")
        self.assertEqual(by_shelf["A"].cabinet, "1")
        self.assertEqual(by_shelf["B"].cabinet, "1")

    def test_two_slots_no_shelf_inferred(self) -> None:
        """'10-9/10' (missing shelf) → two locations with inferred shelf 'A'."""
        locs = self.importer._parse_box_locations("10-9/10")
        self.assertEqual(len(locs), 2)
        for loc in locs:
            self.assertEqual(loc.cabinet, "10")
            self.assertEqual(loc.shelf, "A")
        slots = {loc.slot for loc in locs}
        self.assertEqual(slots, {"9", "10"})

    def test_freeform_text(self) -> None:
        """'R Archive Box' (no hyphens)

        → one location with cabinet=raw, shelf='', slot=''.

        """
        locs = self.importer._parse_box_locations("R Archive Box")
        self.assertEqual(len(locs), 1)
        loc = locs[0]
        self.assertEqual(loc.cabinet, "R Archive Box")
        self.assertEqual(loc.shelf, "")
        self.assertEqual(loc.slot, "")

    def test_deduplication(self) -> None:
        """Parsing the same string twice returns the same PhysicalLocation row

        (get_or_create)

        """
        locs1 = self.importer._parse_box_locations("2-B-5")
        locs2 = self.importer._parse_box_locations("2-B-5")
        self.assertEqual(locs1[0].pk, locs2[0].pk)
