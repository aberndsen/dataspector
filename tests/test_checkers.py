"""Unit and integration tests for :mod:`dataspector.checkers`."""

from __future__ import annotations

import datetime
import json
import pathlib

import pandas as pd
import pandera.pandas as pa
from assertpy import assert_that

import dataspector
from dataspector import checkers


def test_source_exists(sample_csv: pathlib.Path, data_dir: pathlib.Path) -> None:
    """source_exists passes for existing files and fails for missing files."""
    ok = dataspector.run_checks_on_location(sample_csv, [("source_exists", {})])
    missing = dataspector.run_checks_on_location(
        data_dir / "nonexistent_file.csv", [("source_exists", {})]
    )
    assert_that(ok.results[0]).is_true()
    assert_that(missing.results[0]).is_false()


def test_source_fuzzy_find(
    data_dir: pathlib.Path,
    sample_excel: pathlib.Path,
    sample_csv: pathlib.Path,
) -> None:
    """source_fuzzy_find locates files in directories, sheets in Excel, and rejects CSV."""
    found = dataspector.run_checks_on_location(
        data_dir, [("source_fuzzy_find", {"pattern": "*.csv"})]
    )
    not_found = dataspector.run_checks_on_location(
        data_dir, [("source_fuzzy_find", {"pattern": "*nonexistent*"})]
    )
    na_csv = dataspector.run_checks_on_location(
        sample_csv, [("source_fuzzy_find", {"pattern": "*"})]
    )
    excel_found = dataspector.run_checks_on_location(
        f"[{sample_excel}][Sheet1]", [("source_fuzzy_find", {"pattern": "sheet"})]
    )

    assert_that(found.results[0]).is_true()
    assert_that(not_found.results[0]).is_false()
    assert_that(na_csv.results[0]).is_false()
    assert_that(excel_found.results[0]).is_true()


def test_source_has_n_fields(sample_csv: pathlib.Path) -> None:
    """source_has_N_fields checks exact column counts."""
    ok = dataspector.run_checks_on_location(sample_csv, [("source_has_N_fields", {"n_fields": 5})])
    bad = dataspector.run_checks_on_location(sample_csv, [("source_has_N_fields", {"n_fields": 4})])
    assert_that(ok.results[0]).is_true()
    assert_that(bad.results[0]).is_false()
    note = bad.notes[0]
    assert note is not None
    assert_that(note).contains("5 fields")


def test_source_modified_recently_and_on_date(tmp_path: pathlib.Path) -> None:
    """source_modified_recently and source_modified_on_date evaluate file mtime accurately."""
    f = tmp_path / "fresh.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    now = datetime.datetime.now(datetime.UTC)

    recent = dataspector.run_checks_on_location(f, [("source_modified_recently", {"days_ago": 1})])
    stale = dataspector.run_checks_on_location(f, [("source_modified_recently", {"days_ago": -1})])
    on_date = dataspector.run_checks_on_location(
        f, [("source_modified_on_date", {"date": now.isoformat(), "tolerance": "1h"})]
    )
    wrong_date = dataspector.run_checks_on_location(
        f, [("source_modified_on_date", {"date": "1990-01-01", "tolerance": "1h"})]
    )
    bad_date = dataspector.run_checks_on_location(
        f, [("source_modified_on_date", {"date": "not-a-date", "tolerance": "1h"})]
    )
    bad_tol = dataspector.run_checks_on_location(
        f, [("source_modified_on_date", {"date": "2025-01-01", "tolerance": "5monkeys"})]
    )

    assert_that(recent.results[0]).is_true()
    assert_that(stale.results[0]).is_false()
    assert_that(on_date.results[0]).is_true()
    assert_that(wrong_date.results[0]).is_false()
    assert_that(bad_date.results[0]).is_false()
    assert_that(bad_tol.results[0]).is_false()


def test_source_storage_size_roughly(sample_csv: pathlib.Path) -> None:
    """source_storage_size_roughly checks file byte size within tolerance."""
    actual = sample_csv.stat().st_size
    ok = dataspector.run_checks_on_location(
        sample_csv, [("source_storage_size_roughly", {"rough_size": actual})]
    )
    bad = dataspector.run_checks_on_location(
        sample_csv, [("source_storage_size_roughly", {"rough_size": 100000})]
    )
    assert_that(ok.results[0]).is_true()
    assert_that(bad.results[0]).is_false()


def test_source_source_comparisons(
    sample_csv: pathlib.Path,
    sample_csv0: pathlib.Path,
    sample_csv1: pathlib.Path,
    sample_excel: pathlib.Path,
) -> None:
    """Cross-source checks compare fields, byte sizes, identity, and record counts."""
    same_fields = dataspector.run_checks_on_location(
        sample_csv, [("source_source_same_fields", {"source2": sample_csv0})]
    )
    diff_fields = dataspector.run_checks_on_location(
        sample_csv, [("source_source_same_fields", {"source2": sample_excel})]
    )
    assert_that(same_fields.results[0]).is_true()
    assert_that(diff_fields.results[0]).is_false()

    same_size = dataspector.run_checks_on_location(
        sample_csv,
        [("source_source_size_roughly_same", {"source2": sample_csv1, "tolerance": 0.2})],
    )
    diff_size = dataspector.run_checks_on_location(
        sample_csv,
        [("source_source_size_roughly_same", {"source2": sample_excel, "tolerance": 0.01})],
    )
    assert_that(same_size.results[0]).is_true()
    assert_that(diff_size.results[0]).is_false()

    identical_yes = dataspector.run_checks_on_location(
        sample_csv, [("source_source_identical", {"source2": sample_csv, "shallow": False})]
    )
    identical_no = dataspector.run_checks_on_location(
        sample_csv, [("source_source_identical", {"source2": sample_csv0, "shallow": False})]
    )
    assert_that(identical_yes.results[0]).is_true()
    assert_that(identical_no.results[0]).is_false()

    same_rows = dataspector.run_checks_on_location(
        sample_csv, [("source_source_roughly_same_number_of_records", {"source2": sample_csv0})]
    )
    diff_rows = dataspector.run_checks_on_location(
        sample_csv,
        [
            (
                "source_source_roughly_same_number_of_records",
                {"source2": sample_excel, "tolerance": 0.01},
            )
        ],
    )
    assert_that(same_rows.results[0]).is_true()
    assert_that(diff_rows.results[0]).is_false()


def test_record_column_and_value_checks(
    sample_csv: pathlib.Path, sample_csv1: pathlib.Path
) -> None:
    """record_contains, record_contains_at_least, record_field_contains*, and conditional checks."""
    cols = ["Report Date", "Expense Division", "Cost Center", "Component", "Cost [CAD]"]
    res = dataspector.run_checks_on_location(
        sample_csv,
        [
            ("record_contains", {"field": "Cost Center"}),
            ("record_contains", {"field": "MissingCol"}),
            ("record_contains_at_least", {"fields": cols}),
            ("record_contains_at_least", {"fields": [*cols, "MissingCol"]}),
            ("record_field_contains", {"field": "Cost Center", "value": "7517 - 161 Actuarial"}),
            ("record_field_contains", {"field": "Cost Center", "value": "NoSuchValue"}),
            ("record_field_contains", {"field": "MissingCol", "value": "x"}),
            (
                "record_field_contains_at_least",
                {"field": "Cost Center", "values": ["7517 - 161 Actuarial"]},
            ),
            ("record_field_contains_at_least", {"field": "Cost Center", "values": ["NoSuchValue"]}),
            (
                "record_field_contains_only",
                {
                    "field": "Expense Division",
                    "values": ["Asia", "Canadian", "Group", "Investments", "US"],
                },
            ),
            ("record_field_contains_only", {"field": "Cost Center", "values": ["OnlyThis"]}),
            ("record_field_contains_only", {"field": "MissingCol", "values": ["x"]}),
        ],
    )
    assert_that(res.results).is_equal_to(
        {
            0: True,
            1: False,
            2: True,
            3: False,
            4: True,
            5: False,
            6: False,
            7: True,
            8: False,
            9: True,
            10: False,
            11: False,
        }
    )

    cond = dataspector.run_checks_on_location(
        sample_csv1,
        [
            (
                "record_if_field1_startswith_field2_contains_only",
                {"field1": "Cost Center", "value1": "7517", "field2": "CC code", "value2": 7517},
            ),
            (
                "record_if_field1_startswith_field2_contains_only",
                {"field1": "Cost Center", "value1": "7517", "field2": "CC code", "value2": 9999},
            ),
            (
                "record_if_field1_startswith_field2_contains_only",
                {"field1": "Missing", "value1": "7517", "field2": "CC code", "value2": 7517},
            ),
        ],
    )
    assert_that(cond.results).is_equal_to({0: True, 1: False, 2: False})


def test_record_uniqueness_nulls_counts_and_numeric(
    sample_csv: pathlib.Path,
    sample_excel: pathlib.Path,
    sample_fwf: pathlib.Path,
) -> None:
    """Test uniqueness, null checks, row counts, and numeric dtype checks."""
    dup = dataspector.run_checks_on_location(
        sample_csv, [("record_field_is_unique", {"field": "Component"})]
    )
    uniq = dataspector.run_checks_on_location(
        sample_excel, [("record_field_is_unique", {"field": "host"})]
    )
    assert_that(dup.results[0]).is_false()
    assert_that(uniq.results[0]).is_true()

    # Cross-chunk uniqueness detection
    df1 = pd.DataFrame({"id": [1, 2, 3]})
    df2 = pd.DataFrame({"id": [4, 2, 5]})
    o1 = checkers.record_field_is_unique(df1, "id", _last_chunk=False)
    assert_that(o1.passed).is_none()
    o2 = checkers.record_field_is_unique(df2, **o1.kwargs, _last_chunk=True)
    assert_that(o2.passed).is_false()
    assert o2.notes is not None
    assert_that(o2.notes).contains("2")

    null_checks = dataspector.run_checks_on_location(
        sample_csv,
        [
            ("record_field_not_null", {"field": "Cost Center"}),
            ("record_field_not_null", {"field": "Cost [CAD]"}),
            ("record_all_data_not_null", {}),
            ("record_field_is_numeric", {"field": "Cost [CAD]"}),
            ("record_field_is_numeric", {"field": "Cost Center"}),
            ("record_count", {"nrows": 31}),
            ("record_count", {"nrows": 42}),
            ("record_count_greater_than", {"nrows": 30}),
            ("record_count_greater_than", {"nrows": 32}),
        ],
    )
    assert_that(null_checks.results).is_equal_to(
        {
            0: True,
            1: False,
            2: False,
            3: True,
            4: False,
            5: True,
            6: False,
            7: True,
            8: False,
        }
    )

    fwf_no_null = dataspector.run_checks_on_location(
        sample_fwf, [("record_all_data_not_null", {}, "Error", {"widths": [32, 32, 32, 32, 32]})]
    )
    assert_that(fwf_no_null.results[0]).is_true()


def test_record_numeric_and_date_between(sample_csv: pathlib.Path) -> None:
    """Numeric and date range checks handle tuples, strings, inclusive bounds, and errors."""
    res = dataspector.run_checks_on_location(
        sample_csv,
        [
            (
                "record_field_numeric_value_between",
                {"field": "Cost [CAD]", "constraint": (0.1, 146581)},
            ),
            ("record_field_numeric_value_between", {"field": "Cost [CAD]", "constraint": (0.1, 1)}),
            (
                "record_field_numeric_value_between",
                {"field": "Cost [CAD]", "constraint": "(0.1, 146581)"},
            ),
            (
                "record_field_numeric_value_between",
                {"field": "Cost [CAD]", "constraint": ("0.1", "146581")},
            ),
            ("record_field_numeric_value_between", {"field": "Cost [CAD]", "constraint": "bad"}),
            ("record_field_numeric_value_between", {"field": "Missing", "constraint": (0, 10)}),
            (
                "record_field_date_between",
                {"field": "Report Date", "constraint": "[January 2015, 2018-01-01]"},
            ),
            ("record_field_date_between", {"field": "Report Date", "constraint": (1980, 1990)}),
            (
                "record_field_date_between",
                {"field": "Report Date", "constraint": "(Smarch 2017, Flebuary 2019)"},
            ),
            (
                "record_field_date_between",
                {"field": "Report Date", "constraint": (2030, 2525), "include_bounds": True},
            ),
            (
                "record_field_date_between",
                {"field": "Expense Division", "constraint": (2015, 2020), "include_bounds": True},
            ),
            (
                "record_field_date_between",
                {"field": "Missing", "constraint": (2015, 2020), "include_bounds": True},
            ),
        ],
    )
    assert_that(res.results).is_equal_to(
        {
            0: True,
            1: False,
            2: True,
            3: True,
            4: False,
            5: False,
            6: True,
            7: False,
            8: False,
            9: False,
            10: False,
            11: False,
        }
    )


def test_record_validate_schema_with_pandera(
    sample_excel: pathlib.Path,
    sample_cobol_students: str,
    data_dir: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    """record_validate_schema validates via DataFrameSchema, dict, JSON file, and .cbl copybook."""
    # 1. Explicit Pandera DataFrameSchema
    schema = pa.DataFrameSchema(
        {
            "host": pa.Column(str, unique=True, checks=pa.Check.str_startswith("srv-app-")),
            "domain": pa.Column(int, checks=pa.Check.in_range(1, 10)),
        }
    )
    ok = dataspector.run_checks_on_location(
        sample_excel, [("record_validate_schema", {"schema": schema})]
    )
    assert_that(ok.results[0]).is_true()

    # 2. Dict specification (pass and fail)
    dict_ok = dataspector.run_checks_on_location(
        sample_excel,
        [
            (
                "record_validate_schema",
                {
                    "schema": {
                        "host": {"dtype": str, "checks": {"str_startswith": "srv-app-"}},
                        "domain": {"dtype": int, "checks": {"in_range": [1, 10]}},
                    }
                },
            )
        ],
    )
    dict_fail = dataspector.run_checks_on_location(
        sample_excel,
        [
            (
                "record_validate_schema",
                {"schema": {"domain": {"dtype": int, "checks": {"le": 2}}}},
            )
        ],
    )
    assert_that(dict_ok.results[0]).is_true()
    assert_that(dict_fail.results[0]).is_false()
    fail_note = dict_fail.notes[0]
    assert fail_note is not None
    assert_that(fail_note).contains("domain")

    # 3. Direct COBOL copybook path auto-generates Pandera schema
    cbl_ok = dataspector.run_checks_on_location(
        sample_cobol_students,
        [("record_validate_schema", {"schema": data_dir / "sample_cobol_students.cbl"})],
    )
    assert_that(cbl_ok.results[0]).is_true()

    # 4. Inline JSON string & invalid schema handling
    inline_json = json.dumps({"domain": {"dtype": "int64", "checks": {"ge": 1}}})
    json_ok = dataspector.run_checks_on_location(
        sample_excel, [("record_validate_schema", {"schema": inline_json})]
    )
    bad_schema = dataspector.run_checks_on_location(
        sample_excel, [("record_validate_schema", {"schema": "not-valid-json"})]
    )
    assert_that(json_ok.results[0]).is_true()
    assert_that(bad_schema.results[0]).is_false()

    # 5. JSON schema file roundtrip
    schema_file = tmp_path / "excel_schema.json"
    schema.to_json(schema_file)
    file_ok = dataspector.run_checks_on_location(
        sample_excel, [("record_validate_schema", {"schema": schema_file})]
    )
    assert_that(file_ok.results[0]).is_true()


def test_checker_edge_cases_and_multichunk(tmp_path: pathlib.Path) -> None:
    """Cover empty sources, zero-byte files, truncation (>10 bad rows), and chunked streaming."""
    empty_a = tmp_path / "empty_a.csv"
    empty_b = tmp_path / "empty_b.csv"
    empty_a.write_text("x,y\n", encoding="utf-8")
    empty_b.write_text("x,y\n", encoding="utf-8")

    # Zero-record comparison
    same_zero = dataspector.run_checks_on_location(
        empty_a, [("source_source_roughly_same_number_of_records", {"source2": empty_b})]
    )
    assert_that(same_zero.results[0]).is_true()

    # Zero-byte size comparison
    zero_f = tmp_path / "zero.dat"
    zero_f.write_bytes(b"")
    nonzero_f = tmp_path / "nonzero.dat"
    nonzero_f.write_bytes(b"abc")
    res_zero = dataspector.run_checks_on_location(
        zero_f,
        [
            ("source_source_size_roughly_same", {"source2": zero_f}),
            ("source_source_size_roughly_same", {"source2": nonzero_f}),
            ("source_storage_size_roughly", {"rough_size": 0, "tolerance": 0.5}),
        ],
    )
    assert_that(res_zero.results).is_equal_to({0: True, 1: False, 2: True})

    # Large bad-row list triggers >10 line truncation, plus inclusive bounds & both-sides failure
    df_big = pd.DataFrame({"v": list(range(-5, 20)), "k": ["A"] * 25, "t": ["X"] * 25})
    o_between = checkers.record_field_numeric_value_between(
        df_big, "v", (0, 10), include_bounds=True
    )
    assert_that(o_between.passed).is_false()
    assert o_between.notes is not None
    assert_that(o_between.notes).contains("min, max")

    o_only = checkers.record_field_contains_only(df_big, "v", [999])
    assert_that(o_only.passed).is_false()
    assert o_only.notes is not None
    assert_that(o_only.notes).contains("and more")

    o_cond = checkers.record_if_field1_startswith_field2_contains_only(df_big, "k", "A", "t", "Y")
    assert_that(o_cond.passed).is_false()
    assert o_cond.notes is not None
    assert_that(o_cond.notes).contains("and more")

    # Multi-chunk record_field_contains finds value on second chunk
    o_c1 = checkers.record_field_contains(pd.DataFrame({"c": [1, 2]}), "c", 9, _last_chunk=False)
    assert_that(o_c1.passed).is_none()
    o_c2 = checkers.record_field_contains(
        pd.DataFrame({"c": [8, 9]}), **o_c1.kwargs, _last_chunk=True
    )
    assert_that(o_c2.passed).is_true()

    # Default tolerance=0.0 passes on exact match and accepts any Sized chunk
    o_same_1 = checkers.source_source_roughly_same_number_of_records(
        [1, 2], empty_a, _last_chunk=False
    )
    assert_that(o_same_1.passed).is_none()
    o_same_2 = checkers.source_source_roughly_same_number_of_records(
        [], **o_same_1.kwargs, _last_chunk=True
    )
    assert_that(o_same_2.passed).is_false()

    # Non-file source_source_identical returns False cleanly
    o_id = checkers.source_source_identical(
        dataspector.GenericData(tmp_path / "missing1"),
        dataspector.GenericData(("noserver", "nodb", "notable")),
    )
    assert_that(o_id.passed).is_false()

    # Pandera check builder variants (str_length, gt, lt, isin, notin, str_matches, invalid key)
    o_pa = checkers.record_validate_schema(
        pd.DataFrame({"code": ["AB", "CD"], "num": [5, 6]}),
        schema={
            "code": {"dtype": str, "checks": {"str_length": [2, 2], "isin": ["AB", "CD"]}},
            "num": {"dtype": int, "checks": {"gt": 0, "lt": 10}},
        },
    )
    assert_that(o_pa.passed).is_true()

    o_pa_bad = checkers.record_validate_schema(
        pd.DataFrame({"num": [5]}),
        schema={"num": {"dtype": int, "checks": {"unknown_check": 1}}},
    )
    assert_that(o_pa_bad.passed).is_false()
