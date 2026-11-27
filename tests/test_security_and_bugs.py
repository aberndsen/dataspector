"""Regression tests for security hardening and reliability fixes."""

from __future__ import annotations

import pathlib
import sqlite3

import openpyxl
import pytest
import xlsxwriter
from assertpy import assert_that

import dataspector
from dataspector._connectors import _escape_odbc_value, quote_odbc_identifier, redact_url
from dataspector.coboller import Copybook
from dataspector.coboller.codecs import expand_pic
from dataspector.core import (
    CheckeredHistory,
    GenericData,
    load_driverfile,
    pretty_print_results,
    run_checks_on_location,
    version_adder,
    write_excel_report,
)


def test_credential_redaction_in_urls_repr_and_reports(tmp_path: pathlib.Path) -> None:
    """Passwords in database URLs are redacted in logs, reprs, terminal output, and Excel reports."""
    secret_url = "postgresql+psycopg://alice:SuperSecret123!@db.internal:5432/prod#public.accounts"

    redacted = redact_url(secret_url)
    assert_that(redacted).does_not_contain("SuperSecret123!")
    assert_that(redacted).contains("alice:").contains("@db.internal:5432/prod#public.accounts")

    gd = GenericData(secret_url)
    assert_that(repr(gd)).does_not_contain("SuperSecret123!")

    hist = CheckeredHistory(secret_url, [("source_exists", {})])
    assert_that(repr(hist)).does_not_contain("SuperSecret123!")
    hist.results[0] = False

    rendered = pretty_print_results(hist)
    assert_that(rendered).does_not_contain("SuperSecret123!")

    report_path = write_excel_report(hist, tmp_path / "redacted_report.xlsx")
    wb = openpyxl.load_workbook(report_path)
    loc_cell = str(wb["Results"]["C2"].value)
    assert_that(loc_cell).does_not_contain("SuperSecret123!")


def test_odbc_identifier_and_value_escaping() -> None:
    """ODBC table identifiers and connection string parameters resist injection."""
    assert_that(quote_odbc_identifier("Users")).is_equal_to("[Users]")
    assert_that(quote_odbc_identifier("bad]name;DROP TABLE x;--")).is_equal_to(
        "[bad]]name;DROP TABLE x;--]"
    )
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        quote_odbc_identifier("")
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        quote_odbc_identifier("bad\x00table")

    assert_that(_escape_odbc_value("plain_db")).is_equal_to("plain_db")
    assert_that(_escape_odbc_value("db;Trusted_Connection=yes")).is_equal_to(
        "{db;Trusted_Connection=yes}"
    )
    assert_that(_escape_odbc_value("a}b")).is_equal_to("{a}}b}")
    with pytest.raises(ValueError, match="control character"):
        _escape_odbc_value("bad\nval")


def test_excel_report_disables_formula_injection(tmp_path: pathlib.Path) -> None:
    """Untrusted cell values starting with '=' are written as plain strings, not Excel formulas."""
    csv_file = tmp_path / "untrusted.csv"
    csv_file.write_text("status\n\"=CMD|' /C calc'!A0\"\n", encoding="utf-8")

    hist = run_checks_on_location(
        csv_file,
        [("record_field_contains_only", {"field": "status", "values": ["OK"]})],
    )
    assert_that(hist.all_passed).is_false()

    report_path = write_excel_report(hist, tmp_path / "formula_safe.xlsx")
    wb = openpyxl.load_workbook(report_path, data_only=False)
    ws = wb["Results"]
    # Even if a value starts with '=', xlsxwriter stores it as a string ('s'), not a formula ('f')
    note_cell = ws["F2"]
    assert_that(note_cell.data_type).is_equal_to("s")


def test_checkered_history_enforces_available_checks_allowlist(sample_csv: pathlib.Path) -> None:
    """Non-check attributes on dataspector.checkers (e.g. CheckOutcome) are rejected."""
    hist = run_checks_on_location(
        sample_csv,
        [("CheckOutcome", {}), ("requires_all_data", {})],
    )
    assert_that(hist.all_passed).is_false()
    assert_that(hist.results[0]).is_false()
    assert_that(hist.exceptions[0]).contains("not recognized")
    assert_that(hist.results[1]).is_false()
    assert_that(hist.exceptions[1]).contains("not recognized")


def test_empty_sql_table_exists_and_exposes_columns(tmp_path: pathlib.Path) -> None:
    """Empty SQLAlchemy tables report exists=True and return schema columns without SELECT *."""
    db_path = tmp_path / "empty_test.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE empty_tbl (id INTEGER PRIMARY KEY, name TEXT, amount REAL)")
    conn.commit()
    conn.close()

    with GenericData(f"sqlite:///{db_path}#empty_tbl") as gd:
        assert_that(gd.exists).is_true()
        assert_that(gd.columns).is_equal_to(["id", "name", "amount"])
        assert_that(gd.number_of_records).is_equal_to(0)

    with GenericData(f"sqlite:///{db_path}#missing_tbl") as gd_missing:
        assert_that(gd_missing.exists).is_false()
        assert_that(gd_missing.columns).is_none()


def test_load_driverfile_preserves_complete_uris_with_friendly_source_names(
    sample_sqlite: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    """Complete URIs in Location Details are not corrupted by appending friendly Source Names."""
    drv = tmp_path / "uri_driver.xlsx"
    wb = xlsxwriter.Workbook(str(drv))
    ws_loc = wb.add_worksheet("Location Details")
    ws_loc.write_row(1, 0, ["Location", "Source Name", "Reader Arguments"])
    ws_loc.write_row(2, 0, [f"sqlite:///{sample_sqlite}#Table1", "Friendly SQLite Alias", ""])
    ws_chk = wb.add_worksheet("Checks to Run")
    ws_chk.write_row(3, 0, ["Process", "Source Name", "Check", "Keyword Arguments", "Severity"])
    ws_chk.write_row(4, 0, ["Y", "Friendly SQLite Alias", "source_exists", "", "Error"])
    wb.close()

    loaded = load_driverfile(drv)
    expected_uri = f"sqlite:///{sample_sqlite}#Table1"
    assert_that(loaded).contains_key(expected_uri)
    results = dataspector.load_and_run_checks(drv)
    assert_that(results).is_length(1)
    assert_that(results[0].all_passed).is_true()


def test_version_adder_preserves_dotted_filenames(tmp_path: pathlib.Path) -> None:
    """version_adder appends .xlsx instead of stripping dotted segments like .11."""
    dotted = tmp_path / "audit_2026.11"
    result = pathlib.Path(version_adder(dotted, extension=".xlsx"))
    assert_that(result.name).is_equal_to("audit_2026.11.xlsx")


def test_cobol_dos_bounds_and_comp3_trailing_0x0d(tmp_path: pathlib.Path) -> None:
    """COBOL parser caps absurd PIC repeats / OCCURS and preserves trailing 0x0D COMP-3 bytes."""
    with pytest.raises(ValueError, match="exceeds maximum allowed"):
        expand_pic("X(999999999)")

    huge_occurs = "       01 REC.\n          05 X-ITEM PIC X OCCURS 200000 TIMES.\n"
    cbl_huge = Copybook.from_string(huge_occurs)
    with pytest.raises(ValueError, match="exceeds maximum allowed"):
        cbl_huge.layout()

    # Record ending with COMP-3 negative zero (0x00 0x0D) followed by LF (0x0A)
    cbl = Copybook.from_string(
        "       01 REC.\n          05 CODE PIC XX.\n          05 AMT PIC S9(3) COMP-3.\n"
    )
    dat = tmp_path / "comp3_0d.dat"
    dat.write_bytes(b"AB\x00\x0d\nCD\x01\x2c\n")
    df = cbl.to_dataframe(dat, encoding="ascii", line_ending="lf")
    assert_that(len(df)).is_equal_to(2)
    assert_that(df["AMT"].tolist()).is_equal_to([0, 12])
