"""Source-level and cross-source integrity check functions (alphabetical)."""

from __future__ import annotations

import filecmp
import pathlib
from collections.abc import Sized
from typing import TYPE_CHECKING, Any

import pandas as pd

from dataspector.checkers.utils import (
    CheckOutcome,
    as_generic_data,
    requires_all_data,
    source_byte_size,
)

if TYPE_CHECKING:
    from dataspector.core import GenericData


def source_exists(source: GenericData) -> CheckOutcome:
    """Check whether *source* exists.

    Parameters
    ----------
    source
        Data source wrapper.

    Returns
    -------
    CheckOutcome
        ``passed=True`` if *source* exists, else ``False``.
    """
    return CheckOutcome(passed=source.exists)


def source_fuzzy_find(source: GenericData, pattern: str) -> CheckOutcome:
    """Search *source* for files, sheets, or tables matching shell *pattern*.

    Parameters
    ----------
    source
        Directory, workbook, or database source.
    pattern
        Shell-style wildcard pattern (``*``, ``?``).

    Returns
    -------
    CheckOutcome
        Outcome listing matching entries in ``notes``.
    """
    matches = source.fuzzy_find(pattern)
    if matches is None:
        passed, notes = False, "Pattern search not applicable."
    elif matches:
        passed, notes = True, f"Found: {matches}"
    else:
        passed, notes = False, "No matches found."
    return CheckOutcome(passed=passed, notes=notes, kwargs={"pattern": pattern})


def source_has_N_fields(source: GenericData, n_fields: int) -> CheckOutcome:
    """Check that *source* has exactly *n_fields* columns.

    Parameters
    ----------
    source
        Data source wrapper.
    n_fields
        Expected column count.

    Returns
    -------
    CheckOutcome
        Outcome with actual field count in ``notes`` on mismatch.
    """
    cols = source.columns
    n = len(cols) if cols is not None else 0
    has_n = n == n_fields
    notes = None if has_n else f"Source has {n} fields"
    return CheckOutcome(passed=has_n, notes=notes, kwargs={"n_fields": n_fields})


def source_modified_on_date(
    source: GenericData,
    date: Any,
    tolerance: str = "12h",
) -> CheckOutcome:
    """Check that *source* was last modified within *tolerance* of *date*.

    Parameters
    ----------
    source
        Data source wrapper.
    date
        Expected modification timestamp.
    tolerance
        Pandas Timedelta string (e.g. ``'1d'``, ``'2.5h'``).

    Returns
    -------
    CheckOutcome
        Outcome with source modification timestamp in ``notes``.
    """
    kwargs: dict[str, Any] = {"date": date, "tolerance": tolerance}
    try:
        target = pd.to_datetime(date)
    except (ValueError, TypeError):
        return CheckOutcome(
            passed=False,
            notes=f"Cannot convert {date} to dates. Stopping this check.",
            kwargs=kwargs,
        )

    try:
        delta = pd.Timedelta(tolerance)
    except (ValueError, TypeError):
        return CheckOutcome(
            passed=False,
            notes=f"Cannot convert {tolerance} to time difference. Stopping this check.",
            kwargs=kwargs,
        )

    modded_on = source.last_modified
    if modded_on is None:
        return CheckOutcome(
            passed=False,
            notes="Could not determine source last_modified timestamp.",
            kwargs=kwargs,
        )

    mod_ts = pd.Timestamp(modded_on)
    if mod_ts.tzinfo is not None and target.tzinfo is None:
        target = target.tz_localize(mod_ts.tzinfo)
    elif mod_ts.tzinfo is None and target.tzinfo is not None:
        mod_ts = mod_ts.tz_localize(target.tzinfo)

    passed = bool(abs(mod_ts - target) < delta)
    return CheckOutcome(passed=passed, notes=f"Source modified on {modded_on}", kwargs=kwargs)


def source_modified_recently(source: GenericData, days_ago: float = 1) -> CheckOutcome:
    """Check that *source* was modified within the last *days_ago* days.

    Parameters
    ----------
    source
        Data source wrapper.
    days_ago
        Maximum allowed age in days.

    Returns
    -------
    CheckOutcome
        Outcome with last modification timestamp in ``notes`` when stale.
    """
    kwargs: dict[str, Any] = {"days_ago": days_ago}
    recent = source.is_modified_recently(days_ago)
    notes = f"Source modified on {source.last_modified}" if recent is False else None
    return CheckOutcome(passed=recent, notes=notes, kwargs=kwargs)


def source_source_identical(
    source: GenericData,
    source2: Any,
    shallow: bool = False,
) -> CheckOutcome:
    """Check whether *source* and *source2* are identical files on disk.

    Parameters
    ----------
    source
        Primary file-backed data source.
    source2
        Comparison file-backed data source.
    shallow
        Compare only file metadata when ``True``; byte-by-byte when ``False``.

    Returns
    -------
    CheckOutcome
        Outcome indicating file identity.
    """
    kwargs: dict[str, Any] = {"source2": source2, "shallow": shallow}
    f1 = source.path
    f2 = as_generic_data(source2).path
    if not isinstance(f1, pathlib.Path) or not isinstance(f2, pathlib.Path):
        return CheckOutcome(
            passed=False,
            notes="Both sources must be file paths for byte-level comparison.",
            kwargs=kwargs,
        )
    return CheckOutcome(passed=filecmp.cmp(f1, f2, shallow=shallow), kwargs=kwargs)


@requires_all_data
def source_source_roughly_same_number_of_records(
    data: Sized,
    source2: Any,
    tolerance: float = 0.0,
    _last_chunk: bool = True,
    _nrecords: int = 0,
) -> CheckOutcome:
    """Check that the streamed source has roughly the same row count as *source2*.

    Passes when ``abs(n1 - n2) <= tolerance * n2`` (or both have zero records).
    Because this check is decorated with :func:`~dataspector.checkers.utils.requires_all_data`,
    it accumulates ``_nrecords`` and returns ``passed=None`` on intermediate chunks
    (``_last_chunk=False``) so the runner keeps streaming until the final chunk.

    Parameters
    ----------
    data
        Chunk of records from the primary source (any sized sequence/DataFrame).
    source2
        Reference data source to compare against.
    tolerance
        Relative difference threshold (default ``0.0`` requires exact equality).
    _last_chunk
        ``True`` on the final chunk, triggering the comparison against *source2*.
    _nrecords
        Accumulated record count carried across chunks.

    Returns
    -------
    CheckOutcome
        ``passed=None`` while streaming; ``True`` or ``False`` on the final chunk.
    """
    passed: bool | None = None
    notes: str | None = None
    _nrecords += len(data)

    if _last_chunk:
        n2 = as_generic_data(source2).number_of_records
        if _nrecords == 0 and n2 == 0:
            passed = True
            notes = "Number of records is zero."
        elif n2 > 0 and abs(_nrecords - n2) <= tolerance * n2:
            passed = True
        else:
            passed = False
            notes = f"Number of records in (source, source2): ({_nrecords}, {n2})"

    return CheckOutcome(
        passed=passed,
        notes=notes,
        kwargs={"source2": source2, "tolerance": tolerance, "_nrecords": _nrecords},
    )


def source_source_same_fields(source: GenericData, source2: Any) -> CheckOutcome:
    """Check that *source* and *source2* expose the same set of fields.

    Parameters
    ----------
    source
        Primary data source.
    source2
        Comparison data source.

    Returns
    -------
    CheckOutcome
        Outcome detailing missing/extra columns in ``notes`` on mismatch.
    """
    f1 = list(source.columns or [])
    f2 = list(as_generic_data(source2).columns or [])
    same = set(f1) == set(f2)
    notes: str | None = None
    if not same:
        missing = sorted(set(f1) - set(f2))
        extra = sorted(set(f2) - set(f1))
        parts: list[str] = []
        if missing:
            parts.append(f"Missing in source2: {missing}")
        if extra:
            parts.append(f"Extra in source2: {extra}")
        notes = "; ".join(parts)
    return CheckOutcome(passed=same, notes=notes, kwargs={"source2": source2})


def source_source_size_roughly_same(
    source: GenericData,
    source2: Any,
    tolerance: float = 0.2,
) -> CheckOutcome:
    """Check that *source* and *source2* byte sizes are within *tolerance*.

    Parameters
    ----------
    source
        Primary data source.
    source2
        Comparison data source.
    tolerance
        Maximum allowed relative difference ``abs(size1 - size2) / size1``.

    Returns
    -------
    CheckOutcome
        Outcome detailing relative size ratio in ``notes`` on failure.
    """
    size1 = source_byte_size(source)
    size2 = source_byte_size(as_generic_data(source2))

    if size1 == 0:
        passed = size2 == 0
        note = None if passed else f"Source is empty (0 bytes) while source2 is {size2} bytes"
    else:
        passed = abs(size1 - size2) / size1 <= tolerance
        note = None if passed else f"Source2 is {size2 / size1} times the size of source"

    return CheckOutcome(
        passed=passed,
        notes=note,
        kwargs={"source2": source2, "tolerance": tolerance},
    )


def source_storage_size_roughly(
    source: GenericData,
    rough_size: int,
    tolerance: float = 0.2,
) -> CheckOutcome:
    """Check that *source* byte size is within *tolerance* of *rough_size*.

    Parameters
    ----------
    source
        Data source wrapper.
    rough_size
        Expected size in bytes.
    tolerance
        Maximum allowed relative difference.

    Returns
    -------
    CheckOutcome
        Outcome indicating whether the byte size is within tolerance.
    """
    kwargs: dict[str, Any] = {"rough_size": rough_size, "tolerance": tolerance}
    return CheckOutcome(passed=source.storage_size_roughly(**kwargs), kwargs=kwargs)
