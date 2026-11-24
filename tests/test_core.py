"""Unit and integration tests for :mod:`dataspector.core`."""

from __future__ import annotations

import datetime
import pathlib

import pandas as pd
import pytest
from assertpy import assert_that

import dataspector
from dataspector.core import (
    CheckeredHistory,
    DataSourceSpec,
    GenericData,
    connect_to_location,
    connect_to_sqlalchemy_url,
    interpolate_env_vars,
    load_and_run_checks,
    load_driverfile,
    parse_cell_to_dict,
    pretty_print_results,
    resolve_location_with_options,
    run_checks_on_location,
    version_adder,
    write_excel_report,
)


def test_generic_data_across_formats(
    sample_csv: pathlib.Path,
    sample_excel: pathlib.Path,
    sample_sqlite: pathlib.Path,
    sample_cobol_students: str,
    sample_cobol_mainframe: str,
    data_dir: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    """GenericData exposes unified properties across CSV, Excel, SQLite, JSON, COBOL, and more."""
    gd_csv = GenericData(sample_csv)
    gd_csv_copy = GenericData(gd_csv)
    assert_that(gd_csv_copy.exists).is_true()
    assert_that(gd_csv_copy.columns).is_equal_to(gd_csv_copy.fields).is_length(5)
    assert_that(gd_csv_copy.determine_delimiter()).is_equal_to(",")
    assert_that(gd_csv_copy.determine_delimeter()).is_equal_to(",")
    assert_that(gd_csv_copy.list_of_tables).is_none()
    assert_that(gd_csv_copy.number_of_records).is_equal_to(31)
    assert_that(gd_csv_copy.number_of_records).is_equal_to(31)  # cached
    assert_that(gd_csv_copy.last_modified).is_instance_of(datetime.datetime)
    assert_that(str(gd_csv_copy)).contains("GenericData")

    gd_sql = GenericData(f"[{sample_sqlite}][Table1]")
    assert_that(gd_sql.exists).is_true()
    sql_cols = gd_sql.columns
    sql_tables = gd_sql.list_of_tables
    assert sql_cols is not None and sql_tables is not None
    assert_that(sql_cols).is_not_empty()
    assert_that(sql_tables).contains("Table1")
    assert_that(gd_sql.number_of_records).is_equal_to(2)

    gd_excel = GenericData(f"[{sample_excel}][Sheet1]")
    assert_that(gd_excel.exists).is_true()
    excel_tables = gd_excel.list_of_tables
    excel_sheet_matches = gd_excel.fuzzy_find("sheet")
    excel_missing_matches = gd_excel.fuzzy_find("missing")
    assert excel_tables is not None
    assert excel_sheet_matches is not None
    assert excel_missing_matches is not None
    assert_that(excel_tables).contains("Sheet1")
    assert_that(excel_sheet_matches).contains("Sheet1")
    assert_that(excel_missing_matches).is_empty()
    assert_that(gd_excel.number_of_records).is_equal_to(18)

    gd_cbl = GenericData(sample_cobol_students)
    assert_that(gd_cbl.exists).is_true()
    assert_that(gd_cbl.columns).is_length(8)
    assert_that(gd_cbl.number_of_records).is_equal_to(32)
    assert_that(gd_cbl.last_modified).is_instance_of(datetime.datetime)
    assert_that(gd_cbl.storage_size_roughly(1024, tolerance=0.2)).is_true()

    gd_mf = GenericData(sample_cobol_mainframe, reader_options={"encoding": "cp500"})
    assert_that(gd_mf.exists).is_true()
    assert_that(gd_mf.number_of_records).is_equal_to(4)

    # JSON & JSONL & pipe-delimited & unknown file extension fallback
    jsonl = tmp_path / "records.jsonl"
    jsonl.write_text('{"a": 1, "b": "x"}\n{"a": 2, "b": "y"}\n', encoding="utf-8")
    gd_jsonl = GenericData(jsonl)
    assert_that(gd_jsonl.number_of_records).is_equal_to(2)
    assert_that(gd_jsonl.columns).is_equal_to(["a", "b"])

    pipe_txt = tmp_path / "pipe.txt"
    pipe_txt.write_text("col1|col2\n1|2\n3|4\n", encoding="utf-8")
    gd_pipe = GenericData(pipe_txt)
    assert_that(gd_pipe.determine_delimiter()).is_equal_to("|")
    assert_that(gd_pipe.number_of_records).is_equal_to(2)

    raw_unknown = tmp_path / "notes.log"
    raw_unknown.write_text("line1\nline2\n", encoding="utf-8")
    gd_raw = GenericData(raw_unknown)
    assert_that(list(gd_raw.yield_data())).is_length(2)

    # Missing file
    gd_missing = GenericData(data_dir / "does_not_exist.csv")
    assert_that(gd_missing.exists).is_false()
    assert_that(gd_missing.last_modified).is_none()
    assert_that(gd_missing.is_modified_recently(1)).is_none()


def test_connect_to_location_variants(
    sample_sqlite: pathlib.Path,
    data_dir: pathlib.Path,
) -> None:
    """connect_to_location resolves tuples, bracketed strings, and Windows-style paths."""
    p, e, t = connect_to_location((sample_sqlite, "Table1"))
    assert_that(p).is_equal_to(sample_sqlite)
    assert_that(str(e)).contains("sqlite")
    assert_that(t).is_equal_to("Table1")

    # COBOL tuple
    cbl, dat, tbl = connect_to_location(
        (data_dir / "sample_cobol_students.cbl", data_dir / "sample_cobol_students.dat")
    )
    assert_that(cbl).is_instance_of(dataspector.coboller.CopyBook)
    assert_that(dat).is_equal_to(data_dir / "sample_cobol_students.dat")
    assert_that(tbl).is_none()

    # Windows backslash normalization on POSIX
    win_path = r"tests\data\sample_csv.csv"
    resolved_p, _, _ = connect_to_location(win_path)
    assert_that(isinstance(resolved_p, pathlib.Path) and resolved_p.exists()).is_true()


def test_parse_cell_to_dict_variants() -> None:
    """parse_cell_to_dict parses JSON, brace-less pairs, literals, key=val, and scalars."""
    assert_that(parse_cell_to_dict('{"a": 1, "b": "x"}')).is_equal_to({"a": 1, "b": "x"})
    assert_that(parse_cell_to_dict('"widths": [10, 20]')).is_equal_to({"widths": [10, 20]})
    assert_that(parse_cell_to_dict("{'field': 'Cost'}")).is_equal_to({"field": "Cost"})
    assert_that(parse_cell_to_dict("field='Cost', value=42")).is_equal_to(
        {"field": "Cost", "value": 42}
    )
    assert_that(parse_cell_to_dict("5", default_key="n_fields")).is_equal_to({"n_fields": 5})
    assert_that(parse_cell_to_dict(5, default_key="n_fields")).is_equal_to({"n_fields": 5})
    assert_that(parse_cell_to_dict("Report Date", default_key="field")).is_equal_to(
        {"field": "Report Date"}
    )
    assert_that(parse_cell_to_dict(None)).is_none()
    assert_that(parse_cell_to_dict(float("nan"))).is_none()
    assert_that(parse_cell_to_dict("")).is_none()


def test_checkered_history_exceptions_and_repr(sample_csv: pathlib.Path) -> None:
    """Unknown checks and runtime check errors are captured cleanly in CheckeredHistory."""
    hist = run_checks_on_location(
        sample_csv,
        [
            "source_exists",
            ("source_nonexistent_check", {"pattern": "x"}),
        ],
    )
    assert_that(str(hist)).contains("CheckeredHistory")
    assert_that(hist.results[0]).is_true()
    assert_that(hist.results[1]).is_false()
    assert_that(hist.exceptions[1]).contains("not recognized")
    assert_that(hist.all_passed).is_false()

    # String comma-separated checklist
    hist_str = CheckeredHistory(sample_csv, "source_exists")
    hist_str.apply_source_level_checks()
    assert_that(hist_str.all_passed).is_true()


def test_load_driverfile_and_excel_report(
    sample_driver: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    """Driver workbook loads, runs (sequential & multiprocessing), prints, and writes Excel report."""
    loaded = load_driverfile(sample_driver)
    assert_that(loaded).is_instance_of(dict)
    assert_that(loaded).contains_key("tests/data/sample_csv.csv", "tests/data/sample_excel.xlsx")

    for use_mp in (False, True):
        results = load_and_run_checks(sample_driver, use_multiprocessing=use_mp)
        assert_that(results).is_length(5)
        for res in results:
            assert_that(res.all_passed).is_true()

        out_file = tmp_path / f"report_mp_{use_mp}.xlsx"
        written = write_excel_report(results, out_file)
        assert_that(written.exists()).is_true()

        df = pd.read_excel(written)
        assert_that(list(df.columns)).is_equal_to(
            ["Pass", "Severity", "Location", "Check", "kwargs", "Notes"]
        )
        assert_that(df).is_length(18)

        # Calling write_excel_report again auto-versions without overwriting
        written_v2 = write_excel_report(results[0], out_file)
        assert_that(written_v2.name).contains("_v01")

    rendered = pretty_print_results(results)
    assert_that(rendered).contains("Pass").contains("source_exists")


def test_version_adder(tmp_path: pathlib.Path) -> None:
    """version_adder enforces extensions and avoids overwriting existing files."""
    base = tmp_path / "output"
    first = pathlib.Path(version_adder(base, extension=".xlsx"))
    assert_that(first.name).is_equal_to("output.xlsx")
    first.write_text("dummy", encoding="utf-8")

    second = pathlib.Path(version_adder(first, extension=".xlsx"))
    assert_that(second.name).is_equal_to("output_v01.xlsx")


def test_core_edge_cases_and_cobol_only_source(
    data_dir: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    """Cover COBOL layout-only source, duplicate driver source names, and single-element tuple."""
    cbl_only = GenericData(data_dir / "sample_cobol_students.cbl")
    assert_that(cbl_only.exists).is_true()
    assert_that(cbl_only.last_modified).is_instance_of(datetime.datetime)
    try:
        cbl_only.storage_size_roughly(100)
        raise AssertionError("Expected ValueError for layout-only COBOL storage_size_roughly")
    except ValueError:
        pass

    # Single-element tuple in connect_to_location
    p, e, t = connect_to_location((data_dir / "sample_csv.csv",))
    assert_that(p).is_equal_to(data_dir / "sample_csv.csv")
    assert_that(e).is_none()
    assert_that(t).is_none()

    # Driver with duplicate source names, disabled row, and unknown source
    import xlsxwriter

    drv = tmp_path / "edge_driver.xlsx"
    wb = xlsxwriter.Workbook(str(drv))
    ws_loc = wb.add_worksheet("Location Details")
    ws_loc.write_row(1, 0, ["Location", "Source Name", "Reader Arguments"])
    ws_loc.write_row(2, 0, [str(data_dir) + "/", "sample_csv.csv", ""])
    ws_loc.write_row(3, 0, [str(tmp_path) + "/", "sample_csv.csv", ""])
    ws_chk = wb.add_worksheet("Checks to Run")
    ws_chk.write_row(3, 0, ["Process", "Source Name", "Check", "Keyword Arguments", "Severity"])
    ws_chk.write_row(4, 0, ["N", "sample_csv.csv", "source_exists", "", "Error"])
    ws_chk.write_row(5, 0, ["Y", "unknown_source.csv", "source_exists", "", "Error"])
    ws_chk.write_row(6, 0, ["Y", str(data_dir) + "/sample_csv.csv", "source_exists", "", "Error"])
    wb.close()

    loaded = load_driverfile(drv)
    assert_that(loaded).is_length(1)
    assert_that(loaded).contains_key(str(data_dir) + "/sample_csv.csv")


def test_generic_data_to_dataframe_and_convert(
    sample_csv: pathlib.Path,
    sample_sqlite: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    """GenericData.to_dataframe and convert align with Copybook across data sources."""
    gd_csv = GenericData(sample_csv)
    df_preview = gd_csv.to_dataframe(nrows=5, chunksize=2)
    assert_that(df_preview).is_length(5)
    assert_that(list(df_preview.columns)).is_equal_to(gd_csv.columns)

    df_all = gd_csv.to_dataframe(chunksize=10)
    assert_that(df_all).is_length(31)

    jsonl_out = gd_csv.convert(tmp_path / "csv_export.jsonl", chunksize=10)
    assert_that(pd.read_json(jsonl_out, lines=True)).is_length(31)

    gd_sql = GenericData(f"[{sample_sqlite}][Table1]")
    csv_out = gd_sql.convert(tmp_path / "sql_export.csv")
    assert_that(pd.read_csv(csv_out)).is_length(2)


def test_unified_locator_syntax_across_files_cobol_and_databases(
    sample_csv: pathlib.Path,
    sample_excel: pathlib.Path,
    sample_sqlite: pathlib.Path,
    data_dir: pathlib.Path,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unified URI schemes, #fragments, cobol://::, SQLAlchemy URLs, and DataSourceSpec work seamlessly."""
    # 1. Explicit file format scheme on a non-standard extension (.dat containing CSV)
    disguised_csv = tmp_path / "daily_drop.dat"
    disguised_csv.write_text(sample_csv.read_text(encoding="utf-8"), encoding="utf-8")
    gd_csv_uri = GenericData(f"csv://{disguised_csv}")
    assert_that(gd_csv_uri.exists).is_true()
    assert_that(gd_csv_uri.number_of_records).is_equal_to(31)
    assert_that(gd_csv_uri.columns).is_length(5)

    # 2. TSV and fixed-width (fwf://) schemes with inline query options
    tsv_file = tmp_path / "export.out"
    tsv_file.write_text("col_a\tcol_b\n10\t20\n30\t40\n", encoding="utf-8")
    gd_tsv = GenericData(f"tsv://{tsv_file}")
    assert_that(gd_tsv.number_of_records).is_equal_to(2)
    assert_that(gd_tsv.columns).is_equal_to(["col_a", "col_b"])

    fwf_file = tmp_path / "fixed.bin"
    fwf_file.write_text("ID  NAME  \n0001ALICE \n0002BOB   \n", encoding="utf-8")
    gd_fwf = GenericData(f"fwf://{fwf_file}?widths=[4,6]")
    assert_that(gd_fwf.number_of_records).is_equal_to(2)
    assert_that(gd_fwf.columns).is_equal_to(["ID", "NAME"])

    # 3. Excel scheme + #Sheet fragment (and plain path#Sheet fragment)
    gd_excel_uri = GenericData(f"excel://{sample_excel}#Sheet1")
    assert_that(gd_excel_uri.exists).is_true()
    assert_that(gd_excel_uri.number_of_records).is_equal_to(18)

    gd_excel_frag = GenericData(f"{sample_excel}#Sheet1")
    assert_that(gd_excel_frag.exists).is_true()
    assert_that(gd_excel_frag.number_of_records).is_equal_to(18)

    # 4. COBOL scheme: cobol://layout::data and cobol://layout?data=...&encoding=cp500
    # Even when the copybook file has a non-standard .txt extension!
    txt_copybook = tmp_path / "mainframe_layout.txt"
    txt_copybook.write_text(
        (data_dir / "sample_cobol_mainframe.cbl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    mf_data = data_dir / "sample_cobol_mainframe.dat"

    gd_cobol_double_colon = GenericData(
        f"cobol://{txt_copybook}::{mf_data}?encoding=cp500&include_filler=false"
    )
    assert_that(gd_cobol_double_colon.exists).is_true()
    assert_that(gd_cobol_double_colon.number_of_records).is_equal_to(4)

    gd_cobol_query = GenericData(f"cobol://{txt_copybook}?data={mf_data}&encoding=cp500")
    assert_that(gd_cobol_query.exists).is_true()
    assert_that(gd_cobol_query.number_of_records).is_equal_to(4)

    # 5. Unified Database URLs: sqlite:///path#Table1, sqlite://path?table=Table1, and env var interpolation
    monkeypatch.setenv("TEST_SQLITE_PATH", str(sample_sqlite))
    gd_sqlite_uri = GenericData("sqlite:///${TEST_SQLITE_PATH}#Table1")
    assert_that(gd_sqlite_uri.exists).is_true()
    assert_that(gd_sqlite_uri.number_of_records).is_equal_to(2)
    sqlite_cols = gd_sqlite_uri.columns
    assert sqlite_cols is not None
    assert_that(sqlite_cols).is_not_empty()

    gd_sqlite_q = GenericData(f"sqlite3://{sample_sqlite}?table=Table1")
    assert_that(gd_sqlite_q.exists).is_true()
    assert_that(gd_sqlite_q.number_of_records).is_equal_to(2)

    # 6. Structured DataSourceSpec & dict locators (for files, COBOL, and databases)
    spec_cobol = DataSourceSpec(
        uri=txt_copybook,
        format="cobol",
        data=mf_data,
        options={"encoding": "cp500"},
    )
    gd_spec_cobol = GenericData(spec_cobol)
    assert_that(gd_spec_cobol.exists).is_true()
    assert_that(gd_spec_cobol.number_of_records).is_equal_to(4)

    gd_dict_db = GenericData(
        {
            "format": "sqlite",
            "uri": f"sqlite:///{sample_sqlite}",
            "table": "Table1",
        }
    )
    assert_that(gd_dict_db.exists).is_true()
    assert_that(gd_dict_db.number_of_records).is_equal_to(2)

    gd_spec_csv = GenericData(DataSourceSpec(uri=disguised_csv, format="csv"))
    assert_that(gd_spec_csv.number_of_records).is_equal_to(31)

    # 7. Helper coverage for scheme normalization & edge cases
    assert_that(interpolate_env_vars("plain_string")).is_equal_to("plain_string")
    assert_that(connect_to_sqlalchemy_url("not_a_url")).is_none()
    _, _pg_eng, pg_tbl, _ = resolve_location_with_options(
        "postgres://user:pass@localhost:5432/mydb#public.users"
    )
    assert_that(pg_tbl).is_equal_to("public.users")
