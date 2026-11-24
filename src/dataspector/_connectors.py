"""Path normalization, unified URI/scheme locators, and database connection helpers."""

from __future__ import annotations

import ast
import dataclasses
import importlib
import os
import pathlib
import re
import urllib.parse
from collections.abc import Mapping
from typing import Any

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Engine

from dataspector import coboller

pyodbc: Any
try:
    pyodbc = importlib.import_module("pyodbc")
except ImportError:  # pragma: no cover - optional dependency
    logger.trace("Optional dependency 'pyodbc' is not installed; ODBC sources are unavailable.")
    pyodbc = None

_JET_CONNECTIONS: tuple[str, ...] = (
    "DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s",
    "DRIVER={Microsoft Access Driver (*.mdb)};DBQ=%s",
)

_ENV_VAR_PATTERN = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}")

_FILE_SCHEMES: dict[str, str] = {
    "file": "",
    "csv": ".csv",
    "tsv": ".tsv",
    "txt": ".txt",
    "fwf": "fwf",
    "fixed": "fwf",
    "excel": ".xlsx",
    "xlsx": ".xlsx",
    "xls": ".xls",
    "parquet": ".parquet",
    "pq": ".parquet",
    "json": ".json",
    "jsonl": ".jsonl",
    "ndjson": ".jsonl",
    "hdf": ".h5",
    "hdf5": ".h5",
    "h5": ".h5",
}

_COBOL_SCHEMES: frozenset[str] = frozenset({"cobol", "cbl", "cpy", "copybook"})
_ACCESS_SCHEMES: frozenset[str] = frozenset({"access", "msaccess", "mdb", "accdb"})
_SQLALCHEMY_PREFIXES: frozenset[str] = frozenset(
    {
        "sqlite",
        "sqlite3",
        "postgres",
        "postgresql",
        "mysql",
        "mariadb",
        "mssql",
        "sqlserver",
        "oracle",
        "duckdb",
        "snowflake",
        "bigquery",
        "redshift",
        "trino",
        "clickhouse",
    }
)


@dataclasses.dataclass(slots=True)
class DataSourceSpec:
    """Explicit, unified specification for a single file, COBOL pair, or database table.

    Parameters
    ----------
    uri
        Filesystem path, COBOL copybook path, or database connection URL.
    format
        Optional explicit format or database flavour (e.g. ``"csv"``, ``"tsv"``,
        ``"fwf"``, ``"excel"``, ``"parquet"``, ``"json"``, ``"jsonl"``, ``"hdf5"``,
        ``"cobol"``, ``"sqlite"``, ``"postgres"``, ``"mysql"``, ``"mariadb"``,
        ``"mssql"``, ``"oracle"``, ``"duckdb"``, ``"access"``).
    table
        Database table name (optionally ``"schema.table"``), Excel sheet name,
        or HDF5 key.
    data
        Accompanying data extract file path when *format* is ``"cobol"`` (or *uri*
        points to a COBOL copybook).
    options
        Optional reader or connection options forwarded to :class:`~dataspector.core.GenericData`.
    """

    uri: str | pathlib.Path
    format: str | None = None
    table: str | None = None
    data: str | pathlib.Path | None = None
    options: dict[str, Any] = dataclasses.field(default_factory=dict)


def interpolate_env_vars(text: str) -> str:
    """Expand ``${VAR_NAME}`` placeholders in *text* from :data:`os.environ`.

    Parameters
    ----------
    text
        Input locator string or URL.

    Returns
    -------
    str
        String with known environment variables expanded.
    """
    if "${" not in text:
        return text
    return _ENV_VAR_PATTERN.sub(lambda m: os.environ.get(m.group("name"), m.group(0)), text)


def _coerce_query_value(val: str) -> Any:
    """Convert URL query parameter strings into Python booleans, numbers, or lists."""
    lowered = val.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return ast.literal_eval(val)
    except Exception:
        return val


def _extract_fragment_and_query(
    raw_target: str,
) -> tuple[str, str | None, dict[str, Any]]:
    """Split ``#fragment`` and ``?key=val`` from *raw_target*."""
    fragment: str | None = None
    target = raw_target
    if "#" in target:
        target, frag = target.rsplit("#", 1)
        fragment = urllib.parse.unquote(frag).strip() or None

    query_opts: dict[str, Any] = {}
    if "?" in target:
        base, qs = target.split("?", 1)
        target = base
        for k, vals in urllib.parse.parse_qs(qs, keep_blank_values=False).items():
            if vals:
                query_opts[k] = _coerce_query_value(vals[-1])

    return target, fragment, query_opts


def connect_to_copybook(
    layout: str | pathlib.Path,
    data: str | pathlib.Path | None = None,
    force: bool = False,
) -> tuple[coboller.Copybook | None, pathlib.Path | None]:
    """Attempt to parse *layout* as a COBOL copybook and resolve *data*.

    Parameters
    ----------
    layout
        Path to the COBOL copybook file.
    data
        Optional path to the accompanying COBOL data file.
    force
        When ``True``, attempt to parse *layout* as a COBOL copybook regardless
        of its file extension (used by ``cobol://`` locators).

    Returns
    -------
    tuple[Copybook | None, pathlib.Path | None]
        Parsed copybook and resolved data file path, or ``None`` entries if invalid/missing.
    """
    layout_path = resolve_cross_platform_path(layout)
    data_path = resolve_cross_platform_path(data) if data is not None else None

    copybook: coboller.Copybook | None = None
    if layout_path.is_file() and (force or layout_path.suffix.lower() in {".cbl", ".cpy", ".cob"}):
        try:
            parsed = coboller.Copybook(layout_path)
            if parsed.records:
                copybook = parsed
        except Exception as exc:
            logger.trace("Could not parse {} as COBOL copybook: {}", layout_path, exc)

    resolved_data = (
        data_path
        if (copybook is not None and data_path is not None and data_path.exists())
        else None
    )
    return copybook, resolved_data


def connect_to_embedded_db(database: str | pathlib.Path) -> Any:
    """Connect to an embedded SQLite, DuckDB, or MS Access database file.

    Parameters
    ----------
    database
        Path to the embedded database file (``.sqlite``, ``.db``, ``.duckdb``,
        ``.mdb``, ``.accdb``).

    Returns
    -------
    Engine | pyodbc.Connection | None
        Active database handle, or ``None`` if unsupported/unavailable.
    """
    db_path = resolve_cross_platform_path(database)
    suffix = db_path.suffix.lower()
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        try:
            engine = create_engine(f"sqlite:///{db_path}")
            sa_inspect(engine).get_table_names()
            return engine
        except Exception as exc:
            logger.trace("SQLite connection failed for {}: {}", db_path, exc)
            return None

    if suffix == ".duckdb":
        try:
            engine = create_engine(f"duckdb:///{db_path}")
            sa_inspect(engine).get_table_names()
            return engine
        except Exception as exc:
            logger.trace("DuckDB connection failed for {}: {}", db_path, exc)
            return None

    if pyodbc is not None and suffix in {".mdb", ".accdb"}:
        for base in _JET_CONNECTIONS:
            connstr = base % str(db_path)
            try:
                return pyodbc.connect(connstr)
            except Exception as exc:
                logger.trace("MS Access ODBC connection failed: {}", exc)
    return None


def connect_to_sqlalchemy_url(url: str) -> Engine | None:
    """Create a SQLAlchemy :class:`~sqlalchemy.engine.Engine` from a database URL.

    Normalizes common scheme aliases (``postgres://`` -> ``postgresql://``,
    ``sqlite3://`` -> ``sqlite://``, ``sqlserver://`` -> ``mssql+pyodbc://``)
    and handles relative/absolute SQLite file paths cleanly.

    Parameters
    ----------
    url
        SQLAlchemy-compatible database URL.

    Returns
    -------
    Engine | None
        Configured SQLAlchemy engine, or ``None`` if engine creation fails.
    """
    normalized = url.strip()
    scheme, sep, rest = normalized.partition("://")
    if not sep:
        return None

    base_scheme = scheme.lower().split("+", 1)[0]
    if scheme.lower() == "postgres":
        normalized = f"postgresql://{rest}"
    elif scheme.lower() == "sqlite3":
        normalized = f"sqlite://{rest}"
    elif scheme.lower() == "sqlserver":
        normalized = f"mssql+pyodbc://{rest}"

    if base_scheme in {"sqlite", "sqlite3", "duckdb"}:
        raw_path, q_sep, q_str = rest.partition("?")
        if raw_path != "/:memory:":
            candidate_str = raw_path
            db_file = resolve_cross_platform_path(candidate_str)
            if not db_file.exists() and raw_path.startswith("/"):
                alt_file = resolve_cross_platform_path(raw_path[1:])
                if alt_file.exists():
                    db_file = alt_file
            driver_prefix = "duckdb" if base_scheme == "duckdb" else "sqlite"
            suffix_q = f"?{q_str}" if q_sep else ""
            normalized = f"{driver_prefix}:///{db_file}{suffix_q}"

    try:
        return create_engine(normalized)
    except Exception as exc:
        logger.trace("Could not create SQLAlchemy engine for {}: {}", normalized, exc)
        return None


def resolve_location_with_options(
    location: str | pathlib.Path | DataSourceSpec | Mapping[str, Any],
) -> tuple[pathlib.Path | coboller.Copybook | None, Any, str | None, dict[str, Any]]:
    """Resolve *location* into ``(path, engine, table, inferred_options)``.

    Supports the following unified locator styles:

    - Unified URI schemes for files (``csv://path``, ``tsv://path``, ``fwf://path``,
      ``excel://book.xlsx#Sheet1``, ``parquet://path``, ``json://path``,
      ``jsonl://path``, ``hdf5://store.h5#key``)
    - Unified COBOL locators (``cobol://layout.cbl::data.dat`` or
      ``cobol://layout.cbl?data=data.dat&encoding=cp500``)
    - Unified SQL database URLs across any dialect (``sqlite:///db.sqlite#Table1``,
      ``postgresql+psycopg://user:pass@host:5432/db#public.users``,
      ``mysql+pymysql://user:pass@host/db#orders``,
      ``snowflake://user:pass@account/db/schema?warehouse=WH#table``,
      ``mssql+pyodbc://server/db#accounts``, ``duckdb:///file.duckdb#events``,
      ``access://file.accdb#Orders``)
    - Structured :class:`DataSourceSpec` or ``dict`` specifications
    - Plain file paths with optional ``#Sheet`` / ``#Table`` fragment

    Parameters
    ----------
    location
        Source locator in any supported representation.

    Returns
    -------
    tuple[pathlib.Path | Copybook | None, Any, str | None, dict[str, Any]]
        ``(path, engine, table, inferred_options)`` quadruple.
    """
    if isinstance(location, Mapping):
        spec = DataSourceSpec(
            uri=location.get("uri") or location.get("path") or location.get("location", ""),
            format=location.get("format") or location.get("type"),
            table=location.get("table") or location.get("sheet") or location.get("key"),
            data=location.get("data"),
            options=dict(location.get("options") or location.get("reader_options") or {}),
        )
        return _resolve_spec(spec)

    if isinstance(location, DataSourceSpec):
        return _resolve_spec(location)

    if isinstance(location, pathlib.Path):
        location = str(location)

    if isinstance(location, str):
        expanded = interpolate_env_vars(location.strip())

        # 1. Check for URI scheme: <scheme>://<rest>
        scheme_match = re.match(
            r"^(?P<scheme>[A-Za-z][A-Za-z0-9+._-]*):\/\/(?P<rest>.+)$", expanded
        )
        if scheme_match is not None:
            return _resolve_uri_scheme(
                scheme_match.group("scheme"),
                scheme_match.group("rest"),
                expanded,
            )

        # 2. Check for plain path with #Sheet or #Table fragment (e.g. "workbook.xlsx#Sheet1")
        if "#" in expanded:
            base_str, table_frag, query_opts = _extract_fragment_and_query(expanded)
            base_path = resolve_cross_platform_path(base_str)
            if base_path.exists():
                db_engine = connect_to_embedded_db(base_path)
                return base_path, db_engine, table_frag, query_opts

        # 3. Direct filesystem path
        loc_path = resolve_cross_platform_path(expanded)
        try:
            loc_exists = loc_path.exists()
        except OSError:
            loc_exists = False

        if loc_exists:
            copybook, _ = connect_to_copybook(loc_path)
            return (copybook if copybook is not None else loc_path), None, None, {}

        return loc_path, None, None, {}

    return None, None, None, {}


def _resolve_uri_scheme(
    scheme: str,
    rest: str,
    full_uri: str,
) -> tuple[pathlib.Path | coboller.Copybook | None, Any, str | None, dict[str, Any]]:
    """Resolve a ``<scheme>://<rest>`` unified locator."""
    scheme_lower = scheme.lower()
    base_scheme = scheme_lower.split("+", 1)[0]

    # A. COBOL scheme: cobol://layout.cbl::data.dat or cobol://layout.cbl?data=data.dat&encoding=cp500
    if scheme_lower in _COBOL_SCHEMES:
        clean_rest, frag, query_opts = _extract_fragment_and_query(rest)
        data_arg = query_opts.pop("data", None) or frag
        if "::" in clean_rest:
            layout_str, data_str = clean_rest.split("::", 1)
            data_arg = data_str or data_arg
        else:
            layout_str = clean_rest
        copybook, datapath = connect_to_copybook(layout_str, data_arg, force=True)
        if copybook is not None:
            return copybook, datapath, None, query_opts
        return resolve_cross_platform_path(layout_str), None, None, query_opts

    # B. Explicit file format scheme: csv://, tsv://, fwf://, excel://, parquet://, json://, jsonl://, hdf5://
    if scheme_lower in _FILE_SCHEMES:
        clean_rest, frag, query_opts = _extract_fragment_and_query(rest)
        table = (
            query_opts.pop("sheet", None)
            or query_opts.pop("table", None)
            or query_opts.pop("key", None)
            or frag
        )
        reader_marker = _FILE_SCHEMES[scheme_lower]
        if reader_marker == "fwf":
            query_opts.setdefault("reader_type", "fwf")
        elif reader_marker:
            query_opts.setdefault("reader_type", reader_marker)
        if scheme_lower == "tsv":
            query_opts.setdefault("delimiter", "\t")
        file_path = resolve_cross_platform_path(clean_rest)
        return file_path, None, (str(table) if table is not None else None), query_opts

    # C. MS Access scheme: access://path/to/file.accdb#Table1
    if scheme_lower in _ACCESS_SCHEMES:
        clean_rest, frag, query_opts = _extract_fragment_and_query(rest)
        table = query_opts.pop("table", None) or frag
        db_path = resolve_cross_platform_path(clean_rest)
        return db_path, connect_to_embedded_db(db_path), (str(table) if table else None), query_opts

    # D. SQLAlchemy / Database schemes (sqlite, postgres, postgresql, mysql, mariadb, mssql, oracle, duckdb, ...)
    if base_scheme in _SQLALCHEMY_PREFIXES:
        no_frag_uri = full_uri
        frag_table: str | None = None
        if "#" in no_frag_uri:
            no_frag_uri, raw_frag = no_frag_uri.rsplit("#", 1)
            frag_table = urllib.parse.unquote(raw_frag).strip() or None

        # Check for ?table=... in the URL query string and strip it before passing to SQLAlchemy
        base_url_part, q_sep, raw_query = no_frag_uri.partition("?")
        if q_sep:
            query_pairs = urllib.parse.parse_qsl(raw_query, keep_blank_values=True)
            remaining_pairs: list[tuple[str, str]] = []
            for k, v in query_pairs:
                if k == "table" and frag_table is None:
                    frag_table = v
                else:
                    remaining_pairs.append((k, v))
            clean_query = urllib.parse.urlencode(remaining_pairs)
            clean_db_url = f"{base_url_part}?{clean_query}" if clean_query else base_url_part
        else:
            clean_db_url = base_url_part

        # For local SQLite / DuckDB files, also keep `path` populated for file metadata checks
        local_db_path: pathlib.Path | None = None
        if base_scheme in {"sqlite", "sqlite3", "duckdb"}:
            _, _, after_scheme = clean_db_url.partition("://")
            raw_file_part = after_scheme.split("?", 1)[0]
            if raw_file_part and raw_file_part != "/:memory:":
                candidate_str = (
                    raw_file_part[1:] if raw_file_part.startswith("/") else raw_file_part
                )
                candidate = resolve_cross_platform_path(candidate_str)
                if candidate.exists():
                    local_db_path = candidate
                else:
                    direct_candidate = resolve_cross_platform_path(raw_file_part)
                    if direct_candidate.exists():
                        local_db_path = direct_candidate

        engine = connect_to_sqlalchemy_url(clean_db_url)
        return local_db_path, engine, frag_table, {}

    return resolve_cross_platform_path(full_uri), None, None, {}


def _resolve_spec(
    spec: DataSourceSpec,
) -> tuple[pathlib.Path | coboller.Copybook | None, Any, str | None, dict[str, Any]]:
    """Resolve a structured :class:`DataSourceSpec` into ``(path, engine, table, options)``."""
    opts = dict(spec.options) if spec.options else {}
    fmt = spec.format.lower().strip().lstrip(".") if spec.format else None
    uri_str = interpolate_env_vars(str(spec.uri))

    if fmt in _COBOL_SCHEMES or spec.data is not None:
        copybook, datapath = connect_to_copybook(
            uri_str,
            interpolate_env_vars(str(spec.data)) if spec.data is not None else None,
            force=True,
        )
        return (
            (copybook if copybook is not None else resolve_cross_platform_path(uri_str)),
            datapath,
            None,
            opts,
        )

    if fmt in _FILE_SCHEMES:
        marker = _FILE_SCHEMES[fmt]
        if marker == "fwf":
            opts.setdefault("reader_type", "fwf")
        elif marker:
            opts.setdefault("reader_type", marker)
        if fmt == "tsv":
            opts.setdefault("delimiter", "\t")
        return resolve_cross_platform_path(uri_str), None, spec.table, opts

    if fmt in _ACCESS_SCHEMES:
        db_path = resolve_cross_platform_path(uri_str)
        return db_path, connect_to_embedded_db(db_path), spec.table, opts

    if "://" in uri_str or (fmt and fmt.split("+", 1)[0] in _SQLALCHEMY_PREFIXES):
        full_url = uri_str if "://" in uri_str else f"{fmt}://{uri_str}"
        path, engine, parsed_table, uri_opts = resolve_location_with_options(full_url)
        merged = {**uri_opts, **opts}
        return path, engine, (spec.table or parsed_table), merged

    path, engine, parsed_table, uri_opts = resolve_location_with_options(uri_str)
    merged = {**uri_opts, **opts}
    return path, engine, (spec.table or parsed_table), merged


def connect_to_location(
    location: str | pathlib.Path | DataSourceSpec | Mapping[str, Any],
) -> tuple[pathlib.Path | coboller.Copybook | None, Any, str | None]:
    """Resolve *location* into a ``(path, engine, table)`` triple.

    Parameters
    ----------
    location
        File/directory path, unified URI locator (``'csv://...'``,
        ``'excel://book.xlsx#Sheet1'``, ``'cobol://layout.cbl::data.dat'``,
        ``'postgresql+psycopg://...#table'``), or :class:`DataSourceSpec`.

    Returns
    -------
    tuple[pathlib.Path | Copybook | None, Any, str | None]
        ``(path, engine, table)`` triple describing the resolved data source.
    """
    path, engine, table, _ = resolve_location_with_options(location)
    return path, engine, table


def connect_to_server(server: str, database: str) -> Engine | None:
    """Try ODBC connection templates to connect to a remote SQL Server database.

    Parameters
    ----------
    server
        Database server hostname or instance name.
    database
        Target database name.

    Returns
    -------
    Engine | None
        Connected SQLAlchemy engine, or ``None`` if no template succeeded.
    """
    if pyodbc is None:
        logger.trace("pyodbc is not installed; skipping remote SQL Server connection.")
        return None

    ad_odbc = urllib.parse.quote_plus(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};DATABASE={database};"
        "Authentication=ActiveDirectoryIntegrated;"
    )
    templates = (
        f"mssql+pyodbc:///?odbc_connect={ad_odbc}",
        f"mssql+pyodbc://{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server",
        f"mssql+pyodbc://{server}/{database}?driver=SQL+Server+Native+Client+11.0",
    )
    for url in templates:
        try:
            engine = create_engine(url)
            sa_inspect(engine).get_table_names()
            return engine
        except Exception as exc:
            logger.trace("Server connection template failed: {}", exc)
    return None


def is_pyodbc_connection(obj: Any) -> bool:
    """Return ``True`` if *obj* is a :class:`pyodbc.Connection` instance.

    Parameters
    ----------
    obj
        Candidate database handle.

    Returns
    -------
    bool
        ``True`` when ``pyodbc`` is installed and *obj* is a connection.
    """
    return pyodbc is not None and isinstance(obj, pyodbc.Connection)


def resolve_cross_platform_path(raw: str | pathlib.Path) -> pathlib.Path:
    """Resolve *raw* into a :class:`pathlib.Path`, normalizing Windows backslashes on POSIX.

    Parameters
    ----------
    raw
        Filesystem path string or :class:`pathlib.Path`.

    Returns
    -------
    pathlib.Path
        Normalized path (preferring forward-slash fallback if it exists).
    """
    if isinstance(raw, pathlib.Path):
        if raw.exists() or "\\" not in str(raw):
            return raw
        candidate = pathlib.Path(str(raw).replace("\\", "/"))
        return candidate if candidate.exists() else raw

    path = pathlib.Path(raw)
    if "\\" in raw and not path.exists():
        candidate = pathlib.Path(raw.replace("\\", "/"))
        if candidate.exists():
            return candidate
    return path
