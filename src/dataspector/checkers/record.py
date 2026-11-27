"""Record-level integrity check functions operating on DataFrame chunks (alphabetical)."""

from __future__ import annotations

import pathlib
from collections.abc import Sequence
from typing import Any

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaError, SchemaErrors

from dataspector.checkers.utils import (
    CheckOutcome,
    check_series_between,
    missing_field_note,
    parse_date_bound,
    requires_all_data,
    resolve_pandera_schema,
    split_constraint,
    truncate_lines,
)


@requires_all_data
def record_all_data_not_null(
    data: pd.DataFrame,
    _last_chunk: bool = True,
) -> CheckOutcome:
    """Check that no cell anywhere in *data* is null/NaN.

    Parameters
    ----------
    data
        Chunk of records.
    _last_chunk
        ``True`` on the final chunk.

    Returns
    -------
    CheckOutcome
        ``False`` immediately on any null; ``None`` while streaming; ``True`` at end.
    """
    if bool(data.isnull().any().any()):
        bad_rows = truncate_lines(data.index[data.isnull().any(axis=1)].tolist())
        return CheckOutcome(passed=False, notes=f"Field at line(s) {bad_rows} is null.")
    return CheckOutcome(passed=True if _last_chunk else None)


def record_contains(data: pd.DataFrame, field: str) -> CheckOutcome:
    """Check that *data* contains column *field*.

    Parameters
    ----------
    data
        Chunk of records.
    field
        Expected column name.

    Returns
    -------
    CheckOutcome
        Outcome listing available columns on failure.
    """
    present = field in data
    notes = (
        f"Source has fields: {list(data.columns)}"
        if not present and hasattr(data, "columns")
        else None
    )
    return CheckOutcome(passed=present, notes=notes, kwargs={"field": field})


def record_contains_at_least(data: pd.DataFrame, fields: Sequence[str]) -> CheckOutcome:
    """Check that *data* contains every column listed in *fields*.

    Parameters
    ----------
    data
        Chunk of records.
    fields
        Required column names.

    Returns
    -------
    CheckOutcome
        Outcome listing missing columns on failure.
    """
    at_least = all(f in data for f in fields)
    notes = None if at_least else f"Source is missing: {sorted(set(fields) - set(data.columns))}"
    return CheckOutcome(passed=at_least, notes=notes, kwargs={"fields": list(fields)})


@requires_all_data
def record_count(
    data: pd.DataFrame,
    nrows: int,
    _previous: int = 0,
    _last_chunk: bool = True,
) -> CheckOutcome:
    """Check that the dataset has exactly *nrows* rows across all streamed chunks.

    Parameters
    ----------
    data
        Chunk of records.
    nrows
        Expected total row count.
    _previous
        Accumulated row count from prior chunks.
    _last_chunk
        ``True`` on the final chunk.

    Returns
    -------
    CheckOutcome
        ``passed=None`` while streaming; ``True``/``False`` on the final chunk.
    """
    nrecords = len(data) + _previous
    passed: bool | None = None
    notes: str | None = None
    if _last_chunk:
        passed = nrecords == nrows
        if not passed:
            notes = f"Found {nrecords} records"
    return CheckOutcome(passed=passed, notes=notes, kwargs={"nrows": nrows, "_previous": nrecords})


@requires_all_data
def record_count_greater_than(
    data: pd.DataFrame,
    nrows: int,
    _previous: int = 0,
    _last_chunk: bool = True,
) -> CheckOutcome:
    """Check that the dataset has strictly more than *nrows* rows.

    Parameters
    ----------
    data
        Chunk of records.
    nrows
        Exclusive minimum row count.
    _previous
        Accumulated row count from prior chunks.
    _last_chunk
        ``True`` on the final chunk.

    Returns
    -------
    CheckOutcome
        ``True`` as soon as *nrows* is exceeded; ``None`` while streaming; ``False`` at end.
    """
    nrecords = len(data) + _previous
    notes: str | None = None
    passed: bool | None
    if nrecords > nrows:
        passed = True
    elif _last_chunk:
        passed = False
        notes = f"Found {nrecords} records"
    else:
        passed = None
    return CheckOutcome(passed=passed, notes=notes, kwargs={"nrows": nrows, "_previous": nrecords})


@requires_all_data
def record_field_contains(
    data: pd.DataFrame,
    field: str,
    value: Any,
    _last_chunk: bool = True,
) -> CheckOutcome:
    """Check that column *field* contains *value* at least once across chunks.

    Parameters
    ----------
    data
        Chunk of records.
    field
        Target column name.
    value
        Value to search for.
    _last_chunk
        ``True`` on the final chunk.

    Returns
    -------
    CheckOutcome
        ``True`` as soon as *value* is seen; ``None`` while streaming; ``False`` if absent at end.
    """
    kwargs: dict[str, Any] = {"field": field, "value": value}
    if field not in data:
        return CheckOutcome(passed=False, notes=missing_field_note(field, data), kwargs=kwargs)

    if value in data[field].unique():
        return CheckOutcome(passed=True, kwargs=kwargs)
    if _last_chunk:
        return CheckOutcome(
            passed=False,
            notes=f"Value {value!r} not found in field {field!r}.",
            kwargs=kwargs,
        )
    return CheckOutcome(passed=None, kwargs=kwargs)


@requires_all_data
def record_field_contains_at_least(
    data: pd.DataFrame,
    field: str,
    values: Sequence[Any],
    _last_chunk: bool = True,
    _found: set[Any] | list[Any] | None = None,
) -> CheckOutcome:
    """Check that column *field* contains every value in *values* across the dataset.

    Parameters
    ----------
    data
        Chunk of records.
    field
        Target column name.
    values
        Required values.
    _last_chunk
        ``True`` on the final chunk.
    _found
        Accumulated unique values observed in prior chunks.

    Returns
    -------
    CheckOutcome
        ``True`` once all values are observed; ``None`` while streaming; ``False`` at end.
    """
    found_set = (
        _found if isinstance(_found, set) else (set(_found) if _found is not None else set())
    )
    passed: bool | None = None
    notes: str | None = None

    if field not in data:
        passed = False
        notes = missing_field_note(field, data)
    else:
        found_set.update(data[field].dropna().unique().tolist())
        all_found = all(val in found_set for val in values)
        if _last_chunk or all_found:
            passed = all_found
            if not all_found and len(found_set) < 10:
                notes = f"Found the following unique values: {sorted(found_set, key=str)}"

    return CheckOutcome(
        passed=passed,
        notes=notes,
        kwargs={"field": field, "values": list(values), "_found": found_set},
    )


@requires_all_data
def record_field_contains_only(
    data: pd.DataFrame,
    field: str,
    values: Sequence[Any],
    _last_chunk: bool = True,
    _found: set[Any] | list[Any] | None = None,
) -> CheckOutcome:
    """Check that column *field* contains no values outside *values*.

    Parameters
    ----------
    data
        Chunk of records.
    field
        Target column name.
    values
        Permitted values.
    _last_chunk
        ``True`` on the final chunk.
    _found
        Accumulated unique values observed in prior chunks.

    Returns
    -------
    CheckOutcome
        ``False`` immediately on unexpected values; ``None`` while streaming; ``True`` at end.
    """
    found_set = (
        _found if isinstance(_found, set) else (set(_found) if _found is not None else set())
    )
    allowed = set(values)
    passed: bool | None = None
    notes: str | None = None

    if field not in data:
        passed = False
        notes = missing_field_note(field, data)
    else:
        found_set.update(data[field].unique().tolist())
        extra_vals = [v for v in found_set if v not in allowed]
        if extra_vals:
            passed = False
            bad_lines = data.index[data[field].isin(extra_vals)].tolist()
            notes = (
                f"Found the following extra values: {extra_vals} "
                f"at line(s) {truncate_lines(bad_lines)}"
            )
        elif _last_chunk:
            passed = True

    return CheckOutcome(
        passed=passed,
        notes=notes,
        kwargs={"field": field, "values": list(values), "_found": found_set},
    )


@requires_all_data
def record_field_date_between(
    data: pd.DataFrame,
    field: str,
    constraint: str | Sequence[Any],
    include_bounds: bool = False,
    _last_chunk: bool = True,
) -> CheckOutcome:
    """Check that all date values in *field* lie within *constraint*.

    Parameters
    ----------
    data
        Chunk of records.
    field
        Target column name.
    constraint
        Lower and upper date bounds as a 2-sequence or bracketed string
        (e.g. ``'[January 2015, 2018-01-01]'`` or ``(2015, 2018)``).
    include_bounds
        Use inclusive bounds when ``True``, strict otherwise.
    _last_chunk
        ``True`` on the final chunk.

    Returns
    -------
    CheckOutcome
        ``False`` immediately on out-of-range dates; ``None`` while streaming; ``True`` at end.
    """
    try:
        raw_lo, raw_hi = split_constraint(constraint)
        bounds = (parse_date_bound(raw_lo), parse_date_bound(raw_hi))
    except (ValueError, TypeError):
        return CheckOutcome(
            passed=False,
            notes=f"Cannot convert {constraint} to dates. Stopping this check.",
            kwargs={"field": field, "constraint": constraint, "include_bounds": include_bounds},
        )

    kwargs: dict[str, Any] = {
        "field": field,
        "constraint": bounds,
        "include_bounds": include_bounds,
    }
    if field not in data:
        return CheckOutcome(
            passed=False,
            notes=f"{field} not found in {list(data.columns)}. Stopping this check.",
            kwargs=kwargs,
        )

    if data.empty:
        return CheckOutcome(passed=True if _last_chunk else None, kwargs=kwargs)

    try:
        date_series = pd.to_datetime(data[field], format="mixed")
    except (ValueError, TypeError):
        return CheckOutcome(
            passed=False,
            notes=f"Cannot convert {field} to dates. Stopping this check.",
            kwargs=kwargs,
        )

    passed, notes = check_series_between(
        date_series,
        bounds[0],
        bounds[1],
        include_bounds=include_bounds,
        last_chunk=_last_chunk,
    )
    return CheckOutcome(passed=passed, notes=notes, kwargs=kwargs)


def record_field_is_numeric(data: pd.DataFrame, field: str) -> CheckOutcome:
    """Check that column *field* has a numeric pandas dtype.

    Parameters
    ----------
    data
        Chunk of records.
    field
        Target column name.

    Returns
    -------
    CheckOutcome
        Outcome detailing actual dtype on failure.
    """
    kwargs: dict[str, Any] = {"field": field}
    if field not in data:
        return CheckOutcome(passed=False, notes=missing_field_note(field, data), kwargs=kwargs)

    is_num = bool(pd.api.types.is_numeric_dtype(data[field]))
    notes = None if is_num else f"{field} data type: {data[field].dtype}"
    return CheckOutcome(passed=is_num, notes=notes, kwargs=kwargs)


@requires_all_data
def record_field_is_unique(
    data: pd.DataFrame,
    field: str,
    _last_chunk: bool = True,
    _found: set[Any] | list[Any] | None = None,
) -> CheckOutcome:
    """Check that every value in *field* is unique across all chunks.

    Parameters
    ----------
    data
        Chunk of records.
    field
        Target column name.
    _last_chunk
        ``True`` on the final chunk.
    _found
        Accumulated values observed in prior chunks.

    Returns
    -------
    CheckOutcome
        ``False`` immediately on duplicate values; ``None`` while streaming; ``True`` at end.
    """
    seen = _found if isinstance(_found, set) else (set(_found) if _found is not None else set())
    passed: bool | None = None
    notes: str | None = None

    if field not in data:
        passed = False
        notes = missing_field_note(field, data)
    else:
        col = data[field]
        dups_within = set(col[col.duplicated()].tolist())
        dups_across = set(col[col.isin(seen)].tolist())
        dups = sorted(dups_within | dups_across, key=str)
        seen.update(col.tolist())

        if dups:
            passed = False
            bad_lines = data.index[col.isin(dups)].tolist()
            notes = (
                f"Found the following duplicate values: {dups} "
                f"at line(s) {truncate_lines(bad_lines)}"
            )
        elif _last_chunk:
            passed = True

    return CheckOutcome(passed=passed, notes=notes, kwargs={"field": field, "_found": seen})


@requires_all_data
def record_field_not_null(
    data: pd.DataFrame,
    field: str,
    _last_chunk: bool = True,
) -> CheckOutcome:
    """Check that column *field* contains no null/NaN values.

    Parameters
    ----------
    data
        Chunk of records.
    field
        Target column name.
    _last_chunk
        ``True`` on the final chunk.

    Returns
    -------
    CheckOutcome
        ``False`` immediately on any null; ``None`` while streaming; ``True`` at end.
    """
    kwargs: dict[str, Any] = {"field": field}
    if field not in data:
        return CheckOutcome(passed=False, notes=missing_field_note(field, data), kwargs=kwargs)

    null_mask = data[field].isnull()
    if bool(null_mask.any()):
        lines = truncate_lines(data.index[null_mask].tolist())
        return CheckOutcome(passed=False, notes=f"Field at line(s) {lines} is null.", kwargs=kwargs)
    return CheckOutcome(passed=True if _last_chunk else None, kwargs=kwargs)


@requires_all_data
def record_field_numeric_value_between(
    data: pd.DataFrame,
    field: str,
    constraint: str | Sequence[float | int | str],
    include_bounds: bool = False,
    _last_chunk: bool = True,
) -> CheckOutcome:
    """Check that all numeric values in *field* lie within *constraint*.

    Parameters
    ----------
    data
        Chunk of records.
    field
        Target column name.
    constraint
        Lower and upper bounds as a 2-sequence or string (e.g. ``'(0.1, 100)'``).
    include_bounds
        Use inclusive ``<=``/``>=`` bounds when ``True``, strict otherwise.
    _last_chunk
        ``True`` on the final chunk.

    Returns
    -------
    CheckOutcome
        ``False`` immediately on out-of-range values; ``None`` while streaming; ``True`` at end.
    """
    try:
        raw_lo, raw_hi = split_constraint(constraint)
        bounds = (float(raw_lo), float(raw_hi))
    except (ValueError, TypeError):
        return CheckOutcome(
            passed=False,
            notes=f"Cannot convert {constraint} to numeric bounds. Stopping this check.",
            kwargs={"field": field, "constraint": constraint, "include_bounds": include_bounds},
        )

    kwargs: dict[str, Any] = {
        "field": field,
        "constraint": bounds,
        "include_bounds": include_bounds,
    }
    if field not in data:
        return CheckOutcome(
            passed=False,
            notes=f"{field} not found in {list(data.columns)}. Stopping this check.",
            kwargs=kwargs,
        )

    passed, notes = check_series_between(
        data[field],
        bounds[0],
        bounds[1],
        include_bounds=include_bounds,
        last_chunk=_last_chunk,
    )
    return CheckOutcome(passed=passed, notes=notes, kwargs=kwargs)


@requires_all_data
def record_if_field1_startswith_field2_contains_only(
    data: pd.DataFrame,
    field1: str,
    value1: str,
    field2: str,
    value2: Any,
    _last_chunk: bool = True,
) -> CheckOutcome:
    """Check conditional dependency: if *field1* starts with *value1*, *field2* equals *value2*.

    Parameters
    ----------
    data
        Chunk of records.
    field1
        Condition column name.
    value1
        Required prefix on *field1*.
    field2
        Dependent column name.
    value2
        Required value for *field2* whenever *field1* matches *value1*.
    _last_chunk
        ``True`` on the final chunk.

    Returns
    -------
    CheckOutcome
        ``False`` immediately on violations; ``None`` while streaming; ``True`` at end.
    """
    kwargs: dict[str, Any] = {
        "field1": field1,
        "value1": value1,
        "field2": field2,
        "value2": value2,
    }
    if field1 not in data or field2 not in data:
        return CheckOutcome(
            passed=False,
            notes=f"Fields {field1} or {field2} not available in {list(data.columns)}",
            kwargs=kwargs,
        )

    if data.empty:
        return CheckOutcome(passed=True if _last_chunk else None, kwargs=kwargs)

    matches_prefix = data[field1].astype(str).str.startswith(str(value1))
    mismatches = matches_prefix & (data[field2] != value2)
    if bool(mismatches.any()):
        extra_vals = data.loc[mismatches, field2].unique().tolist()
        bad_lines = data.index[mismatches].tolist()
        note = (
            f"Found the following extra values: {extra_vals} at line(s) {truncate_lines(bad_lines)}"
        )
        return CheckOutcome(passed=False, notes=note, kwargs=kwargs)

    return CheckOutcome(passed=True if _last_chunk else None, kwargs=kwargs)


@requires_all_data
def record_validate_schema(
    data: pd.DataFrame,
    schema: pa.DataFrameSchema | dict[str, Any] | str | pathlib.Path,
    lazy: bool = True,
    _last_chunk: bool = True,
) -> CheckOutcome:
    """Validate each chunk of *data* against a Pandera :class:`DataFrameSchema`.

    Accepts a :class:`pandera.pandas.DataFrameSchema` object, a concise dict
    specification, a YAML/JSON schema file path, or a COBOL copybook path
    (auto-converted via :meth:`~dataspector.coboller.copybook.Copybook.to_pandera_schema`).

    Parameters
    ----------
    data
        Chunk of records to validate.
    schema
        Declarative Pandera schema definition or path.
    lazy
        Collect all schema violations per chunk before failing.
    _last_chunk
        ``True`` on the final chunk.

    Returns
    -------
    CheckOutcome
        Outcome with concise violation summary in ``notes`` on failure.
    """
    try:
        resolved = resolve_pandera_schema(schema)
    except Exception as exc:
        return CheckOutcome(
            passed=False,
            notes=f"Invalid Pandera schema: {exc}",
            kwargs={"schema": schema, "lazy": lazy},
        )

    kwargs: dict[str, Any] = {"schema": resolved, "lazy": lazy}
    if data.empty:
        return CheckOutcome(passed=True if _last_chunk else None, kwargs=kwargs)

    try:
        resolved.validate(data, lazy=lazy)
    except SchemaErrors as exc:
        cases = exc.failure_cases
        summary = "; ".join(
            f"{row.get('column', '<df>')}: {row.get('check', 'failed')} (case={row.get('failure_case')})"
            for _, row in cases.head(5).iterrows()
        )
        if len(cases) > 5:
            summary += f"; ... ({len(cases)} total failures)"
        return CheckOutcome(passed=False, notes=summary, kwargs=kwargs)
    except SchemaError as exc:
        return CheckOutcome(passed=False, notes=str(exc), kwargs=kwargs)

    return CheckOutcome(passed=True if _last_chunk else None, kwargs=kwargs)
