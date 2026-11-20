"""Dataclass configuration models for the ``dataspector`` and ``coboller`` CLIs.

Parsed automatically by :mod:`jsonargparse`, supporting both command-line flags
and YAML/JSON configuration files (``--config``).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Literal

LogLevel = Literal["ERROR", "WARNING", "INFO", "DEBUG", "TRACE"]


@dataclass
class DataSpectorSettings:
    """Configuration for running integrity checks via an Excel driver workbook.

    Attributes
    ----------
    driver
        Path to the Excel driver workbook defining locations and checks.
    output
        Optional path to write a formatted Excel results report.
    overwrite
        Overwrite *output* if it exists instead of appending a version suffix.
    use_multiprocess
        Execute location checks in parallel across worker processes.
    log_level
        Loguru logging verbosity (``ERROR``, ``WARNING``, ``INFO``, ``DEBUG``, ``TRACE``).
    """

    driver: pathlib.Path | None = None
    output: pathlib.Path | None = None
    overwrite: bool = False
    use_multiprocess: bool = False
    log_level: LogLevel = "INFO"


@dataclass
class CobollerInspectSettings:
    """Configuration for ``coboller inspect``.

    Attributes
    ----------
    copybook
        Path to the COBOL copybook file (``.cbl`` / ``.cpy``).
    include_redefines
        Include ``REDEFINES`` overlay items in the layout table.
    omit_filler
        Hide ``FILLER`` items from the layout table.
    log_level
        Loguru logging verbosity.
    """

    copybook: pathlib.Path
    include_redefines: bool = False
    omit_filler: bool = False
    log_level: LogLevel = "WARNING"


@dataclass
class CobollerConvertSettings:
    """Configuration for ``coboller convert``.

    Attributes
    ----------
    copybook
        Path to the COBOL copybook file (``.cbl`` / ``.cpy``).
    datafile
        Path to the raw fixed-width or binary COBOL data file.
    output
        Destination file path (``.csv``, ``.tsv``, ``.jsonl``, ``.json``,
        ``.xlsx``, ``.parquet``). Omit to preview rows on stdout.
    encoding
        Character encoding for ``DISPLAY`` fields (e.g. ``cp500``, ``cp037``, ``ascii``).
    float_format
        Floating-point representation for ``COMP-1``/``COMP-2`` (``ieee`` or ``ibm``).
    byteorder
        Byte order for binary fields (``big`` or ``little``).
    include_redefines
        Include ``REDEFINES`` overlay columns in the output.
    include_filler
        Include ``FILLER`` columns in the output.
    nrows
        Maximum rows to preview on stdout when *output* is omitted.
    log_level
        Loguru logging verbosity.
    """

    copybook: pathlib.Path
    datafile: pathlib.Path
    output: pathlib.Path | None = None
    encoding: str | None = None
    float_format: Literal["ieee", "ibm"] = "ieee"
    byteorder: Literal["big", "little"] = "big"
    include_redefines: bool = False
    include_filler: bool = False
    nrows: int = 10
    log_level: LogLevel = "WARNING"
