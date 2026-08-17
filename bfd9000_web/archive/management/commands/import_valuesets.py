"""Command to import FHIR ValueSet expansions"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast, final, override

from django.core.management.base import BaseCommand, CommandError

from archive.constants import VALUESET_EXPAND_URLS
from archive.management.importers.valuesets import import_valueset

if TYPE_CHECKING:
    from django.core.management import CommandParser


class _CommandDict(TypedDict):
    slug: str
    expand_url: str
    all: bool


@final
class Command(BaseCommand):
    """Import FHIR ValueSet expansions"""

    help = (
        "Import FHIR ValueSet expansions. Use --all or provide --slug and --expand-url."
    )

    @override
    def add_arguments(self, parser: CommandParser) -> None:
        _ = parser.add_argument("--slug", type=str, help="Internal ValueSet slug")
        _ = parser.add_argument("--expand-url", type=str, help="FHIR $expand URL")
        _ = parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="Import all valuesets from constants mapping",
        )

    @override
    def handle(self, *_args: Any, **_options) -> None:  # pyright: ignore[reportAny, reportMissingParameterType, reportExplicitAny, reportUnknownParameterType]  # noqa: ANN003
        options = cast("_CommandDict", _options)  # pyright: ignore[reportInvalidCast]
        if options.get("all"):
            if not VALUESET_EXPAND_URLS:
                raise CommandError("No valuesets configured in VALUESET_EXPAND_URLS.")
            for slug, expand_url in VALUESET_EXPAND_URLS.items():
                count = import_valueset(expand_url=expand_url, slug=slug)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Imported {count} codings into ValueSet '{slug}'."
                    )
                )
            return

        slug = options.get("slug")
        expand_url = options.get("expand_url")
        if not slug or not expand_url:
            raise CommandError("Use --all or provide both --slug and --expand-url.")
        count = import_valueset(expand_url=expand_url, slug=slug)
        self.stdout.write(
            self.style.SUCCESS(f"Imported {count} codings into ValueSet '{slug}'.")
        )
