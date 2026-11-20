# DataSpector

[![PyPI version](https://img.shields.io/pypi/v/dataspector.svg)](https://pypi.org/project/dataspector/)
[![Python versions](https://img.shields.io/pypi/pyversions/dataspector.svg)](https://pypi.org/project/dataspector/)
[![CI](https://github.com/aberndsen/dataspector/actions/workflows/ci.yml/badge.svg)](https://github.com/aberndsen/dataspector/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue.svg)](https://aberndsen.github.io/dataspector/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/aberndsen/dataspector/blob/main/LICENSE)

**DataSpector** is a format-agnostic Python toolkit for **converting** legacy fixed-width and compressed mainframe/COBOL files into modern human-readable formats and **enforcing data-integrity checks** across heterogeneous data sources (COBOL, CSV, fixed-width text, Excel, Parquet, JSON/JSONL, SQLite, and ODBC databases).

## Highlights

- **Convert mainframe & fixed-width COBOL files effortlessly (`coboller`)**: turn opaque EBCDIC, fixed-width, and binary-compressed files (`COMP-3` packed decimal, `COMP`/`COMP-5`/`COMP-X`, `COMP-6`, `COMP-1`/`COMP-2` IEEE & IBM HFP, `BINARY-*`, `FLOAT-*`, `PIC U` UTF-8, `PIC G` DBCS, `PIC 1` bitfields, `OCCURS`, `REDEFINES`) directly into **CSV, TSV, JSON/JSONL, Excel, Parquet, or pandas DataFrames** — via CLI or Python.
- **Format-agnostic `GenericData` abstraction**: query existence, columns, modification timestamps, storage size, table/sheet lists, and stream records uniformly as `pandas.DataFrame` chunks across all supported formats.
- **Pandera schema integration**: run declarative `pandera.DataFrameSchema` validations on any format via `record_validate_schema`, or auto-generate a Pandera schema directly from a COBOL copybook with `CopyBook.to_pandera_schema()`.
- **Excel driver & reporting**: configure batch integrity checks in an Excel workbook, execute sequentially or in parallel, and export color-coded Excel reports.

## Installation

Install from [PyPI](https://pypi.org/project/dataspector/):

```bash
pip install dataspector
# or with uv
uv add dataspector
```

Or install from source for local development using [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --all-groups
```

Optional extras:

```bash
pip install "dataspector[odbc]"   # pyodbc support for SQL Server / MS Access
pip install "dataspector[docs]"   # Sphinx + PyData theme documentation dependencies
```

## Converting Fixed-Width & Compressed COBOL Files (`coboller`)

Mainframe extracts are often unreadable binary/EBCDIC blobs packed with `COMP-3`, `COMP`, and floating-point fields:

```text
b'\xd5\xc1\xf1\xf0\xf0\xf0\xf0\xf0\xf1\xf7@@\xc1\xf2\xf0\xf2\xf4\xf0\xf1\xf1\xf5\xf0\xf0\xf1\xf2\xf5\xf5\xc0\x00$\x00\x0b^(=.\x14{?\xf0'
```

### One-Line CLI Inspection & Conversion

Both `coboller` and `dataspector` CLIs are powered by `jsonargparse` from typed dataclasses in `dataspector.settings` (supporting `--config config.yaml` files as well as CLI flags):

```bash
# Inspect field layout, byte offsets, PIC clauses, and storage types
uv run coboller inspect tests/data/sample_cobol_mainframe.cbl --omit_filler true

# Preview decoded records directly in the terminal
uv run coboller convert tests/data/sample_cobol_mainframe.cbl tests/data/sample_cobol_mainframe.dat --encoding cp500

# Convert binary EBCDIC/COMP-3 data directly to human-readable CSV, JSONL, JSON, or Excel
uv run coboller convert tests/data/sample_cobol_mainframe.cbl tests/data/sample_cobol_mainframe.dat \
    --encoding cp500 --output accounts.csv
```

### Interactive Python Walkthrough

```python
>>> from dataspector.coboller import Copybook
>>> cbl = Copybook("tests/data/sample_cobol_mainframe.cbl")
>>> cbl.record_length
67

# 1. Inspect the decoded byte layout interactively
>>> cbl.summary(include_filler=False)[["name", "pic", "usage", "offset", "byte_length"]].head(6)
               name      pic   usage  offset  byte_length
0       ACCT-REGION       XX DISPLAY       0            2
1       ACCT-NUMBER     X(7) DISPLAY       2            7
2  ACCT-CHECK-DIGIT        X DISPLAY       9            1
3       ACCT-STATUS        X DISPLAY      12            1
4     ACCT-EFF-DATE     9(8) DISPLAY      13            8
5   ACCT-ADJUSTMENT S9(5)V99 DISPLAY      21            7

# 2. Preview decoded mainframe records as a clean pandas DataFrame
>>> df = cbl.to_dataframe(
...     "tests/data/sample_cobol_mainframe.dat",
...     encoding="cp500",
...     include_filler=False,
...     nrows=5,
... )
>>> df[["ACCT-REGION", "ACCT-NUMBER", "ACCT-STATUS", "ACCT-ADJUSTMENT", "ACCT-BALANCE"]]
  ACCT-REGION ACCT-NUMBER ACCT-STATUS  ACCT-ADJUSTMENT  ACCT-BALANCE
0          NA     1000001           A           125.50     250000.00
1          EU     1000002           A           -42.75     -15000.50
2          AP     1000003           C             0.00          0.00
3          NA     1000004           A          9999.99    1234567.89

# 3. Stream-convert to human-readable CSV, JSONL, JSON, Excel, or Parquet
>>> cbl.convert("tests/data/sample_cobol_mainframe.dat", "accounts.csv", encoding="cp500")
PosixPath('accounts.csv')
>>> cbl.convert("tests/data/sample_cobol_mainframe.dat", "accounts.jsonl", encoding="cp500")
PosixPath('accounts.jsonl')

# 4. Auto-generate a Pandera schema from the copybook and validate the decoded data
>>> schema = cbl.to_pandera_schema(include_filler=False, enforce_conditions=True)
>>> _ = schema.validate(df)
```

## Format-Agnostic Data-Integrity Checks

### Python API

```python
from pathlib import Path
import dataspector

results = dataspector.run_checks_on_location(
    Path("tests/data/sample_csv.csv"),
    [
        ("source_exists", {}),
        ("source_has_N_fields", {"n_fields": 5}),
        ("record_count", {"nrows": 31}),
        ("record_field_numeric_value_between", {"field": "Cost [CAD]", "constraint": (0, 200000)}),
    ],
)
assert results.all_passed
```

### Batch Checks via Excel Driver CLI

```bash
uv run dataspector --driver test_driver.xlsx --output report.xlsx
uv run dataspector --config run.yaml
```

Key options (from `DataSpectorSettings`):
- `--driver`: path to the Excel driver workbook (`Location Details` and `Checks to Run` sheets).
- `--output`: path to write the formatted Excel report (auto-versioned unless `--overwrite true`).
- `--use_multiprocess true`: run location checks in parallel worker processes.
- `--log_level`: Loguru verbosity (`ERROR`, `WARNING`, `INFO`, `DEBUG`, `TRACE`).
- `--config`: optional YAML/JSON configuration file.

## Development

```bash
# Run tests with coverage
uv run pytest

# Lint & format check
uv run ruff check src tests

# Static type checking
uv run ty check src tests

# Build Sphinx HTML documentation (PyData theme)
uv run sphinx-build -b html docs/source docs/build/html
```
