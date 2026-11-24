"""Core data-source abstraction and integrity check execution engine.

Provides :class:`GenericData` to unify metadata queries and chunked streaming
across CSV, delimited/fixed-width text, Excel, Parquet, JSON/JSONL, SQLite,
SQL Server / MS Access (optional ODBC), and COBOL copybook + data files,
together with :class:`CheckeredHistory` and the high-level runners
:func:`run_checks_on_location` and :func:`load_and_run_checks`.
"""

from __future__ import annotations

import datetime
import glob
import multiprocessing as mp
import pathlib
import re
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import MetaData, Table, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine

from dataspector import checkers, coboller
from dataspector._connectors import (
    DataSourceSpec,
    connect_to_copybook,
    connect_to_embedded_db,
    connect_to_location,
    connect_to_server,
    connect_to_sqlalchemy_url,
    interpolate_env_vars,
    is_pyodbc_connection,
    resolve_location_with_options,
)
from dataspector._reporting import (
    available_checks,
    chunks_to_dataframe,
    export_chunks,
    load_driverfile,
    parse_cell_to_dict,
    pretty_print_results,
    version_adder,
    write_excel_report,
)
from dataspector.checkers import CheckOutcome

# ---------------------------------------------------------------------------
# Primary Public Classes
# ---------------------------------------------------------------------------


class GenericData:
    """Format-agnostic wrapper exposing unified metadata and chunked reading.

    Parameters
    ----------
    location
        Locator describing a file, directory, COBOL pair, or database table.
    reader_options
        Optional keyword arguments forwarded to the underlying reader
        (e.g. ``{"widths": [10, 20]}`` for fixed-width files or
        ``{"encoding": "cp500"}`` for COBOL files).

    Attributes
    ----------
    path
        Local file path or parsed :class:`~dataspector.coboller.copybook.Copybook`.
    engine
        Database handle, or COBOL data file path when *path* is a copybook.
    table
        Database table or Excel sheet name, if applicable.
    """

    def __init__(
        self,
        location: str | pathlib.Path | DataSourceSpec | Mapping[str, Any] | GenericData,
        reader_options: dict[str, Any] | None = None,
    ) -> None:
        if isinstance(location, GenericData):
            raw_location: Any = location._location
            if reader_options is None:
                reader_options = dict(location.reader_options) if location.reader_options else None
        elif isinstance(location, pathlib.Path):
            raw_location = str(location)
        else:
            raw_location = location

        self._location: Any = raw_location
        self.path, self.engine, self.table, uri_opts = resolve_location_with_options(raw_location)

        merged_opts: dict[str, Any] = dict(uri_opts) if uri_opts else {}
        if reader_options:
            merged_opts.update(reader_options)
        self.reader_options: dict[str, Any] | None = merged_opts if merged_opts else None

        self._tables: list[str] | None = None
        self._columns: list[Any] | None = None
        self._number_of_records: int | None = None
        self._exist: bool | None = None
        self._delim: str | None = None

    def __repr__(self) -> str:
        display_path = self.path if self.path is not None else self._location
        return f"<GenericData: [{display_path}][{self.engine}][{self.table}]>"

    @property
    def columns(self) -> list[Any] | None:
        """Column (field) names present in this data source."""
        if self._columns is None:
            if isinstance(self.path, coboller.Copybook):
                self._columns = list(self.path.fields)
            else:
                for chunk in self.yield_data(chunksize=2):
                    if isinstance(chunk, pd.DataFrame):
                        self._columns = list(chunk.columns)
                    break
        return self._columns

    @property
    def exists(self) -> bool:
        """``True`` if the underlying file, COBOL pair, or database table exists."""
        if self._exist is None:
            if isinstance(self.path, coboller.Copybook):
                if isinstance(self.engine, pathlib.Path):
                    self._exist = self.path.exists and self.engine.exists()
                else:
                    logger.warning(
                        "COBOL existence checks ideally verify both copybook and data via "
                        "cobol://layout.cbl::data.dat."
                    )
                    self._exist = self.path.exists
            elif self.engine is not None:
                try:
                    self._exist = self.columns is not None
                except Exception:
                    self._exist = False
            elif isinstance(self.path, pathlib.Path):
                self._exist = self.path.exists()
            else:
                self._exist = False
        return self._exist

    @property
    def fields(self) -> list[Any] | None:
        """Alias for :attr:`columns`."""
        return self.columns

    @property
    def last_modified(self) -> datetime.datetime | None:
        """UTC timestamp of when this data source was last modified."""
        if isinstance(self.path, coboller.Copybook):
            mtime = datetime.datetime.fromtimestamp(
                self.path.copybook.stat().st_mtime,
                tz=datetime.UTC,
            )
            if isinstance(self.engine, pathlib.Path) and self.engine.exists():
                data_mtime = datetime.datetime.fromtimestamp(
                    self.engine.stat().st_mtime,
                    tz=datetime.UTC,
                )
                return min(mtime, data_mtime)
            return mtime

        if isinstance(self.path, pathlib.Path) and self.path.exists():
            return datetime.datetime.fromtimestamp(
                self.path.stat().st_mtime,
                tz=datetime.UTC,
            )

        if isinstance(self.engine, Engine):
            if "mssql" in str(self.engine.url):
                qry = sa_text("SELECT MAX(modify_date) AS last_modify_date FROM sys.tables")
                with self.engine.begin() as conn:
                    row = conn.execute(qry).fetchone()
                    if row and row[0] is not None:
                        val = row[0]
                        if isinstance(val, datetime.datetime) and val.tzinfo is None:
                            return val.replace(tzinfo=datetime.UTC)
                        return val
            raise NotImplementedError(
                "Database last_modified is currently supported only for SQL Server."
            )

        return None

    @property
    def list_of_tables(self) -> list[str] | None:
        """List of tables (database) or worksheets (Excel), or ``None`` if not applicable."""
        if self._tables is None:
            if isinstance(self.engine, Engine):
                self._tables = list(sa_inspect(self.engine).get_table_names())
            elif is_pyodbc_connection(self.engine):
                with self.engine.cursor() as curr:
                    self._tables = [t[2] for t in curr.tables()]
            elif (
                isinstance(self.path, pathlib.Path)
                and self.path.is_file()
                and self.path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}
            ):
                with pd.ExcelFile(self.path) as xf:
                    self._tables = [str(s) for s in xf.sheet_names]
        return self._tables

    @property
    def number_of_records(self) -> int:
        """Total number of records in this source (cached after first computation)."""
        if self._number_of_records is None:
            nrecords = 0
            if isinstance(self.engine, Engine) and self.table is not None:
                schema_name: str | None = None
                table_name = self.table
                if "." in self.table:
                    schema_name, table_name = self.table.split(".", 1)
                if self.reader_options and "schema" in self.reader_options and schema_name is None:
                    schema_name = str(self.reader_options["schema"])
                tbl = Table(table_name, MetaData(), schema=schema_name)
                stmt = select(func.count()).select_from(tbl)
                with self.engine.connect() as conn:
                    val = conn.execute(stmt).scalar()
                    if val is not None:
                        nrecords = int(val)
            elif is_pyodbc_connection(self.engine) and self.table is not None:
                qry = f"SELECT COUNT(*) AS Nrecords FROM [{self.table}]"
                df = pd.read_sql_query(qry, self.engine)
                if not df.empty:
                    nrecords = int(df["Nrecords"].iloc[0])
            elif isinstance(self.path, coboller.Copybook) or (
                isinstance(self.path, pathlib.Path) and self.path.exists()
            ):
                for chunk in self.yield_data():
                    nrecords += len(chunk)
            else:
                raise NotImplementedError(
                    f"{self} format does not support number_of_records query."
                )
            self._number_of_records = nrecords
        return self._number_of_records

    def determine_delimiter(
        self,
        delimiters: Sequence[str] = (",", "|", "\t"),
        nlines: int = 10,
    ) -> str | None:
        """Infer the most frequent delimiter across the first *nlines* lines of a text file.

        Parameters
        ----------
        delimiters
            Candidate delimiter characters to count.
        nlines
            Number of leading lines to sample.

        Returns
        -------
        str | None
            Most frequent candidate delimiter, or ``None`` if none appear or
            the source is not a local file.
        """
        if self._delim is None and isinstance(self.path, pathlib.Path) and self.path.is_file():
            with self.path.open("r", encoding="utf-8", errors="replace") as fh:
                sample = "".join(fh.readline() for _ in range(nlines))
            best_count = 0
            for delim in delimiters:
                count = sample.count(delim)
                if count > best_count:
                    best_count = count
                    self._delim = delim
            logger.trace("Inferred delimiter {!r} for {}", self._delim, self.path)
        return self._delim

    determine_delimeter = determine_delimiter

    def fuzzy_find(self, pattern: str) -> list[str] | None:
        """Search for *pattern* in directory paths, Excel sheet names, or database tables.

        Parameters
        ----------
        pattern
            Shell-style wildcard pattern (e.g. ``"*.csv"`` or ``"*users*"``).

        Returns
        -------
        list[str] | None
            Matching paths, sheet names, or table names, or ``None`` when
            pattern search does not apply to this source.
        """
        tables = self.list_of_tables
        if tables is not None:
            escaped = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".?")
            regex = re.compile(f"^.*{escaped}.*$", re.I)
            return [t for t in tables if regex.match(t) is not None]

        if isinstance(self.path, pathlib.Path) and self.path.is_dir():
            return glob.glob(str(self.path / pattern), recursive=True)

        return None

    def is_modified_recently(self, days_ago: float) -> bool | None:
        """Return ``True`` if the source was modified within *days_ago* days of now.

        Parameters
        ----------
        days_ago
            Freshness window in days.

        Returns
        -------
        bool | None
            ``True`` if modified within the window, ``False`` otherwise, or
            ``None`` if modification time is unavailable.
        """
        mtime = self.last_modified
        if mtime is None:
            return None
        cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_ago)
        if mtime.tzinfo is None:
            mtime = mtime.replace(tzinfo=datetime.UTC)
        return mtime > cutoff

    def storage_size_roughly(self, rough_size: int, tolerance: float = 0.2) -> bool:
        """Return ``True`` if file byte size is within *tolerance* of *rough_size*.

        Parameters
        ----------
        rough_size
            Expected file size in bytes.
        tolerance
            Allowed relative deviation (default ``0.2`` for ±20%).

        Returns
        -------
        bool
            ``True`` when the actual file size falls within tolerance, else ``False``.
        """
        if isinstance(self.path, coboller.Copybook):
            if not isinstance(self.engine, pathlib.Path):
                raise ValueError(
                    "Please specify the location of the underlying data for this COBOL layout."
                )
            actual = self.engine.stat().st_size
        elif isinstance(self.path, pathlib.Path) and self.path.exists():
            actual = self.path.stat().st_size
        else:
            logger.error("Storage size check is not supported for {}.", self)
            return False

        if actual > 0:
            return abs(actual - rough_size) / actual <= tolerance
        return abs(actual - rough_size) <= tolerance

    def convert(
        self,
        output: str | pathlib.Path,
        chunksize: int = 5000,
    ) -> pathlib.Path:
        """Convert this data source into CSV, TSV, JSONL, JSON, Excel, or Parquet.

        Streams chunk-by-chunk via :meth:`yield_data` for ``.csv``, ``.tsv``,
        and ``.jsonl`` outputs to keep memory bounded on large sources.

        Parameters
        ----------
        output
            Destination file path whose extension selects the output format.
        chunksize
            Number of rows per streaming chunk.

        Returns
        -------
        pathlib.Path
            Path to the written output file.
        """
        return export_chunks(
            self.yield_data(chunksize=chunksize),
            output,
            empty_columns=self.columns,
        )

    def to_dataframe(
        self,
        nrows: int | None = None,
        chunksize: int = 500,
    ) -> pd.DataFrame:
        """Load records from this data source into a single :class:`pandas.DataFrame`.

        Reads internally via chunked streaming (:meth:`yield_data`) and stops
        early once *nrows* rows are collected. For sources larger than memory,
        iterate over :meth:`yield_data` directly instead.

        Parameters
        ----------
        nrows
            Optional maximum number of records to return (``None`` reads all).
        chunksize
            Number of rows requested per internal streaming chunk.

        Returns
        -------
        pandas.DataFrame
            Materialized records (empty DataFrame if source has no rows).
        """
        eff_chunk = min(chunksize, nrows) if nrows is not None and nrows > 0 else chunksize
        return chunks_to_dataframe(
            self.yield_data(chunksize=eff_chunk),
            nrows=nrows,
            empty_columns=self.columns,
        )

    def yield_data(self, chunksize: int = 500) -> Iterator[Any]:
        """Stream records from this data source as :class:`pandas.DataFrame` chunks.

        Parameters
        ----------
        chunksize
            Maximum number of rows per yielded chunk for chunkable formats.

        Yields
        ------
        pandas.DataFrame | str
            Decoded DataFrame chunks (or raw text lines for unrecognized formats).
        """
        opts = dict(self.reader_options) if self.reader_options else {}

        if isinstance(self.path, coboller.Copybook) and isinstance(self.engine, pathlib.Path):
            yield from self.path.yield_data(self.engine, chunksize=chunksize, **opts)
            return

        if self.engine is not None and self.table is not None:
            if is_pyodbc_connection(self.engine):
                qry = f"SELECT * FROM [{self.table}]"
                yield from pd.read_sql_query(qry, self.engine, chunksize=chunksize, **opts)
            elif isinstance(self.engine, Engine):
                table_name = self.table
                if "." in self.table and "schema" not in opts:
                    schema_part, table_name = self.table.split(".", 1)
                    opts["schema"] = schema_part
                yield from pd.read_sql_table(table_name, self.engine, chunksize=chunksize, **opts)
            return

        if not isinstance(self.path, pathlib.Path) or not self.path.is_file():
            return

        suffix = self.path.suffix.lower()
        readers: dict[str, Any] = {
            ".xlsx": pd.read_excel,
            ".xls": pd.read_excel,
            ".xlsm": pd.read_excel,
            ".hdf": pd.read_hdf,
            ".h5": pd.read_hdf,
            ".csv": pd.read_csv,
            ".tsv": pd.read_csv,
            ".txt": pd.read_csv,
            ".parquet": pd.read_parquet,
            ".json": pd.read_json,
            ".jsonl": pd.read_json,
        }
        chunkable = {".csv", ".tsv", ".txt", ".hdf", ".h5"}
        delimited = {".csv", ".tsv", ".txt"}

        raw_type = opts.pop("reader_type", None)
        norm_type: str | None = None
        if isinstance(raw_type, str):
            low = raw_type.lower().strip()
            if low in {"fwf", ".fwf", "fixed", "fixed_width", "fixed-width"}:
                norm_type = "fwf"
            elif low in {"excel", "xlsx", ".xlsx"}:
                norm_type = ".xlsx"
            elif low in {"hdf5", "hdf", "h5", ".h5", ".hdf"}:
                norm_type = ".h5"
            elif low in {"ndjson", "jsonl", ".jsonl"}:
                norm_type = ".jsonl"
            else:
                norm_type = low if low.startswith(".") else f".{low}"

        if "widths" in opts or norm_type == "fwf":
            reader: Any = pd.read_fwf
            is_chunkable = True
        else:
            effective_suffix = norm_type if norm_type in readers else suffix
            reader = readers.get(effective_suffix)
            is_chunkable = effective_suffix in chunkable
            if effective_suffix == ".tsv":
                opts.setdefault("delimiter", "\t")
            if effective_suffix in delimited and "delimiter" not in opts and "sep" not in opts:
                delim = self.determine_delimiter()
                if delim is not None:
                    opts["delimiter"] = delim
            if effective_suffix == ".jsonl":
                opts.setdefault("lines", True)

        if reader is None:
            logger.warning("Unrecognized file format {}; falling back to line reader.", self.path)
            with self.path.open("r", encoding="utf-8", errors="replace") as fh:
                yield from fh
            return

        if reader is pd.read_excel and self.table is not None:
            opts.setdefault("sheet_name", self.table)

        if is_chunkable:
            if reader is pd.read_hdf and self.table is not None:
                yield from reader(self.path, key=self.table, chunksize=chunksize, **opts)
            else:
                yield from reader(self.path, chunksize=chunksize, **opts)
        else:
            yield reader(self.path, **opts)


class CheckeredHistory:
    """Track and execute a list of integrity checks against a single data source.

    Parameters
    ----------
    location
        Target data source locator.
    checklist
        Sequence of check specifications — check names or tuples
        ``(checkname, kwargs[, severity[, reader_options]])``.
    """

    def __init__(
        self,
        location: str | pathlib.Path | DataSourceSpec | Mapping[str, Any] | GenericData,
        checklist: list[Any] | str,
    ) -> None:
        gd = location if isinstance(location, GenericData) else GenericData(location)
        self.location: Any = gd._location
        self.checklist: list[Any] = (
            [c.strip() for c in checklist.split(",")]
            if isinstance(checklist, str)
            else list(checklist)
        )

        self.cheques: dict[int, tuple[str, dict[str, Any]]] = {}
        self.results: dict[int, bool | None] = {}
        self.notes: dict[int, str | None] = {}
        self.exceptions: dict[int, str] = {}
        self.reader_options: dict[str, Any] = dict(gd.reader_options) if gd.reader_options else {}

        rlc = False
        for idx, item in enumerate(self.checklist):
            if isinstance(item, str):
                checkname = item
                this_kwargs: dict[str, Any] = {}
                this_reader: dict[str, Any] = {}
            else:
                checkname = str(item[0])
                this_kwargs = dict(item[1]) if len(item) > 1 and isinstance(item[1], dict) else {}
                this_reader = dict(item[3]) if len(item) > 3 and isinstance(item[3], dict) else {}

            if this_reader:
                self.reader_options.update(this_reader)

            if hasattr(checkers, checkname):
                self.cheques[idx] = (checkname, this_kwargs)
                if checkname.startswith("record_") or checkname in checkers.REQUIRES_ALL_DATA:
                    rlc = True
            else:
                self.results[idx] = False
                self.exceptions[idx] = f"Check '{checkname}' is not recognized in checkers module."

        self._rlc = rlc

    def __repr__(self) -> str:
        return f"<CheckeredHistory: {len(self.checklist)} checks on {self.location}>"

    @property
    def all_passed(self) -> bool:
        """``True`` if every check completed with ``True`` and no exceptions occurred."""
        return (
            not self.exceptions
            and len(self.results) == len(self.checklist)
            and all(v is True for v in self.results.values())
        )

    @property
    def record_level_checks_remain(self) -> bool:
        """``True`` if any pending checks require streaming records."""
        if self._rlc:
            self._rlc = any(
                name.startswith("record_") or name in checkers.REQUIRES_ALL_DATA
                for name, _ in self.cheques.values()
            )
        return self._rlc

    def apply_record_level_checks(self, chunksize: int = 500) -> None:
        """Stream records from the source and execute all pending record-level checks.

        Parameters
        ----------
        chunksize
            Number of rows requested per streamed chunk.
        """
        done: deque[int] = deque()
        last_record: Any = pd.DataFrame()
        gd = GenericData(self.location, reader_options=self.reader_options)

        for record in gd.yield_data(chunksize=chunksize):
            last_record = record
            for idx, (checkname, kwargs) in list(self.cheques.items()):
                if not (checkname.startswith("record_") or checkname in checkers.REQUIRES_ALL_DATA):
                    continue
                call_kwargs = dict(kwargs)
                if checkname in checkers.REQUIRES_ALL_DATA:
                    call_kwargs["_last_chunk"] = False
                if _run_check(self, idx, checkname, record, **call_kwargs):
                    done.append(idx)

            while done:
                self.cheques.pop(done.pop(), None)

            if not self.record_level_checks_remain:
                return

        empty_frame: Any = (
            last_record.iloc[0:0] if isinstance(last_record, pd.DataFrame) else pd.DataFrame()
        )
        for idx, (checkname, kwargs) in list(self.cheques.items()):
            if checkname.startswith("record_") or checkname in checkers.REQUIRES_ALL_DATA:
                call_kwargs = dict(kwargs)
                if checkname in checkers.REQUIRES_ALL_DATA:
                    call_kwargs["_last_chunk"] = True
                if _run_check(self, idx, checkname, empty_frame, **call_kwargs):
                    done.append(idx)

        while done:
            self.cheques.pop(done.pop(), None)

    def apply_source_level_checks(self) -> None:
        """Execute all pending source-level checks."""
        done: deque[int] = deque()
        gd = GenericData(self.location, reader_options=self.reader_options)
        for idx, (checkname, kwargs) in list(self.cheques.items()):
            if (
                checkname.startswith("source_")
                and checkname not in checkers.REQUIRES_ALL_DATA
                and _run_check(self, idx, checkname, gd, **kwargs)
            ):
                done.append(idx)
        while done:
            self.cheques.pop(done.pop(), None)


# ---------------------------------------------------------------------------
# High-Level Check Runners
# ---------------------------------------------------------------------------


def load_and_run_checks(
    driverfile: str | pathlib.Path,
    use_multiprocessing: bool = False,
) -> list[CheckeredHistory]:
    """Load *driverfile* and execute all configured checks across all locations.

    Parameters
    ----------
    driverfile
        Path to an Excel driver workbook listing data locations and checks.
    use_multiprocessing
        Execute checks across multiple locations concurrently using a process pool.

    Returns
    -------
    list[CheckeredHistory]
        Completed check histories, one per location in *driverfile*.
    """
    tocheck = load_driverfile(driverfile)
    results: list[CheckeredHistory] = []

    if use_multiprocessing and len(tocheck) > 1 and mp.cpu_count() > 1:
        n_procs = min(len(tocheck), mp.cpu_count() - 1)
        items = list(tocheck.items())
        logger.debug("Checking {} locations using {} processes.", len(items), n_procs)
        with mp.Pool(processes=n_procs) as pool:
            results = pool.map(_run_checks_on_location_star, items)
    else:
        for location, checks in tocheck.items():
            results.append(run_checks_on_location(location, checks))

    return results


def run_checks_on_location(
    location: str | pathlib.Path | DataSourceSpec | Mapping[str, Any] | GenericData,
    checklist: list[Any] | str,
) -> CheckeredHistory:
    """Run all checks in *checklist* against *location*.

    Parameters
    ----------
    location
        Target data source locator or :class:`GenericData` instance.
    checklist
        Comma-separated check names or sequence of check specifications.

    Returns
    -------
    CheckeredHistory
        Populated history containing results, notes, and any exceptions.
    """
    results = CheckeredHistory(location, checklist)
    results.apply_source_level_checks()
    if results.record_level_checks_remain:
        results.apply_record_level_checks()
    return results


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------


def _run_check(
    checkhist: CheckeredHistory,
    idx: int,
    checkname: str,
    arg: Any,
    **kwargs: Any,
) -> bool:
    """Invoke a single check function and update *checkhist* in place."""
    result: bool | None = None
    notes: str | None = None
    next_kwargs: dict[str, Any] = kwargs
    exception: Exception | None = None

    try:
        checkfunc = getattr(checkers, checkname)
        raw = checkfunc(arg, **kwargs)
        if isinstance(raw, CheckOutcome):
            result, notes, next_kwargs = raw.passed, raw.notes, raw.kwargs
        else:
            raw_result, next_kwargs = raw
            if isinstance(raw_result, tuple):
                result, notes = raw_result
            else:
                result = raw_result
    except Exception as exc:
        exception = exc
        result = False

    if result is not None or exception is not None or notes is not None:
        checkhist.results[idx] = result
        checkhist.notes[idx] = notes
        if exception is not None:
            checkhist.exceptions[idx] = str(exception)
        return True

    checkhist.cheques[idx] = (checkname, next_kwargs)
    return False


def _run_checks_on_location_star(args: tuple[Any, list[Any]]) -> CheckeredHistory:
    """Multiprocessing trampoline for :func:`run_checks_on_location`."""
    return run_checks_on_location(*args)


__all__ = [
    "CheckeredHistory",
    "DataSourceSpec",
    "GenericData",
    "available_checks",
    "connect_to_copybook",
    "connect_to_embedded_db",
    "connect_to_location",
    "connect_to_server",
    "connect_to_sqlalchemy_url",
    "interpolate_env_vars",
    "load_and_run_checks",
    "load_driverfile",
    "parse_cell_to_dict",
    "pretty_print_results",
    "resolve_location_with_options",
    "run_checks_on_location",
    "version_adder",
    "write_excel_report",
]
