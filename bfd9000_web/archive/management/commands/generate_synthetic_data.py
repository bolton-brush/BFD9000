"""Django command for seeding synthetic data"""

from __future__ import annotations

from typing import override

from django.core.management import BaseCommand, CommandParser

from archive.management.importers.synthetic import DynamicSyntheticDataGenerator


class Command(BaseCommand):
    """Generates synthetic, randomized mock pipeline records for tests or development"""

    help = (
        "Generates synthetic, randomized mock pipeline records"
        + " for tests or development sandbox profiles."
    )

    @override
    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--collections",
            nargs="+",
            type=str,
            default=list(DynamicSyntheticDataGenerator.DEFAULT_COLLECTIONS),
            help="Space-separated list of collection name strings to process.",
        )
        parser.add_argument(
            "--subjects-per-collection",
            type=int,
            default=DynamicSyntheticDataGenerator.DEFAULT_NUM_SUBJECTS_PER_COLLECTION,
            help="Number of Subject items per collection.",
        )

    @override
    def handle(self, *_args, **_options) -> None:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]  # noqa: ANN002, ANN003
        collections_list = _options["collections"]
        subjects_count = _options["subjects_per_collection"]

        self.stdout.write(
            self.style.MIGRATE_HEADING("Launching Pipeline Generation Script...")
        )

        DynamicSyntheticDataGenerator.execute(
            collections_list=collections_list,
            subjects_per_collection=subjects_count,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Successfully seeded synthetic database infrastructure rows!"
            )
        )
