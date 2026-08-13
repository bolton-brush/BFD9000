"""Small helper function to print all Django registered URLs"""

from __future__ import annotations

from typing import Any, override

from django.core.management.base import BaseCommand
from django.urls import URLPattern, URLResolver, get_resolver


class Command(BaseCommand):
    """Prints all URL patterns and their namespace tag names."""

    help = "Prints all URL patterns and their namespace tag names."

    @override
    def handle(self, *args: Any, **options: Any) -> None:
        resolver = get_resolver()
        self._print_clean_urls(resolver.url_patterns)

    def _print_clean_urls(
        self,
        patterns: list[URLPattern | URLResolver],
        ns_prefix: str = "",
        path_prefix: str = "",
    ) -> None:
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                # If this resolver defines a namespace, update the tag prefix
                new_ns = (
                    f"{ns_prefix}{pattern.namespace}:"
                    if pattern.namespace
                    else ns_prefix
                )
                # Accumulate the actual URL path prefix
                new_path = f"{path_prefix}{pattern.pattern}"
                self._print_clean_urls(pattern.url_patterns, new_ns, new_path)

            elif isinstance(pattern, URLPattern):
                # Construct full namespace tag name
                tag_name = f"{ns_prefix}{pattern.name}" if pattern.name else "<unnamed>"

                # Clean up raw regex artifact symbols (^, $, \Z, etc.) for clean output
                raw_path = f"/{path_prefix}{pattern.pattern}"
                clean_path = (
                    raw_path.replace("^", "").replace("$", "").replace(r"\Z", "")
                )

                self.stdout.write(f"Tag Name: {tag_name:<50} -> Path: {clean_path}")
