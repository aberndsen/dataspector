"""Tests for :mod:`dataspector.cli`, :mod:`dataspector.settings`, and ``python -m dataspector``."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pandas as pd
import pytest
import xlsxwriter
from assertpy import assert_that

from dataspector.cli import (
    coboller_main,
    main,
    run_dataspector,
)
from dataspector.settings import (
    CobollerConvertSettings,
    CobollerInspectSettings,
    DataSpectorSettings,
)


def test_settings_dataclasses(sample_driver: pathlib.Path, data_dir: pathlib.Path) -> None:
    """Settings dataclasses store clean typed defaults and values."""
    ds = DataSpectorSettings(driver=sample_driver, overwrite=True, log_level="DEBUG")
    assert_that(ds.driver).is_equal_to(sample_driver)
    assert_that(ds.overwrite).is_true()
    assert_that(ds.log_level).is_equal_to("DEBUG")

    ins = CobollerInspectSettings(
        copybook=data_dir / "sample_cobol_mainframe.cbl", omit_filler=True
    )
    assert_that(ins.omit_filler).is_true()

    conv = CobollerConvertSettings(
        copybook=data_dir / "sample_cobol_mainframe.cbl",
        datafile=data_dir / "sample_cobol_mainframe.dat",
        encoding="cp500",
    )
    assert_that(conv.encoding).is_equal_to("cp500")
    assert_that(conv.float_format).is_equal_to("ieee")


def test_cli_main_success_and_output_report(
    sample_driver: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    """main() returns 0 for passing driver and writes report with --overwrite true support."""
    out = tmp_path / "cli_report.xlsx"
    assert_that(main(["--driver", str(sample_driver), "--output", str(out)])).is_equal_to(0)
    assert_that(out.exists()).is_true()

    # Overwrite mode replaces in place
    assert_that(
        main(["--driver", str(sample_driver), "--output", str(out), "--overwrite", "true"])
    ).is_equal_to(0)
    assert_that(out.exists()).is_true()

    # YAML config file support via jsonargparse
    cfg_file = tmp_path / "run.yaml"
    cfg_file.write_text(
        f"driver: {sample_driver}\nlog_level: WARNING\n",
        encoding="utf-8",
    )
    assert_that(main(["--config", str(cfg_file)])).is_equal_to(0)


def test_cli_main_missing_driver_and_no_args(tmp_path: pathlib.Path) -> None:
    """main() returns 1 when driver is omitted or does not exist."""
    assert_that(main([])).is_equal_to(1)
    assert_that(main(["--driver", str(tmp_path / "missing.xlsx")])).is_equal_to(1)
    assert_that(run_dataspector(DataSpectorSettings())).is_equal_to(1)


def test_cli_main_returns_1_on_failed_check(tmp_path: pathlib.Path) -> None:
    """main() returns 1 when any configured check fails."""
    driver = tmp_path / "failing_driver.xlsx"
    wb = xlsxwriter.Workbook(str(driver))
    ws_loc = wb.add_worksheet("Location Details")
    ws_loc.write_row(1, 0, ["Location", "Source Name", "Reader Arguments"])
    ws_loc.write_row(2, 0, [str(tmp_path) + "/", "does_not_exist.csv", ""])
    ws_chk = wb.add_worksheet("Checks to Run")
    ws_chk.write_row(3, 0, ["Process", "Source Name", "Check", "Keyword Arguments", "Severity"])
    ws_chk.write_row(4, 0, ["Y", "does_not_exist.csv", "source_exists", "", "Error"])
    wb.close()

    assert_that(main(["--driver", str(driver)])).is_equal_to(1)


def test_python_module_entrypoint(sample_driver: pathlib.Path) -> None:
    """Running ``python -m dataspector`` exits cleanly with code 0."""
    proc = subprocess.run(
        [sys.executable, "-m", "dataspector", "--driver", str(sample_driver)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert_that(proc.returncode).is_equal_to(0)
    assert_that(proc.stdout).contains("Printing results of checks")


def test_coboller_cli_inspect_and_convert(
    data_dir: pathlib.Path,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """coboller CLI inspects copybooks, previews decoded rows, and converts to CSV."""
    cbl_path = data_dir / "sample_cobol_mainframe.cbl"
    dat_path = data_dir / "sample_cobol_mainframe.dat"

    assert_that(coboller_main(["inspect", str(cbl_path), "--omit_filler", "true"])).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("record_length=67").contains("ACCT-BALANCE")

    assert_that(
        coboller_main(
            ["convert", str(cbl_path), str(dat_path), "--encoding", "cp500", "--nrows", "2"]
        )
    ).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("1000001").contains("1000002")

    out_csv = tmp_path / "converted.csv"
    assert_that(
        coboller_main(
            [
                "convert",
                str(cbl_path),
                str(dat_path),
                "--encoding",
                "cp500",
                "--include_redefines",
                "true",
                "--output",
                str(out_csv),
            ]
        )
    ).is_equal_to(0)
    df = pd.read_csv(out_csv)
    assert_that(df).is_length(4)
    assert_that(list(df.columns)).contains("ACCT-BALANCE", "ACCT-EFF-YEAR")

    # Missing copybook or data file returns 1
    assert_that(coboller_main(["inspect", str(tmp_path / "missing.cbl")])).is_equal_to(1)
    assert_that(
        coboller_main(["convert", str(tmp_path / "missing.cbl"), str(dat_path)])
    ).is_equal_to(1)
    assert_that(
        coboller_main(["convert", str(cbl_path), str(tmp_path / "missing.dat")])
    ).is_equal_to(1)
