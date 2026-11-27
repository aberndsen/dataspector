"""Excel driver workbook loading, terminal formatting, and Excel report export."""

from __future__ import annotations

import ast
import inspect
import json
import pathlib
from collections import defaultdict
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any

import pandas as pd
import xlsxwriter
from loguru import logger

from dataspector import checkers
from dataspector._connectors import redact_url

if TYPE_CHECKING:
    from dataspector.core import CheckeredHistory

available_checks: list[str] = [
    name
    for name, obj in checkers.__dict__.items()
    if callable(obj) and (name.startswith("source_") or name.startswith("record_"))
]

SUPPORTED_EXPORT_FORMATS: frozenset[str] = frozenset(
    {".csv", ".tsv", ".jsonl", ".json", ".xlsx", ".parquet"}
)


def chunks_to_dataframe(
    chunks: Iterator[Any],
    nrows: int | None = None,
    empty_columns: Sequence[Any] | None = None,
) -> pd.DataFrame:
    """Materialize streamed DataFrame chunks into a single :class:`pandas.DataFrame`.

    Parameters
    ----------
    chunks
        Iterator yielding :class:`pandas.DataFrame` chunks.
    nrows
        Optional maximum number of rows to collect before stopping iteration.
    empty_columns
        Column names to use if *chunks* yields no rows.

    Returns
    -------
    pandas.DataFrame
        Concatenated records.
    """
    frames: list[pd.DataFrame] = []
    collected = 0

    for chunk in chunks:
        if not isinstance(chunk, pd.DataFrame):
            continue
        if nrows is not None:
            remaining = nrows - collected
            if remaining <= 0:
                break
            if len(chunk) > remaining:
                chunk = chunk.iloc[:remaining]
        frames.append(chunk)
        collected += len(chunk)
        if nrows is not None and collected >= nrows:
            break

    if not frames:
        return pd.DataFrame(columns=list(empty_columns) if empty_columns is not None else [])
    return pd.concat(frames, ignore_index=True)


def export_chunks(
    chunks: Iterator[Any],
    output: str | pathlib.Path,
    empty_columns: Sequence[Any] | None = None,
) -> pathlib.Path:
    """Stream DataFrame chunks to CSV, TSV, JSONL, JSON, Excel, or Parquet.

    Parameters
    ----------
    chunks
        Iterator yielding :class:`pandas.DataFrame` chunks.
    output
        Destination file path whose extension selects the output format.
    empty_columns
        Column names written when *chunks* yields no rows.

    Returns
    -------
    pathlib.Path
        Path to the written output file.

    Raises
    ------
    ValueError
        If the destination extension is not in :data:`SUPPORTED_EXPORT_FORMATS`.
    """
    out_path = pathlib.Path(output)
    suffix = out_path.suffix.lower()
    if suffix not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError(
            f"Unsupported output format {suffix!r}; choose from {sorted(SUPPORTED_EXPORT_FORMATS)}."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if suffix in (".csv", ".tsv", ".jsonl"):
        sep = "\t" if suffix == ".tsv" else ","
        first = True
        for chunk in chunks:
            if not isinstance(chunk, pd.DataFrame):
                continue
            mode = "w" if first else "a"
            if suffix == ".jsonl":
                chunk.to_json(out_path, orient="records", lines=True, mode=mode, force_ascii=False)
            else:
                chunk.to_csv(out_path, sep=sep, index=False, header=first, mode=mode)
            first = False
        if first:
            empty_df = pd.DataFrame(
                columns=list(empty_columns) if empty_columns is not None else []
            )
            if suffix == ".jsonl":
                out_path.write_text("", encoding="utf-8")
            else:
                empty_df.to_csv(out_path, sep=sep, index=False)
        return out_path

    df = chunks_to_dataframe(chunks, empty_columns=empty_columns)
    if suffix == ".json":
        df.to_json(out_path, orient="records", indent=2, force_ascii=False)
    elif suffix == ".xlsx":
        df.to_excel(out_path, index=False)
    elif suffix == ".parquet":
        df.to_parquet(out_path, index=False)
    return out_path


def load_driverfile(
    driver: str | pathlib.Path,
) -> dict[str, list[tuple[str, dict[str, Any] | None, Any, dict[str, Any]]]]:
    """Load an Excel driver workbook containing ``Location Details`` and ``Checks to Run`` sheets.

    Parameters
    ----------
    driver
        Path to the Excel driver workbook.

    Returns
    -------
    dict[str, list[tuple[str, dict[str, Any] | None, Any, dict[str, Any]]]]
        Mapping of resolved source locator to list of
        ``(check_name, kwargs, severity, reader_args)`` tuples.
    """
    file_info = pd.read_excel(driver, sheet_name="Location Details", header=1)
    checks_df = pd.read_excel(driver, sheet_name="Checks to Run", header=3)

    sources = file_info["Source Name"].astype(str).copy()
    locations = file_info["Location"].fillna("").astype(str)

    def _combine_location(loc: str, src: str) -> str:
        loc_s = loc.strip()
        src_s = src.strip()
        if not loc_s:
            return src_s
        if loc_s.endswith(("/", "\\", "#", "::")):
            return loc_s + src_s
        if "://" in loc_s or "#" in loc_s or "::" in loc_s:
            return loc_s
        return loc_s + src_s

    full_paths = pd.Series(
        [_combine_location(loc, src) for loc, src in zip(locations, sources, strict=True)],
        index=file_info.index,
    )

    dup_mask = sources.duplicated(keep=False)
    if bool(dup_mask.any()):
        logger.error(
            "Duplicate Source Name(s) {} in Location Details; falling back to full paths.",
            sources[dup_mask].unique().tolist(),
        )
        sources.loc[dup_mask] = full_paths.loc[dup_mask]

    to_check: dict[str, list[tuple[str, dict[str, Any] | None, Any, dict[str, Any]]]] = defaultdict(
        list
    )

    for row in checks_df.to_dict("records"):
        if row.get("Process") not in ("Y", "y", "1", 1, True):
            continue

        source_ref = str(row.get("Source Name", ""))
        match_mask = (sources == source_ref) | (full_paths == source_ref)
        if not bool(match_mask.any()):
            logger.error(
                "Skipping check with unknown/ambiguous source: {} {}",
                source_ref,
                row.get("Check"),
            )
            continue

        location = str(full_paths.loc[match_mask].iloc[0])
        reader_series = file_info.loc[match_mask, "Reader Arguments"].dropna()
        if len(reader_series) == 1:
            reader_args = parse_cell_to_dict(reader_series.iloc[0]) or {}
        else:
            if len(reader_series) > 1:
                logger.error("Source {} has duplicate Reader Arguments; ignoring.", source_ref)
            reader_args = {}

        check_name = str(row.get("Check", ""))
        if check_name not in available_checks:
            logger.error("Check '{}' does not exist for {}.", check_name, source_ref)

        default_key: str | None = None
        check_fn = getattr(checkers, check_name, None)
        if callable(check_fn):
            params = list(inspect.signature(check_fn).parameters)
            if len(params) > 1:
                default_key = params[1]

        kwargs = parse_cell_to_dict(row.get("Keyword Arguments"), default_key=default_key)
        severity = row.get("Severity", "")
        to_check[location].append((check_name, kwargs, severity, reader_args))

    return dict(to_check)


def parse_cell_to_dict(cell: Any, default_key: str | None = None) -> dict[str, Any] | None:
    """Parse flexible Excel cell text (JSON, Python literal, ``key=val``, or scalar) into a dict.

    Parameters
    ----------
    cell
        Cell value read from an Excel driver workbook.
    default_key
        Key name assigned when *cell* holds a single scalar value.

    Returns
    -------
    dict[str, Any] | None
        Parsed keyword arguments dictionary, or ``None`` if empty/unparseable.
    """
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return None

    if isinstance(cell, dict):
        return cell

    if isinstance(cell, str):
        stripped = cell.strip()
        if not stripped:
            return None

        for parser in (json.loads, ast.literal_eval):
            for candidate in (stripped, f"{{{stripped}}}"):
                try:
                    parsed = parser(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue

        if "=" in stripped:
            kv_dict: dict[str, Any] = {}
            for line in stripped.splitlines():
                for part in line.split(","):
                    if "=" in part:
                        raw_k, raw_v = part.split("=", 1)
                        k_str = raw_k.strip()
                        try:
                            key = str(ast.literal_eval(k_str))
                        except Exception:
                            key = k_str
                        sub = parse_cell_to_dict(raw_v.strip(), default_key=key)
                        if sub:
                            kv_dict.update(sub)
            if kv_dict:
                return kv_dict

        if default_key is not None:
            try:
                return {default_key: ast.literal_eval(stripped)}
            except Exception:
                return {default_key: stripped}
        return None

    if default_key is not None:
        return {default_key: cell}
    return None


def pretty_print_results(
    results: CheckeredHistory | Sequence[CheckeredHistory],
    maxlen: int = 40,
) -> str:
    """Format and print check results as an aligned ASCII table.

    Parameters
    ----------
    results
        Results to render.
    maxlen
        Maximum column width before wrapping onto additional lines.

    Returns
    -------
    str
        Rendered table text (also printed to stdout).
    """
    from dataspector.core import CheckeredHistory

    result_list: list[CheckeredHistory] = (
        [results] if isinstance(results, CheckeredHistory) else list(results)
    )
    lines: list[str] = [
        f"Printing results of checks across {len(result_list)} locations",
        "",
    ]

    table: list[tuple[str, ...]] = [("Pass", "Location", "Check", "kwargs", "Notes")]
    for res in result_list:
        loc_display = redact_url(getattr(res.location, "_location", res.location))
        for idx, check in enumerate(res.checklist):
            if isinstance(check, tuple):
                checkname = check[0]
                kwargs: Any = check[1] if len(check) > 1 else {}
                if isinstance(kwargs, dict) and len(kwargs) == 1:
                    kwargs = next(iter(kwargs.values()))
            else:
                checkname = check
                kwargs = {}

            notes_text = " ".join(
                part for part in (res.notes.get(idx), res.exceptions.get(idx)) if part
            )
            row = (
                str(res.results.get(idx)),
                str(loc_display),
                str(checkname),
                str(kwargs),
                notes_text,
            )
            n_wraps = max((len(col) - 1) // maxlen + 1 if col else 1 for col in row)
            for wrap_idx in range(n_wraps):
                sl = slice(wrap_idx * maxlen, (wrap_idx + 1) * maxlen)
                table.append(tuple(col[sl] for col in row))

    widths = [max(len(r[col_i]) for r in table) for col_i in range(len(table[0]))]
    for r_idx, row in enumerate(table):
        parts = [f"{row[0].ljust(widths[0] + 1)}||"]
        for col_i in range(1, len(row)):
            parts.append(f"{row[col_i].rjust(widths[col_i] + 1)} |")
        lines.append("".join(parts))
        if r_idx == 0:
            lines.append("-" * (sum(widths) + 14))

    output = "\n".join(lines)
    print(output)
    return output


def version_adder(fout: str | pathlib.Path, extension: str | None = None) -> str:
    """Return a non-colliding output path, appending ``_v01``, ``_v02``, ... if needed.

    Parameters
    ----------
    fout
        Desired output file path.
    extension
        Optional required file extension (e.g. ``'.xlsx'``).

    Returns
    -------
    str
        Unique output path string.
    """
    path = pathlib.Path(fout)
    if extension is not None:
        ext = f".{extension.lstrip('.')}"
        if path.suffix.lower() != ext.lower():
            logger.info("Appending {} extension to {}", ext, path)
            path = pathlib.Path(f"{path}{ext}")

    candidate = path
    n = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_v{n:02d}{path.suffix}")
        n += 1
    return str(candidate)


def write_excel_report(
    results: CheckeredHistory | Sequence[CheckeredHistory],
    excel_file_name: str | pathlib.Path,
) -> pathlib.Path:
    """Write formatted check results to an Excel workbook with conditional highlighting.

    Parameters
    ----------
    results
        Check results produced by :func:`~dataspector.core.run_checks_on_location` or
        :func:`~dataspector.core.load_and_run_checks`.
    excel_file_name
        Target ``.xlsx`` output path (auto-versioned if it already exists).

    Returns
    -------
    pathlib.Path
        Path to the written Excel report.
    """
    from dataspector.core import CheckeredHistory

    result_list: list[CheckeredHistory] = (
        [results] if isinstance(results, CheckeredHistory) else list(results)
    )
    out_path = pathlib.Path(version_adder(excel_file_name, extension=".xlsx"))

    workbook = xlsxwriter.Workbook(
        str(out_path),
        {"strings_to_formulas": False, "strings_to_urls": False},
    )
    worksheet = workbook.add_worksheet("Results")
    header_row = ["Pass", "Severity", "Location", "Check", "kwargs", "Notes"]
    header = [{"header": col} for col in header_row]

    format_fail = workbook.add_format({"bg_color": "#FF6B6B", "font_color": "#000000"})
    format_warn = workbook.add_format({"bg_color": "#FADA5E", "font_color": "#000000"})
    format_pass = workbook.add_format({"bg_color": "#ADD8E6", "font_color": "#000000"})

    row_idx = 1
    for res in result_list:
        loc_display = redact_url(getattr(res.location, "_location", res.location))
        for idx, check in enumerate(res.checklist):
            if isinstance(check, tuple):
                checkname = check[0]
                kwargs = check[1] if len(check) > 1 else {}
                severity = check[2] if len(check) > 2 else ""
            else:
                checkname = check
                kwargs = {}
                severity = ""

            notes_text = " ".join(
                part for part in (res.notes.get(idx), res.exceptions.get(idx)) if part
            )
            worksheet.write_row(
                row_idx,
                0,
                [
                    str(res.results.get(idx)),
                    str(severity).upper(),
                    str(loc_display),
                    str(checkname),
                    str(kwargs),
                    notes_text,
                ],
            )
            row_idx += 1

    last_row = max(row_idx - 1, 1)
    worksheet.add_table(
        0,
        0,
        last_row,
        len(header_row) - 1,
        {"header_row": True, "first_column": True, "columns": header},
    )
    cell_range = f"A2:F{last_row + 1}"
    worksheet.conditional_format(
        cell_range,
        {"type": "formula", "criteria": '=LEFT($A2, 4)="TRUE"', "format": format_pass},
    )
    worksheet.conditional_format(
        cell_range,
        {
            "type": "formula",
            "criteria": '=AND(LEFT($A2, 5)="FALSE", LEFT($B2, 7)="WARNING")',
            "format": format_warn,
        },
    )
    worksheet.conditional_format(
        cell_range,
        {
            "type": "formula",
            "criteria": '=AND(LEFT($A2, 5)="FALSE", NOT(LEFT($B2, 7)="WARNING"))',
            "format": format_fail,
        },
    )
    worksheet.set_column(0, 1, 12)
    worksheet.set_column(2, 5, 40)
    workbook.close()
    return out_path
