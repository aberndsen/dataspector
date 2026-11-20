"""Format-agnostic data-integrity checkers.

Public facade re-exporting:

* **Source-level checks** (``source_*``) from :mod:`dataspector.checkers.source`
* **Record-level checks** (``record_*``) from :mod:`dataspector.checkers.record`
* :class:`~dataspector.checkers.utils.CheckOutcome`,
  :func:`~dataspector.checkers.utils.requires_all_data`, and
  ``REQUIRES_ALL_DATA`` from :mod:`dataspector.checkers.utils`

Every check returns a :class:`~dataspector.checkers.utils.CheckOutcome` whose
``passed`` attribute is:

* ``True`` — check passed;
* ``False`` — check failed;
* ``None`` — indeterminate so far; keep streaming subsequent chunks.
"""

from __future__ import annotations

from dataspector.checkers.record import (
    record_all_data_not_null,
    record_contains,
    record_contains_at_least,
    record_count,
    record_count_greater_than,
    record_field_contains,
    record_field_contains_at_least,
    record_field_contains_only,
    record_field_date_between,
    record_field_is_numeric,
    record_field_is_unique,
    record_field_not_null,
    record_field_numeric_value_between,
    record_if_field1_startswith_field2_contains_only,
    record_validate_schema,
)
from dataspector.checkers.source import (
    source_exists,
    source_fuzzy_find,
    source_has_N_fields,
    source_modified_on_date,
    source_modified_recently,
    source_source_identical,
    source_source_roughly_same_number_of_records,
    source_source_same_fields,
    source_source_size_roughly_same,
    source_storage_size_roughly,
)
from dataspector.checkers.utils import (
    REQUIRES_ALL_DATA,
    CheckOutcome,
    requires_all_data,
)

__all__ = [
    "REQUIRES_ALL_DATA",
    "CheckOutcome",
    "record_all_data_not_null",
    "record_contains",
    "record_contains_at_least",
    "record_count",
    "record_count_greater_than",
    "record_field_contains",
    "record_field_contains_at_least",
    "record_field_contains_only",
    "record_field_date_between",
    "record_field_is_numeric",
    "record_field_is_unique",
    "record_field_not_null",
    "record_field_numeric_value_between",
    "record_if_field1_startswith_field2_contains_only",
    "record_validate_schema",
    "requires_all_data",
    "source_exists",
    "source_fuzzy_find",
    "source_has_N_fields",
    "source_modified_on_date",
    "source_modified_recently",
    "source_source_identical",
    "source_source_roughly_same_number_of_records",
    "source_source_same_fields",
    "source_source_size_roughly_same",
    "source_storage_size_roughly",
]
