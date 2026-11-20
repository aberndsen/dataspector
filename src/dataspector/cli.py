"""Command-line interfaces for ``dataspector`` and ``coboller`` powered by ``jsonargparse``."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from jsonargparse import auto_cli
from loguru import logger

from dataspector.coboller import Copybook
from dataspector.core import (
    load_and_run_checks,
    pretty_print_results,
    version_adder,
    write_excel_report,
)
from dataspector.settings import (
    CobollerConvertSettings,
    CobollerInspectSettings,
    DataSpectorSettings,
    LogLevel,
)


def _configure_logging(level: LogLevel) -> None:
    """Configure loguru stderr sink at *level*."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name} - {message}",
    )


def run_dataspector(settings: DataSpectorSettings) -> int:
    """Execute the DataSpector batch check workflow from *settings*.

    Parameters
    ----------
    settings
        Parsed CLI / config settings.

    Returns
    -------
    int
        Exit status code (``0`` if all checks pass, ``1`` otherwise).
    """
    _configure_logging(settings.log_level)

    if settings.driver is None:
        logger.error("No driver workbook supplied. Pass --driver <path.xlsx>.")
        return 1

    if not settings.driver.exists():
        logger.error("Could not find driver file {}. Stopping DataSpector.", settings.driver)
        return 1

    results = load_and_run_checks(
        settings.driver,
        use_multiprocessing=settings.use_multiprocess,
    )
    pretty_print_results(results)

    if settings.output is not None:
        out_target = settings.output
        if settings.overwrite and out_target.exists():
            out_target.unlink()
        fout = (
            str(out_target) if settings.overwrite else version_adder(out_target, extension=".xlsx")
        )
        written = write_excel_report(results, fout)
        print(f"Writing Excel report to {written.resolve()}")

    if any(not res.all_passed for res in results):
        print("Some checks failed to pass. Exiting with status code 1.")
        return 1

    return 0


def run_coboller_inspect(settings: CobollerInspectSettings) -> int:
    """Print a copybook's field layout, PIC/USAGE types, and byte offsets.

    Parameters
    ----------
    settings
        Parsed CLI settings for the ``coboller inspect`` subcommand.

    Returns
    -------
    int
        Exit status code (``0`` on success, ``1`` if the copybook is missing).
    """
    _configure_logging(settings.log_level)

    if not settings.copybook.exists():
        print(f"Error: copybook not found: {settings.copybook}")
        return 1

    cbl = Copybook(settings.copybook)
    table = cbl.summary(
        include_redefines=settings.include_redefines,
        include_filler=not settings.omit_filler,
    )
    print(
        f"Copybook: {settings.copybook} "
        f"(record_length={cbl.record_length} bytes, fields={len(table)})"
    )
    print(table.to_string(index=False))
    return 0


def run_coboller_convert(settings: CobollerConvertSettings) -> int:
    """Preview or convert a COBOL data file into a human-readable format.

    Parameters
    ----------
    settings
        Parsed CLI settings for the ``coboller convert`` subcommand.

    Returns
    -------
    int
        Exit status code (``0`` on success, ``1`` if an input file is missing).
    """
    _configure_logging(settings.log_level)

    if not settings.copybook.exists():
        print(f"Error: copybook not found: {settings.copybook}")
        return 1
    if not settings.datafile.exists():
        print(f"Error: data file not found: {settings.datafile}")
        return 1

    cbl = Copybook(settings.copybook)

    if settings.output is not None:
        written = cbl.convert(
            settings.datafile,
            settings.output,
            encoding=settings.encoding,
            float_format=settings.float_format,
            byteorder=settings.byteorder,
            include_redefines=settings.include_redefines,
            include_filler=settings.include_filler,
        )
        print(f"Converted {settings.datafile} -> {written}")
        return 0

    df = cbl.to_dataframe(
        settings.datafile,
        nrows=settings.nrows,
        encoding=settings.encoding,
        float_format=settings.float_format,
        byteorder=settings.byteorder,
        include_redefines=settings.include_redefines,
        include_filler=settings.include_filler,
    )
    print(df.to_string(index=False))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``dataspector`` CLI.

    Parameters
    ----------
    argv
        Optional argument list (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Exit status code (``0`` if all checks pass, ``1`` otherwise).
    """
    settings = auto_cli(
        DataSpectorSettings,
        args=list(argv) if argv is not None else None,
        as_positional=False,
    )
    return run_dataspector(settings)


def coboller_main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``coboller`` CLI (``inspect`` and ``convert`` subcommands).

    Parameters
    ----------
    argv
        Optional argument list (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Exit status code (``0`` on success, ``1`` on error).
    """
    settings = auto_cli(
        {
            "inspect": CobollerInspectSettings,
            "convert": CobollerConvertSettings,
        },
        args=list(argv) if argv is not None else None,
    )
    if isinstance(settings, CobollerInspectSettings):
        return run_coboller_inspect(settings)
    return run_coboller_convert(settings)
