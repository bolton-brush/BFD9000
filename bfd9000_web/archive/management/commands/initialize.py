"""Project initialization command for local development setup."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Any, Literal, TypedDict, cast, final, override

from BFD9000.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import (
    BaseCommand,
    CommandError,
    CommandParser,
    call_command,
)


class _CommandDict(TypedDict):
    skip_migrate: bool
    skip_superuser: bool
    skip_import: bool
    non_interactive: bool
    superuser_username: str | None
    superuser_email: str | None
    superuser_password: str | None
    import_source: Literal["all"] | str
    bolton_file: str
    lancaster_file: str
    richardson_file: str
    include_names: bool
    no_timepoints: bool
    verbosity: str | None


@final
class Command(BaseCommand):
    """Run migrate, create superuser, and import seed subject datasets."""

    help = "Initialize DB: migrate, createsuperuser, import_subjects"

    @override
    def add_arguments(self, parser: CommandParser) -> None:
        _ = parser.add_argument(
            "--skip-migrate",
            action="store_true",
            default=False,
            help="Skip running migrate",
        )
        _ = parser.add_argument(
            "--skip-superuser",
            action="store_true",
            default=False,
            help="Skip running createsuperuser",
        )
        _ = parser.add_argument(
            "--skip-import",
            action="store_true",
            default=False,
            help="Skip running import_subjects",
        )
        _ = parser.add_argument(
            "--non-interactive",
            action="store_true",
            default=False,
            help="Run createsuperuser with --noinput (requires env/options)",
        )

        _ = parser.add_argument("--superuser-username", default=None)
        _ = parser.add_argument("--superuser-email", default=None)
        _ = parser.add_argument("--superuser-password", default=None)

        _ = parser.add_argument(
            "--import-source",
            choices=["all", "bolton", "lancaster", "richardson"],
            default="all",
            help="Which dataset importer(s) to run",
        )
        _ = parser.add_argument(
            "--bolton-file",
            default=str(
                settings.BASE_DIR / "docs" / "collections_data" / "BoltonSubjects2.xlsx"
            ),
            help="Path to BoltonSubjects2.xlsx",
        )
        _ = parser.add_argument(
            "--lancaster-file",
            default=str(
                settings.BASE_DIR
                / "docs"
                / "collections_data"
                / "LancasterDemographic.csv"
            ),
            help="Path to LancasterDemographic.csv",
        )
        _ = parser.add_argument(
            "--richardson-file",
            default=str(
                settings.BASE_DIR
                / "docs"
                / "collections_data"
                / "Richardson Collectionv3.xlsx"
            ),
            help="Path to 'Richardson Collectionv3.xlsx'",
        )
        _ = parser.add_argument(
            "--include-names",
            action="store_true",
            default=False,
            help="Pass --include-names to import_subjects",
        )
        _ = parser.add_argument(
            "--no-timepoints",
            action="store_true",
            default=False,
            help="Pass --no-timepoints to Bolton importer",
        )

    @override
    def handle(self, *_args: Any, **_options: Any) -> None:  # pyright: ignore[reportExplicitAny, reportAny]
        options = cast("_CommandDict", _options)  # pyright: ignore[reportInvalidCast]
        verbosity = int(options.get("verbosity") or "1")

        if not options["skip_migrate"]:
            self.stdout.write(self.style.NOTICE("Running migrate..."))
            _ = call_command("migrate", verbosity=verbosity)

            self.stdout.write(self.style.NOTICE("Importing all valuesets..."))
            try:
                _ = call_command(
                    "import_valuesets",
                    "--all",
                    verbosity=verbosity,
                )
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(f"WARNING: import_valuesets --all failed: {exc}")
                )

        if not options["skip_superuser"]:
            self._run_createsuperuser(options, verbosity)

        if not options["skip_import"]:
            self._run_imports(options, verbosity)

        self.stdout.write(self.style.SUCCESS("Initialization complete."))

    def _run_createsuperuser(self, options: _CommandDict, verbosity: int) -> None:
        user_model = get_user_model()
        if user_model.objects.filter(is_superuser=True).exists():
            self.stdout.write(
                self.style.WARNING(
                    "Superuser already exists; skipping createsuperuser."
                )
            )
            return

        non_interactive = bool(options.get("non_interactive"))
        if non_interactive:
            self._set_superuser_env(options)
            self.stdout.write(self.style.NOTICE("Running createsuperuser --noinput..."))
            try:
                _ = call_command(
                    "createsuperuser", interactive=False, verbosity=verbosity
                )
            except CommandError as exc:
                raise CommandError(
                    textwrap.dedent("""
                    Failed to create superuser non-interactively.
                    Provide --superuser-username/--superuser-email/--superuser-password\
                    or DJANGO_SUPERUSER_* environment variables."
                    """)
                ) from exc
            return

        self.stdout.write(self.style.NOTICE("Running createsuperuser (interactive)..."))
        _ = call_command("createsuperuser", verbosity=verbosity)

    @staticmethod
    def _set_superuser_env(options: _CommandDict) -> None:
        """Set environment variables required by Django's createsuperuser --noinput.

        Security note: This method writes the plaintext password to
        ``os.environ["DJANGO_SUPERUSER_PASSWORD"]``, which is visible in
        ``/proc/<pid>/environ`` on Linux and is commonly captured in process
        listings and CI logs.  This command is intended for **local development
        and CI bootstrapping only** — never use it in a shared or production
        environment where the process environment may be logged or inspected.
        """
        username = options.get("superuser_username")
        email = options.get("superuser_email")
        password = options.get("superuser_password")

        if username:
            os.environ["DJANGO_SUPERUSER_USERNAME"] = str(username)
        if email:
            os.environ["DJANGO_SUPERUSER_EMAIL"] = str(email)
        if password:
            os.environ["DJANGO_SUPERUSER_PASSWORD"] = str(password)

    def _run_imports(self, options: _CommandDict, verbosity: int) -> None:
        source = options["import_source"]
        include_names = bool(options.get("include_names"))

        if source in {"all", "bolton"}:
            bolton_file = Path(options["bolton_file"]).expanduser().resolve()
            self.stdout.write(
                self.style.NOTICE(f"Importing Bolton subjects from {bolton_file}...")
            )
            _ = call_command(
                "import_subjects",
                "bolton",
                file=str(bolton_file),
                include_names=include_names,
                no_timepoints=bool(options.get("no_timepoints")),
                verbosity=verbosity,
            )

        if source in {"all", "lancaster"}:
            lancaster_file = Path(options["lancaster_file"]).expanduser().resolve()
            self.stdout.write(
                self.style.NOTICE(
                    f"Importing Lancaster subjects from {lancaster_file}..."
                )
            )
            _ = call_command(
                "import_subjects",
                "lancaster",
                file=str(lancaster_file),
                include_names=include_names,
                verbosity=verbosity,
            )

        if source in {"all", "richardson"}:
            richardson_file = Path(options["richardson_file"]).expanduser().resolve()
            self.stdout.write(
                self.style.NOTICE(
                    f"Importing Richardson collection from {richardson_file}..."
                )
            )
            _ = call_command(
                "import_subjects",
                "richardson",
                file=str(richardson_file),
                include_names=include_names,
                verbosity=verbosity,
            )
