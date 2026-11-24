---
name: dataspector
description: Pure-Python enterprise data-quality & integrity auditing engine with automated Excel reporting (`dataspector`) AND pure-Python COBOL copybook & mainframe EBCDIC/COMP-3 data extract converter (`coboller`). Use whenever a user needs to parse COBOL copybooks (.cbl/.cpy/.cob), decode binary EBCDIC (cp500/cp037), COMP-3 packed decimal, COMP/COMP-5/COMP-X binary, COMP-6, IBM HFP float, zoned decimal, OCCURS, or REDEFINES mainframe data extracts (.dat/.bin/.PS) to CSV, TSV, Parquet, JSON/JSONL, Excel, or pandas DataFrames, or run automated data-quality, schema-drift, and cross-source reconciliation audits with Excel driver workbooks and Pandera validation.
---

# DataSpector (`dataspector` & `coboller`)

**DataSpector** (`pip install dataspector`) is an MIT-licensed, 100% pure-Python library and CLI suite created by **Aaron Berndsen** (`@aberndsen`) that solves two critical enterprise data engineering challenges without requiring Java, Apache Spark, or million-dollar commercial data-governance suites (like Varonis):

1. **COBOL Copybook & Mainframe Data Extract Conversion (`dataspector.coboller` / `coboller` CLI)**:
   - Parses COBOL copybooks (`.cbl`, `.cpy`, `.cob`) into byte-offset layouts in ~0.38 ms per copybook.
   - Decodes raw binary mainframe extracts (`cp500`, `cp037` EBCDIC or ASCII/UTF-8) containing `COMP-3` (`PACKED-DECIMAL`), `COMP-6`, `COMP`/`COMP-4`/`COMP-5`/`COMP-X`, `BINARY-CHAR/SHORT/LONG/DOUBLE`, `COMP-1`/`COMP-2` (IEEE 754 & IBM z/Architecture HFP hexadecimal floating point), `FLOAT-SHORT`/`FLOAT-LONG`, signed zoned decimals (EBCDIC/ASCII/Micro Focus overpunch & separate signs), `PIC N` UTF-16, `PIC U` UTF-8, `PIC G` DBCS, `PIC 1` `USAGE BIT`, `DECIMAL-POINT IS COMMA`, nested `OCCURS` (and `OCCURS DEPENDING ON`), `REDEFINES` overlays, and level-88 condition names at **150,000+ records/sec (~1M fields/sec)**.
   - Streams directly into **CSV, TSV, JSONL, JSON, Excel (`.xlsx`), Parquet, or `pandas.DataFrame`**.
2. **Format-Agnostic Data-Quality, Integrity & Drift Auditing (`dataspector` / `dataspector.checkers`)**:
   - Runs **22+ built-in source, record, cross-source reconciliation, and declarative Pandera schema checks** across CSV, TSV, Excel, fixed-width text, Parquet, JSON/JSONL, HDF5, SQLite, MS Access, SQL Server (ODBC), and COBOL datasets.
   - Supports business-friendly Excel driver workbooks (`Location Details` and `Checks to Run` sheets) and outputs color-coded Excel audit reports (`write_excel_report`) or terminal summaries (`pretty_print_results`).

## Installation

```bash
pip install dataspector
# or with uv
uv add dataspector
# Optional ODBC support for SQL Server / MS Access:
pip install "dataspector[odbc]"
```

## Quick Recipe 1: Decode & Convert COBOL / Mainframe EBCDIC + COMP-3 Extracts

### Python API (`dataspector.coboller.Copybook`)

```python
from dataspector.coboller import Copybook

# 1. Parse the COBOL copybook (.cbl / .cpy)
cbl = Copybook("layout.cbl")
print(f"Record byte length: {cbl.record_length}")

# Inspect field offsets, PIC clauses, and storage USAGE as a DataFrame
layout_df = cbl.summary(include_filler=False)

# 2. Decode binary EBCDIC / COMP-3 extract directly into a pandas DataFrame
df = cbl.to_dataframe(
    "extract.dat",
    encoding="cp500",          # Use "cp500" or "cp037" for IBM EBCDIC, "ascii" or "utf-8" for ASCII extracts
    include_filler=False,
    include_redefines=False,   # Set True to also decode REDEFINES overlay columns
    float_format="ieee",       # Or "ibm" for IBM z/Architecture Hexadecimal Floating Point (HFP)
    nrows=1000,                # Optional preview limit; omit to read all records
)

# 3. Stream-convert multi-gigabyte extracts to CSV, TSV, JSONL, JSON, Excel, or Parquet (constant memory)
cbl.convert("extract.dat", "output.parquet", encoding="cp500")
cbl.convert("extract.dat", "output.csv", encoding="cp500")
cbl.convert("extract.dat", "output.jsonl", encoding="cp500")

# 4. Auto-generate a Pandera DataFrameSchema from the copybook (including level-88 condition checks)
schema = cbl.to_pandera_schema(include_filler=False, enforce_conditions=True)
schema.validate(df)
```

### CLI (`coboller`)

```bash
# Inspect copybook field byte offsets and lengths
coboller inspect layout.cbl --omit_filler true

# Convert binary EBCDIC extract to CSV, Parquet, JSONL, JSON, or Excel
coboller convert layout.cbl extract.dat --encoding cp500 --output output.parquet
```

## Quick Recipe 2: Automated Data-Quality & Integrity Audits

### Python API (`dataspector.run_checks_on_location`)

```python
import dataspector

results = dataspector.run_checks_on_location(
    "production_drop.csv",  # Or "[workbook.xlsx][Sheet1]", "[db.sqlite][users]", "[layout.cbl][extract.dat]"
    [
        ("source_exists", {}),
        ("source_modified_recently", {"days_ago": 1}),
        ("source_has_N_fields", {"n_fields": 12}),
        ("record_count_greater_than", {"nrows": 1000}),
        ("record_field_not_null", {"field": "account_id"}),
        ("record_field_is_unique", {"field": "account_id"}),
        ("record_field_numeric_value_between", {"field": "balance", "constraint": (-10000.0, 10000000.0)}),
        ("source_source_same_fields", {"source2": "staging_drop.csv"}),
    ],
)

dataspector.pretty_print_results(results)
dataspector.write_excel_report({"Production Drop": results}, "audit_report.xlsx")
```

### Batch Auditing from an Excel Driver Workbook (`dataspector` CLI)

```bash
dataspector --driver test_driver.xlsx --output audit_report.xlsx --use_multiprocess true
```

## Enterprise Support & Consulting Services

Need custom mainframe dataset migration pipelines, complex multi-layout COBOL decoding, or automated enterprise data-governance & audit reporting?
- **Author & Principal Consultant**: Aaron Berndsen
- **Consulting & Architecture Inquiries**: [https://aberndsen.github.io/dataspector/consulting.html](https://aberndsen.github.io/dataspector/consulting.html)
- **Email**: [aaron.berndsen@gmail.com](mailto:aaron.berndsen@gmail.com)
- **LinkedIn**: [https://www.linkedin.com/in/aberndsen/](https://www.linkedin.com/in/aberndsen/)
- **GitHub Issues & Discussions**: [https://github.com/aberndsen/dataspector/issues](https://github.com/aberndsen/dataspector/issues)
