"""Shared types, decorators, and internal helpers for :mod:`dataspector.checkers`."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

import pandas as pd
import pandera.pandas as pa

if TYPE_CHECKING:
    from dataspector.core import GenericData

_F = TypeVar("_F", bound=Callable[..., Any])

REQUIRES_ALL_DATA: set[str] = set()


@dataclass(slots=True)
class CheckOutcome:
    """Structured result returned by every check function in :mod:`dataspector.checkers`.

    Attributes
    ----------
    passed
        ``True`` if the check passed, ``False`` if it failed, or ``None`` if
        more chunks must be streamed before deciding.
    notes
        Optional human-readable diagnostic details (e.g. failing row indices).
    kwargs
        Keyword arguments (including updated accumulator state) forwarded to
        subsequent chunk invocations or recorded in reports.
    """

    passed: bool | None
    notes: str | None = None
    kwargs: dict[str, Any] = field(default_factory=dict)


def requires_all_data(func: _F) -> _F:
    """Mark a check function as requiring the full streamed dataset before finalizing.

    Decorated checks accept a ``_last_chunk: bool = True`` parameter. While
    streaming chunks with ``_last_chunk=False``, the check may return
    ``CheckOutcome(passed=None, kwargs=...)`` to instruct
    :class:`~dataspector.core.CheckeredHistory` to keep streaming and pass the
    updated ``kwargs`` into the next chunk. On the final flush
    (``_last_chunk=True``), the check must emit a definite ``True`` or ``False``.

    Parameters
    ----------
    func
        Check function to register in ``REQUIRES_ALL_DATA``.

    Returns
    -------
    Callable
        The original check function, unmodified.
    """
    name = getattr(func, "__name__", None)
    if isinstance(name, str):
        REQUIRES_ALL_DATA.add(name)
    return func


def as_generic_data(source: Any) -> GenericData:
    """Coerce a path, tuple, or :class:`~dataspector.core.GenericData` into :class:`~dataspector.core.GenericData`.

    Parameters
    ----------
    source
        File path, locator tuple, or existing :class:`~dataspector.core.GenericData` wrapper.

    Returns
    -------
    GenericData
        Wrapped data source.
    """
    from dataspector.core import GenericData

    return source if isinstance(source, GenericData) else GenericData(source)


def build_pandera_checks(spec: dict[str, Any] | list[pa.Check] | None) -> list[pa.Check]:
    """Convert a simple dict of check constraints into :class:`pandera.Check` objects.

    Parameters
    ----------
    spec
        Mapping of constraint names (e.g. ``gt``, ``in_range``, ``isin``) to
        arguments, an existing list of :class:`pandera.Check`, or ``None``.

    Returns
    -------
    list[pandera.Check]
        Constructed Pandera check instances.
    """
    if spec is None:
        return []
    if isinstance(spec, list):
        return spec

    builders: dict[str, Callable[[Any], pa.Check]] = {
        "gt": pa.Check.greater_than,
        "ge": pa.Check.greater_than_or_equal_to,
        "lt": pa.Check.less_than,
        "le": pa.Check.less_than_or_equal_to,
        "isin": pa.Check.isin,
        "notin": pa.Check.notin,
        "str_matches": pa.Check.str_matches,
        "str_startswith": pa.Check.str_startswith,
        "str_endswith": pa.Check.str_endswith,
        "str_contains": pa.Check.str_contains,
    }
    checks: list[pa.Check] = []
    for name, arg in spec.items():
        if name == "in_range" and isinstance(arg, (list, tuple)) and len(arg) == 2:
            checks.append(pa.Check.in_range(min_value=arg[0], max_value=arg[1]))
        elif name == "str_length" and isinstance(arg, (list, tuple)) and len(arg) == 2:
            checks.append(pa.Check.str_length(min_value=arg[0], max_value=arg[1]))
        elif name in builders:
            checks.append(builders[name](arg))
        else:
            raise ValueError(f"Unsupported Pandera check key: {name!r}")
    return checks


def check_series_between(
    series: pd.Series,
    lower: Any,
    upper: Any,
    include_bounds: bool = False,
    last_chunk: bool = True,
) -> tuple[bool | None, str | None]:
    """Evaluate range bounds on a numeric or datetime :class:`pandas.Series`.

    Parameters
    ----------
    series
        Values to test against the interval bounds.
    lower
        Lower bound.
    upper
        Upper bound.
    include_bounds
        Treat *lower* and *upper* as inclusive when ``True`` (exclusive when ``False``).
    last_chunk
        Whether this is the final chunk in a streaming check.

    Returns
    -------
    tuple[bool | None, str | None]
        Pair of ``(passed, diagnostic_note)``; ``passed`` is ``None`` while
        more chunks remain and no violation has occurred.
    """
    if series.empty:
        return (True, None) if last_chunk else (None, None)

    if include_bounds:
        outside = (series < lower) | (series > upper)
    else:
        outside = (series <= lower) | (series >= upper)

    if bool(outside.any()):
        minv = series.min()
        maxv = series.max()
        below = minv < lower if include_bounds else minv <= lower
        above = maxv > upper if include_bounds else maxv >= upper
        if below and above:
            note = (
                f"Found (min, max) values: ({minv}, {maxv}) "
                f"at lines ({series.idxmin()}, {series.idxmax()})"
            )
        elif below:
            note = f"Found value of {minv}, below constraint {lower} at line {series.idxmin()}"
        else:
            note = f"Found value of {maxv}, above constraint {upper} at line {series.idxmax()}"
        return False, note

    return (True, None) if last_chunk else (None, None)


def missing_field_note(field_name: str, data: pd.DataFrame) -> str:
    """Format a consistent diagnostic note when a required column is absent.

    Parameters
    ----------
    field_name
        Name of the missing column.
    data
        DataFrame whose columns were inspected.

    Returns
    -------
    str
        Human-readable diagnostic message listing available columns.
    """
    return f"Field {field_name} not available in {list(data.columns)}"


def parse_date_bound(value: Any) -> pd.Timestamp:
    """Convert a string, year integer, or datetime-like bound to :class:`pd.Timestamp`.

    Parameters
    ----------
    value
        Date string, integer year, or datetime-like object.

    Returns
    -------
    pandas.Timestamp
        Parsed timestamp bound.
    """
    if isinstance(value, pd.Timestamp):
        return value
    if isinstance(value, int):
        return pd.to_datetime(str(value))
    return pd.to_datetime(value)


def resolve_pandera_schema(
    schema: pa.DataFrameSchema | dict[str, Any] | str | pathlib.Path,
) -> pa.DataFrameSchema:
    """Resolve a Pandera schema from an object, dict, YAML/JSON file, or COBOL copybook.

    Parameters
    ----------
    schema
        Existing :class:`pandera.pandas.DataFrameSchema`, column-spec dictionary,
        JSON string, or path to a ``.json``, ``.yaml``/``.yml``, or COBOL copybook file.

    Returns
    -------
    pandera.pandas.DataFrameSchema
        Resolved Pandera DataFrame schema.
    """
    if isinstance(schema, pa.DataFrameSchema):
        return schema

    if isinstance(schema, dict):
        columns: dict[str, pa.Column] = {}
        for col_name, spec in schema.items():
            if isinstance(spec, pa.Column):
                columns[col_name] = spec
            elif isinstance(spec, dict):
                col_checks = build_pandera_checks(spec.get("checks"))
                columns[col_name] = pa.Column(
                    dtype=spec.get("dtype"),
                    nullable=bool(spec.get("nullable", False)),
                    unique=bool(spec.get("unique", False)),
                    coerce=bool(spec.get("coerce", False)),
                    checks=col_checks,
                )
            else:
                columns[col_name] = pa.Column(dtype=spec)
        return pa.DataFrameSchema(columns=columns)

    path = pathlib.Path(schema)
    suffix = path.suffix.lower()
    if suffix in (".cbl", ".cpy", ".cob"):
        from dataspector.coboller import Copybook

        return Copybook(path).to_pandera_schema()
    if suffix == ".json":
        return pa.DataFrameSchema.from_json(path)
    if suffix in (".yml", ".yaml"):
        return pa.DataFrameSchema.from_yaml(path)

    parsed = json.loads(str(schema))
    return resolve_pandera_schema(parsed)


def source_byte_size(source: GenericData) -> int:
    """Return file byte size for a file-backed or COBOL :class:`~dataspector.core.GenericData`.

    Parameters
    ----------
    source
        Data source wrapper backed by a local file or COBOL data file.

    Returns
    -------
    int
        Size of the underlying data file in bytes.
    """
    from dataspector.coboller import Copybook

    if isinstance(source.path, Copybook):
        if isinstance(source.engine, pathlib.Path):
            return source.engine.stat().st_size
        raise ValueError("COBOL size check requires an underlying data file path.")
    if source.path is not None and source.path.exists():
        return source.path.stat().st_size
    raise FileNotFoundError(f"Cannot determine byte size for source {source!r}.")


def split_constraint(constraint: str | Sequence[Any]) -> tuple[Any, Any]:
    """Split a string like ``'(0, 10)'`` / ``'[2020-01-01, 2021-01-01]'`` or 2-sequence.

    Parameters
    ----------
    constraint
        Two-element sequence or bracketed comma-separated string.

    Returns
    -------
    tuple[Any, Any]
        ``(lower, upper)`` raw bound values.
    """
    if isinstance(constraint, str):
        cleaned = constraint.strip().strip("()[]")
        parts = [p.strip() for p in cleaned.split(",")]
        if len(parts) != 2:
            raise ValueError(f"Expected 2 bounds in constraint {constraint!r}.")
        return parts[0], parts[1]
    if len(constraint) != 2:
        raise ValueError(f"Expected 2 bounds in constraint {constraint!r}.")
    return constraint[0], constraint[1]


def truncate_lines(indices: Sequence[Any], limit: int = 10) -> list[Any]:
    """Return up to *limit* row indices with an overflow marker if truncated.

    Parameters
    ----------
    indices
        Sequence of failing row indices.
    limit
        Maximum number of indices to retain before appending ``"and more"``.

    Returns
    -------
    list[Any]
        List of row indices, optionally followed by ``"and more"``.
    """
    items = list(indices)
    if len(items) > limit:
        return [*items[:limit], "and more"]
    return items
