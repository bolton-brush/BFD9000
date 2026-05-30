"""Shared helpers for dataset importers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from django.core.management.base import CommandError
from typing_extensions import override

from archive.constants import SYSTEM_PROCEDURE
from archive.models import Coding, Collection, GenderLiteral, Identifier, Subject


class Stringable(Protocol):
    """Anything that can become a string"""

    @override
    def __str__(self) -> str: ...


@runtime_checkable
class Dateable(Protocol):
    """Anything that might have a date on it"""

    def date(self) -> date:
        """A function that returns a possible date"""
        ...


class Writeable(Protocol):
    """Anything that can be written to, matching both StringIO and OutputWrapper."""

    def write(  # pyright: ignore[reportAny]
        self,
        s: str,
        /,
        *args: Any,  # pyright: ignore[reportExplicitAny, reportAny]  # noqa: ANN401
        **kwargs: Any,  # pyright: ignore[reportExplicitAny, reportAny]  # noqa: ANN401
    ) -> Any:  # pyright: ignore[reportExplicitAny]  # noqa: ANN401
        """The write function"""
        ...


@dataclass
class ImportStats:
    """Basic counters for import progress reporting."""

    subjects_created: int = 0
    subjects_updated: int = 0
    identifiers_created: int = 0
    identifiers_attached: int = 0
    rows_skipped: int = 0


@dataclass
class BaseImporter:
    """Common helper methods used across dataset importers."""

    def __init__(
        self,
        *,
        dry_run: bool,
        include_names: bool,
        stdout: Writeable,
        stderr: Writeable,
    ) -> None:
        """Base importer for any data"""
        self.dry_run: bool = dry_run
        self.include_names: bool = include_names
        self.stdout: Writeable = stdout
        self.stderr: Writeable = stderr

    @staticmethod
    def _get_or_create_collection(
        short_name: str, full_name: str | None = None
    ) -> Collection:
        full_name_value = full_name or short_name
        collection, _ = Collection.objects.get_or_create(
            short_name=short_name,
            defaults={"full_name": full_name_value},
        )
        return collection

    @staticmethod
    def _attach_identifier(
        subject: Subject,
        system: str,
        value: str,
        use: str,
        stats: ImportStats,
    ) -> None:
        identifier, created = Identifier.objects.get_or_create(
            system=system,
            value=value,
            defaults={"use": use},
        )
        if created:
            stats.identifiers_created += 1
        if not subject.identifiers.filter(pk=identifier.pk).exists():
            subject.identifiers.add(identifier)
            stats.identifiers_attached += 1

    @staticmethod
    def _map_gender(value: str) -> GenderLiteral:
        gender_map: dict[str, GenderLiteral] = {
            label.upper(): key for key, label in Subject.GENDER_CHOICES
        }
        normalized = value.strip().upper()
        return gender_map.get(normalized, "unknown")

    @staticmethod
    def _normalize_date(value: datetime | date | Dateable | Stringable) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, Dateable):
            return value.date()
        raw = str(value).strip()
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            pass
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise CommandError(f"Invalid date format: {value}") from exc

    @staticmethod
    def _get_or_create_procedure() -> Coding:
        procedure, _ = Coding.objects.get_or_create(
            system=SYSTEM_PROCEDURE,
            code="historical-import-encounter",
            defaults={"display": "Historical imported encounter"},
        )
        return procedure

    @staticmethod
    def _cell_str(value: Stringable) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _expand_two_digit_year(year: int) -> int:
        # TODO: Update when its 2030 :)
        if year >= 30:  # noqa: PLR2004
            return 1900 + year
        return 2000 + year

    @staticmethod
    def _midpoint_date_for_year(year: int) -> date:
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)
        midpoint_days = (end - start).days // 2
        return start + timedelta(days=midpoint_days)

    @staticmethod
    def _build_class_codes() -> dict[str, str | None]:
        """Map Angle/molar class labels to SNOMED codes.

        Returns:
            Map of class codes to SNOMED codes

        """
        return {
            "Class I": "248292005",
            "Class II": "248293000",
            "Class III": "248294006",
            "NULL": None,
        }

    @staticmethod
    def _load_skeletal_coding_cache() -> dict[tuple[str, str], Coding]:
        """Load SNOMED skeletal-pattern Coding objects into a cache dict.

        Returns:
            A cached dictionary keyed by (system, code)

        Raises:
            CommandError: If could not obtain codes from the database

        """
        skeletal_system = "http://snomed.info/sct"
        skeletal_codes = ["248292005", "248293000", "248294006"]
        codings = Coding.objects.filter(system=skeletal_system, code__in=skeletal_codes)
        cache: dict[tuple[str, str], Coding] = {(c.system, c.code): c for c in codings}
        missing = [
            code for code in skeletal_codes if (skeletal_system, code) not in cache
        ]
        if missing:
            raise CommandError(
                "Missing SNOMED skeletal Coding entries. Run migrations to seed codes. "
                + f"Missing: {', '.join(missing)}"
            )
        return cache

    @staticmethod
    def _resolve_skeletal_pattern(
        label: str,
        class_codes: dict[str, str | None],
        coding_cache: dict[tuple[str, str], Coding],
    ) -> Coding | None:
        """Return the Coding for an Angle class label (e.g. 'Class I'), or None.

        Returns:
            Skeletal coding if found, None else

        """
        if not label:
            return None
        code = class_codes.get(label.strip())
        if not code:
            return None
        return coding_cache.get(("http://snomed.info/sct", code))
