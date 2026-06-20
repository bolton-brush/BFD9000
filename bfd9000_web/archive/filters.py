"""FilterSet definitions for the archive app.

Provides clean URL parameter aliases for complex ORM traversal filter paths,
so that API clients use short readable keys (e.g. ``subject``, ``encounter``)
instead of full ORM paths (e.g. ``series__imaging_study__encounter__subject``).
"""

from collections.abc import Sequence
from typing import final

import django_filters

from .models import DigitalRecord


@final
class DigitalRecordFilter(django_filters.FilterSet):  # type: ignore[misc]
    """FilterSet for DigitalRecord with clean URL parameter aliases.

    Supported query parameters:
      - ``subject``    : filter by Subject PK
            (maps to series__imaging_study__encounter__subject)
      - ``encounter``  : filter by Encounter PK
            (maps to series__imaging_study__encounter__id)
      - ``collection`` : filter by Collection PK
            (maps to series__imaging_study__encounter__subject__collection)
      - ``collection_short_name`` : filter by Collection short_name
      - ``series``     : filter by Series PK
      - ``record_type``: filter by record_type (Coding) PK
    """

    subject = django_filters.NumberFilter(
        field_name="series__imaging_study__encounter__subject",
        label="Subject PK",
    )
    encounter = django_filters.NumberFilter(
        field_name="series__imaging_study__encounter__id",
        label="Encounter PK",
    )
    collection = django_filters.NumberFilter(
        field_name="series__imaging_study__encounter__subject__collection",
        label="Collection PK",
    )
    collection_short_name = django_filters.CharFilter(
        field_name="series__imaging_study__encounter__subject__collection__short_name",
        label="Collection short name",
        lookup_expr="exact",
    )
    series = django_filters.NumberFilter(
        field_name="series",
        label="Series PK",
    )
    record_type = django_filters.NumberFilter(
        field_name="record_type__id",
        label="Record type (Coding) PK",
    )

    class Meta:
        """Meta information for DigitalRecordFilter"""

        model: type = DigitalRecord
        fields: Sequence[str] = (
            "subject",
            "encounter",
            "collection",
            "collection_short_name",
            "series",
            "record_type",
        )
