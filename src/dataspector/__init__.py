"""DataSpector: format-agnostic data-integrity checking and COBOL copybook conversion."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from dataspector import checkers, coboller, settings
from dataspector.checkers import CheckOutcome, requires_all_data
from dataspector.cli import (
    coboller_main,
    main,
    run_coboller_convert,
    run_coboller_inspect,
    run_dataspector,
)
from dataspector.core import (
    CheckeredHistory,
    GenericData,
    available_checks,
    connect_to_copybook,
    connect_to_embedded_db,
    connect_to_location,
    connect_to_server,
    load_and_run_checks,
    load_driverfile,
    parse_cell_to_dict,
    pretty_print_results,
    run_checks_on_location,
    version_adder,
    write_excel_report,
)

try:
    __version__ = version("dataspector")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = [
    "CheckOutcome",
    "CheckeredHistory",
    "GenericData",
    "__version__",
    "available_checks",
    "checkers",
    "coboller",
    "coboller_main",
    "connect_to_copybook",
    "connect_to_embedded_db",
    "connect_to_location",
    "connect_to_server",
    "load_and_run_checks",
    "load_driverfile",
    "main",
    "parse_cell_to_dict",
    "pretty_print_results",
    "requires_all_data",
    "run_checks_on_location",
    "run_coboller_convert",
    "run_coboller_inspect",
    "run_dataspector",
    "settings",
    "version_adder",
    "write_excel_report",
]
