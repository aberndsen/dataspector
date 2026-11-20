"""Path normalization and data-source connection helpers for :mod:`dataspector.core`."""

from __future__ import annotations

import importlib
import pathlib
import re
import urllib.parse
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

_SQL_MATCH = re.compile(
    r"^\[(?P<server>.+?)\].*?\[[^\S\n]*(?P<database>.+?)\].*?\[[^\S\n]*(?P<table>.+?)\].*$",
    re.I,
)
_EMBEDDED_DB_MATCH = re.compile(
    r"^\[[^\S\n]*(?P<database>.+?)\].*?\[[^\S\n]*(?P<table>.+?)\].*$",
    re.I,
)


def connect_to_copybook(
    layout: str | pathlib.Path,
    data: str | pathlib.Path | None = None,
) -> tuple[coboller.Copybook | None, pathlib.Path | None]:
    """Attempt to parse *layout* as a COBOL copybook and resolve *data*.

    Parameters
    ----------
    layout
        Path to the COBOL copybook file.
    data
        Optional path to the accompanying COBOL data file.

    Returns
    -------
    tuple[Copybook | None, pathlib.Path | None]
        Parsed copybook and resolved data file path, or ``None`` entries if invalid/missing.
    """
    layout_path = resolve_cross_platform_path(layout)
    data_path = resolve_cross_platform_path(data) if data is not None else None

    copybook: coboller.Copybook | None = None
    if layout_path.is_file() and layout_path.suffix.lower() in {".cbl", ".cpy", ".cob"}:
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
    """Connect to an embedded SQLite or MS Access database file.

    Parameters
    ----------
    database
        Path to the embedded database file (``.sqlite``, ``.db``, ``.mdb``, ``.accdb``).

    Returns
    -------
    Engine | pyodbc.Connection | None
        Active database handle, or ``None`` if unsupported/unavailable.
    """
    db_path = resolve_cross_platform_path(database)
    if db_path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        try:
            engine = create_engine(f"sqlite:///{db_path}")
            sa_inspect(engine).get_table_names()
            return engine
        except Exception as exc:
            logger.trace("SQLite connection failed for {}: {}", db_path, exc)
            return None

    if pyodbc is not None and db_path.suffix.lower() in {".mdb", ".accdb"}:
        for base in _JET_CONNECTIONS:
            connstr = base % str(db_path)
            try:
                return pyodbc.connect(connstr)
            except Exception as exc:
                logger.trace("MS Access ODBC connection failed: {}", exc)
    return None


def connect_to_location(
    location: str | pathlib.Path | tuple[Any, ...],
) -> tuple[pathlib.Path | coboller.Copybook | None, Any, str | None]:
    """Resolve *location* into a ``(path, engine, table)`` triple.

    Parameters
    ----------
    location
        File/directory path, bracketed locator (``'[file][table]'``,
        ``'[layout.cbl][data.dat]'``, ``'[server][db][table]'``), or tuple.

    Returns
    -------
    tuple[pathlib.Path | Copybook | None, Any, str | None]
        ``(path, engine, table)`` triple describing the resolved data source.
    """
    if isinstance(location, pathlib.Path):
        location = str(location)

    if isinstance(location, str):
        loc_path = resolve_cross_platform_path(location)
        try:
            loc_exists = loc_path.exists()
        except OSError:
            loc_exists = False

        if loc_exists:
            copybook, _ = connect_to_copybook(loc_path)
            return (copybook if copybook is not None else loc_path), None, None

        sql_m = _SQL_MATCH.match(location)
        emb_m = _EMBEDDED_DB_MATCH.match(location)

        if sql_m is not None:
            server = sql_m.group("server")
            database = sql_m.group("database")
            table = sql_m.group("table")
            return None, connect_to_server(server, database), table

        if emb_m is not None:
            raw_db = emb_m.group("database")
            raw_tbl = emb_m.group("table")
            db_path = resolve_cross_platform_path(raw_db)
            copybook, datapath = connect_to_copybook(db_path, raw_tbl)
            if copybook is not None:
                return copybook, datapath, None
            if db_path.exists():
                return db_path, connect_to_embedded_db(db_path), raw_tbl

        return loc_path, None, None

    if isinstance(location, tuple):
        if len(location) >= 2:
            copybook, datapath = connect_to_copybook(location[0], location[1])
            if copybook is not None:
                return copybook, datapath, None

            first_path = resolve_cross_platform_path(location[0])
            if first_path.exists():
                return first_path, connect_to_embedded_db(first_path), str(location[1])

            engine = connect_to_server(str(location[0]), str(location[1]))
            table = str(location[2]) if len(location) > 2 else None
            return None, engine, table

        if len(location) == 1:
            return connect_to_location(location[0])

    return None, None, None


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
