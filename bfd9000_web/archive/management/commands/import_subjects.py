"""Management command entrypoint for historical imports."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict, cast, final

from django.core.management.base import BaseCommand, CommandError
from typing_extensions import override

from archive.constants import SYSTEM_IDENTIFIER_LANCASTER_SUBJECT
from archive.management.importers.bolton import BoltonImporter
from archive.management.importers.lancaster import LancasterImporter
from archive.management.importers.richardson import RichardsonImporter

if TYPE_CHECKING:
    from django.core.management import CommandParser


class _BoltonDict(TypedDict):
    source: Literal["bolton"]
    file: str
    dry_run: bool
    include_names: bool
    timepoints_file: str | None
    no_timepoints: bool


class _LancasterDict(TypedDict):
    source: Literal["lancaster"]
    file: str
    dry_run: bool
    include_names: bool
    identifier_prefix: str
    identifier_width: int
    identifier_system: str
    collection_short_name: str
    collection_full_name: str


class _RichardsonDict(TypedDict):
    source: Literal["richardson"]
    file: str
    dry_run: bool
    include_names: bool


_CommandDict = _BoltonDict | _LancasterDict | _RichardsonDict


@final
class Command(BaseCommand):
    """Dispatch imports by dataset source."""

    help = "Import historical subjects from supported datasets"

    @override
    def add_arguments(self, parser: CommandParser) -> None:
        subparsers = parser.add_subparsers(dest="source", required=True)

        bolton = subparsers.add_parser("bolton", help="Import Bolton subjects")
        _ = bolton.add_argument(
            "--file",
            default="BoltonSubjects2.xlsx",
            help="Path to BoltonSubjects2.xlsx",
        )
        _ = bolton.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Parse and validate without writing to the database",
        )
        _ = bolton.add_argument(
            "--include-names",
            action="store_true",
            default=False,
            help="Populate first/last names when available",
        )
        _ = bolton.add_argument(
            "--timepoints-file",
            default=None,
            help="Path to BoltonTimepoints2.csv "
            + "(defaults to bundled docs/collections_data)",
        )
        _ = bolton.add_argument(
            "--no-timepoints",
            action="store_true",
            default=False,
            help="Do not import timepoints (skip creating Encounters)",
        )

        lancaster = subparsers.add_parser("lancaster", help="Import Lancaster subjects")
        _ = lancaster.add_argument(
            "--file",
            default="LancasterDemographic.csv",
            help="Path to LancasterDemographic.csv",
        )
        _ = lancaster.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Parse and validate without writing to the database",
        )
        _ = lancaster.add_argument(
            "--include-names",
            action="store_true",
            default=False,
            help="Populate first/last names when available",
        )
        _ = lancaster.add_argument(
            "--identifier-prefix",
            default="L",
            help="Prefix for formatted Lancaster identifiers",
        )
        _ = lancaster.add_argument(
            "--identifier-width",
            type=int,
            default=8,
            help="Zero-padding width for Lancaster identifiers",
        )
        _ = lancaster.add_argument(
            "--identifier-system",
            default=SYSTEM_IDENTIFIER_LANCASTER_SUBJECT,
            help="Identifier system URL for Lancaster subjects",
        )
        _ = lancaster.add_argument(
            "--collection-short-name",
            default="Lancaster",
            help="Collection short name for Lancaster dataset",
        )
        _ = lancaster.add_argument(
            "--collection-full-name",
            default="Lancaster",
            help="Collection full name for Lancaster dataset",
        )

        richardson = subparsers.add_parser(
            "richardson", help="Import Richardson subjects and physical records"
        )
        _ = richardson.add_argument(
            "--file",
            default=str(
                Path(__file__).resolve().parents[4]
                / "docs"
                / "collections_data"
                / "Richardson Collectionv3.xlsx"
            ),
            help="Path to 'Richardson Collectionv3.xlsx'",
        )
        _ = richardson.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Parse and validate without writing to the database",
        )
        _ = richardson.add_argument(
            "--include-names",
            action="store_true",
            default=False,
            help="Populate first/last names when available (PHI — use with caution)",
        )

    @override
    def handle(self, *_args, **_options) -> None:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]  # noqa: ANN002, ANN003
        options = cast("_CommandDict", _options)  # pyright: ignore[reportInvalidCast]
        if options["source"] == "bolton":
            importer = BoltonImporter(
                dry_run=options["dry_run"],
                include_names=options["include_names"],
                stdout=self.stdout,
                stderr=self.stderr,
                timepoints_file=options.get("timepoints_file"),
                skip_timepoints=options.get("no_timepoints", False),
            )
            importer.run(Path(options["file"]).expanduser().resolve())
            return

        if options["source"] == "lancaster":
            importer = LancasterImporter(
                dry_run=options["dry_run"],
                include_names=options["include_names"],
                stdout=self.stdout,
                stderr=self.stderr,
                identifier_prefix=options["identifier_prefix"],
                identifier_width=options["identifier_width"],
                identifier_system=options["identifier_system"],
                collection_short_name=options["collection_short_name"],
                collection_full_name=options["collection_full_name"],
            )
            importer.run(Path(options["file"]).expanduser().resolve())
            return

        if options["source"] == "richardson":
            importer = RichardsonImporter(
                dry_run=options["dry_run"],
                include_names=options["include_names"],
                stdout=self.stdout,
                stderr=self.stderr,
            )
            importer.run(Path(options["file"]).expanduser().resolve())
            return

        raise CommandError(f"Unknown import source: {options['source']}")
