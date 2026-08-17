"""Importer for the Lancaster demographic CSV."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, final

from django.core.management.base import CommandError
from django.db import transaction

from archive.management.importers.base import BaseImporter, ImportStats, Writeable
from archive.models import Coding, Collection, Encounter, Subject

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


@dataclass
class LancasterStats(ImportStats):
    """Import counters specific to the Lancaster dataset."""

    encounters_created: int = 0
    encounters_skipped: int = 0
    partial_dates: int = 0
    uncertain_dates: int = 0


@final
class LancasterImporter(BaseImporter):
    """Import Lancaster subjects and derived encounters from CSV data."""

    DATE_COLUMNS = (7, 9, 11, 13, 15, 17)

    def __init__(
        self,
        *,
        dry_run: bool,
        include_names: bool,
        stdout: Writeable,
        stderr: Writeable,
        identifier_prefix: str,
        identifier_width: int,
        identifier_system: str,
        collection_short_name: str,
        collection_full_name: str | None,
    ) -> None:
        """Initializes the Lancaster Data Importer"""
        super().__init__(
            dry_run=dry_run, include_names=include_names, stdout=stdout, stderr=stderr
        )
        self.identifier_prefix = identifier_prefix
        self.identifier_width = identifier_width
        self.identifier_system = identifier_system
        self.collection_short_name = collection_short_name
        self.collection_full_name = collection_full_name

    def run(self, file_path: Path) -> None:
        """Execute the Lancaster import from the provided CSV path.

        Raises:
            CommandError: If reading the csv file has any issues

        """
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        stats = LancasterStats()
        procedure_code = self._get_or_create_procedure()

        if self.dry_run:
            self.stdout.write("Dry run enabled: no database writes will occur.")

        with file_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if not header:
                raise CommandError("Missing header row")

            index = self._build_header_index(header)
            collection = self._get_or_create_collection(
                self.collection_short_name,
                self.collection_full_name,
            )

            with transaction.atomic():
                for row in reader:
                    if not row or all(
                        cell is None or not str(cell).strip() for cell in row
                    ):
                        continue
                    try:
                        self._import_row(row, index, collection, procedure_code, stats)
                    except CommandError as exc:
                        stats.rows_skipped += 1
                        self.stderr.write(str(exc))

                if self.dry_run:
                    transaction.set_rollback(True)
                    self.stdout.write("Dry run complete. Rolling back transaction.")
                    self._print_summary(stats)
                    return

        self._print_summary(stats)

    @staticmethod
    def _build_header_index(header: Iterable[str]) -> dict[str, int]:
        normalized = [str(value).strip().lower() for value in header]
        required = ["last", "first", "pt. no.", "sex", "dob"]
        missing = [name for name in required if name not in normalized]
        if missing:
            raise CommandError(f"Missing required columns: {', '.join(missing)}")
        return {name: normalized.index(name) for name in required}

    def _import_row(
        self,
        row: list[str],
        index: dict[str, int],
        collection: Collection,
        procedure_code: Coding,
        stats: LancasterStats,
    ) -> None:
        last_name = self._cell_str(row[index["last"]])
        first_name = self._cell_str(row[index["first"]])
        patient_number = self._cell_str(row[index["pt. no."]])
        sex_value = self._cell_str(row[index["sex"]])
        birth_date_value = self._cell_str(row[index["dob"]])

        if not patient_number or not birth_date_value:
            raise CommandError(
                f"Skipping row with missing required values: {patient_number}"
            )

        subject_identifier = self._format_identifier(patient_number)
        subject = self._get_subject_by_identifier(subject_identifier)
        is_new_subject = subject is None

        birth_date = self._parse_birth_date(birth_date_value)

        if subject is None:
            subject = Subject.objects.create(
                gender=self._map_gender(sex_value),
                birth_date=birth_date,
                collection=collection,
                humanname_family=last_name if self.include_names else None,
                humanname_given=first_name if self.include_names else None,
            )
            stats.subjects_created += 1
        else:
            updated = False
            gender = self._map_gender(sex_value)
            if sex_value and subject.gender != gender:
                subject.gender = gender
                updated = True
            if subject.birth_date != birth_date:
                subject.birth_date = birth_date
                updated = True
            if subject.collection_id is None:
                subject.collection = collection
                updated = True
            if self.include_names:
                if last_name and subject.humanname_family != last_name:
                    subject.humanname_family = last_name
                    updated = True
                if first_name and subject.humanname_given != first_name:
                    subject.humanname_given = first_name
                    updated = True
            if updated:
                subject.save()
                stats.subjects_updated += 1

        self._attach_identifier(
            subject,
            self.identifier_system,
            subject_identifier,
            use="official",
            stats=stats,
        )

        self._import_encounters(row, subject, birth_date, procedure_code, stats)

        if not is_new_subject and subject.pk:
            subject.save()

    def _format_identifier(self, value: str) -> str:
        padded = value.zfill(self.identifier_width)
        return f"{self.identifier_prefix}{padded}"

    def _parse_birth_date(self, value: str) -> date:
        raw = value.strip()
        return self._parse_full_date(raw)

    def _parse_full_date(self, token: str) -> date:
        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", token)
        if not match:
            raise CommandError(f"Invalid DOB format: {token}")
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        if year < 100:  # noqa: PLR2004
            year = self._expand_two_digit_year(year)
        return date(year, month, day)

    def _import_encounters(
        self,
        row: list[str],
        subject: Subject,
        birth_date: date,
        procedure_code: Coding,
        stats: LancasterStats,
    ) -> None:
        seen: set[tuple[date, str, str]] = set()
        for column_index in self.DATE_COLUMNS:
            if column_index >= len(row):
                continue
            raw_cell = self._cell_str(row[column_index])
            if not raw_cell:
                continue
            tokens = [token.strip() for token in raw_cell.split(";") if token.strip()]
            for token in tokens:
                parsed = self._parse_encounter_token(token, birth_date)
                if parsed is None:
                    stats.encounters_skipped += 1
                    continue
                encounter_date, precision, uncertain, raw = parsed
                key = (encounter_date, precision, raw)
                if key in seen:
                    continue
                seen.add(key)

                if precision != "day":
                    stats.partial_dates += 1
                if uncertain:
                    stats.uncertain_dates += 1

                if Encounter.objects.filter(
                    subject=subject,
                    actual_period_start=encounter_date,
                    actual_period_start_raw=raw,
                ).exists():
                    stats.encounters_skipped += 1
                    continue

                _ = Encounter.objects.create(
                    subject=subject,
                    actual_period_start=encounter_date,
                    procedure_code=procedure_code,
                    actual_period_start_raw=raw,
                    actual_period_start_precision=precision,
                    actual_period_start_uncertain=uncertain,
                )
                stats.encounters_created += 1

    @classmethod
    def _parse_encounter_token(
        cls,
        token: str,
        birth_date: date,
    ) -> tuple[date, str, bool, str] | None:
        raw = token.strip()
        if not raw:
            return None

        if "age:" in raw.lower():
            return cls._parse_age_token(raw, birth_date)

        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", raw)
        if match:
            month, day, year = (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
            if year < 100:  # noqa: PLR2004
                year = cls._expand_two_digit_year(year)
            return date(year, month, day), "day", False, raw

        match = re.match(r"^(\d{1,2})/(\d{2,4})$", raw)
        if match:
            month, year = (int(match.group(1)), int(match.group(2)))
            if year < 100:  # noqa: PLR2004
                year = cls._expand_two_digit_year(year)
            return cls._midpoint_for_month(year, month), "month", True, raw

        match = re.match(r"^(\d{4})$", raw)
        if match:
            year = int(match.group(1))
            return cls._midpoint_date_for_year(year), "year", True, raw

        match = re.match(r"^(\d{1,2})/\?/(\d{2,4})$", raw)
        if match:
            month, year = (int(match.group(1)), int(match.group(2)))
            if year < 100:  # noqa: PLR2004
                year = cls._expand_two_digit_year(year)
            return cls._midpoint_for_month(year, month), "month", True, raw

        match = re.match(r"^\?/\?/(\d{2,4})$", raw)
        if match:
            year = int(match.group(1))
            if year < 100:  # noqa: PLR2004
                year = cls._expand_two_digit_year(year)
            return cls._midpoint_date_for_year(year), "year", True, raw

        return None

    @classmethod
    def _parse_age_token(
        cls, raw: str, birth_date: date
    ) -> tuple[date, str, bool, str] | None:
        match = re.search(
            r"age:\s*(\d+)\s*(years?|yrs?|y|months?|mos?|mo|days?|d)",
            raw.lower(),
        )
        if not match:
            return None
        value = int(match.group(1))
        unit = match.group(2)

        if unit.startswith("y"):
            target_year = birth_date.year + value
            return cls._midpoint_date_for_year(target_year), "year", True, raw
        if unit.startswith("m"):
            target = cls._add_months(birth_date, value)
            return (
                cls._midpoint_for_month(target.year, target.month),
                "month",
                True,
                raw,
            )
        if unit.startswith("d"):
            return birth_date + timedelta(days=value), "day", True, raw
        return None

    @classmethod
    def _add_months(cls, value: date, months: int) -> date:
        year = value.year + (value.month - 1 + months) // 12
        month = (value.month - 1 + months) % 12 + 1
        return date(year, month, min(value.day, cls._days_in_month(year, month)))

    @classmethod
    def _midpoint_for_month(cls, year: int, month: int) -> date:
        mid_day = (cls._days_in_month(year, month) + 1) // 2
        return date(year, month, mid_day)

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        next_month = date(year, month, 1).replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        return last_day.day

    def _get_subject_by_identifier(self, value: str) -> Subject | None:
        return (
            Subject.objects.filter(
                identifiers__system=self.identifier_system,
                identifiers__value=value,
            )
            .distinct()
            .first()
        )

    def _print_summary(self, stats: LancasterStats) -> None:
        self.stdout.write("Import complete")
        self.stdout.write(f"Subjects created: {stats.subjects_created}")
        self.stdout.write(f"Subjects updated: {stats.subjects_updated}")
        self.stdout.write(f"Identifiers created: {stats.identifiers_created}")
        self.stdout.write(f"Identifiers attached: {stats.identifiers_attached}")
        self.stdout.write(f"Encounters created: {stats.encounters_created}")
        self.stdout.write(f"Encounters skipped: {stats.encounters_skipped}")
        self.stdout.write(f"Partial date encounters: {stats.partial_dates}")
        self.stdout.write(f"Uncertain date encounters: {stats.uncertain_dates}")
        self.stdout.write(f"Rows skipped: {stats.rows_skipped}")
