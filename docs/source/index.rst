.. meta::
   :description: Enterprise data-quality and integrity auditing with automated Excel reporting, plus pure-Python COBOL copybook and mainframe EBCDIC/COMP-3 extract conversion to CSV, Parquet, JSON, Excel, or pandas DataFrames.
   :keywords: data quality python, data integrity checks, automated excel audit report, read cobol python, read mainframe file python, convert cobol mainframe extract, cobol copybook parser, ebcdic to csv, comp-3 packed decimal python, cobol to parquet, cobol to pandas, data validation, pandera

DataSpector Documentation
=========================

**DataSpector** is a pure-Python library and CLI combining **enterprise
data-quality & integrity auditing** (``dataspector``) with **COBOL copybook &
mainframe data extract conversion** (``coboller``):

1. **Enforce format-agnostic data-integrity checks & automated audit reporting**
   across CSV, Excel, fixed-width text, Parquet, JSON, HDF5, SQLite, MS Access,
   ODBC databases, and COBOL datasets — inspired by replacing million-dollar
   enterprise data-governance suites (like Varonis) with an open-source engine
   that runs **22+ source, record, cross-source reconciliation, and declarative**
   `Pandera <https://pandera.readthedocs.io/>`_ **schema checks** from Python or
   an Excel driver workbook and exports color-coded Excel audit reports.
2. **Read & convert COBOL mainframe extracts in pure Python** — decode EBCDIC
   (``cp500``, ``cp037``), ``COMP-3`` packed decimals, ``COMP-6``,
   ``COMP``/``COMP-5``/``COMP-X``, ``COMP-1``/``COMP-2`` (IEEE & IBM HFP), signed
   zoned decimals, ``OCCURS``, ``REDEFINES``, UTF-8, DBCS, and bitfields directly
   into clean, human-readable **CSV, TSV, JSON/JSONL, Excel, Parquet, or pandas
   DataFrames** via :mod:`dataspector.coboller` and the ``coboller`` CLI.

Run Data-Integrity Checks & Generate Excel Audit Reports
--------------------------------------------------------

Audit any file, database table, or mainframe extract from Python or an Excel
driver workbook:

.. code-block:: python

   >>> import dataspector
   >>> results = dataspector.run_checks_on_location(
   ...     "tests/data/sample_csv.csv",
   ...     [
   ...         ("source_exists", {}),
   ...         ("source_has_N_fields", {"n_fields": 5}),
   ...         ("record_count", {"nrows": 31}),
   ...         ("record_field_not_null", {"field": "Cost Center"}),
   ...         ("record_field_numeric_value_between", {"field": "Cost [CAD]", "constraint": (0, 200000)}),
   ...     ],
   ... )
   >>> results.all_passed
   True
   >>> dataspector.write_excel_report({"Sample CSV": results}, "audit_report.xlsx")

Or run an entire multi-source audit suite in parallel from an Excel driver file:

.. code-block:: bash

   uv run dataspector --driver test_driver.xlsx --output report.xlsx --use_multiprocess true

Read & Convert a COBOL Mainframe Extract in 3 Lines
---------------------------------------------------

.. code-block:: python

   >>> from dataspector.coboller import Copybook
   >>> cbl = Copybook("tests/data/sample_cobol_mainframe.cbl")
   >>> df = cbl.to_dataframe("tests/data/sample_cobol_mainframe.dat", encoding="cp500", include_filler=False)
   >>> cbl.convert("tests/data/sample_cobol_mainframe.dat", "accounts.csv", encoding="cp500")
   PosixPath('accounts.csv')

Or directly from the command line:

.. code-block:: bash

   uv run coboller inspect tests/data/sample_cobol_mainframe.cbl --omit_filler true
   uv run coboller convert tests/data/sample_cobol_mainframe.cbl tests/data/sample_cobol_mainframe.dat --encoding cp500 --output accounts.csv

.. toctree::
   :maxdepth: 2
   :hidden:

   usage
   api/index
   consulting

Contents
--------

* :doc:`usage` — Installation, locating data sources, CLI/Python usage, Excel driver workbooks, and extending DataSpector.
* :doc:`coboller_guide` — Reading COBOL copybooks, converting mainframe EBCDIC/COMP-3 extracts, and the 69-copybook / 37-extract benchmark.
* :doc:`checks_guide` — Built-in source/record checks and Pandera schema integration.
* :doc:`api/index` — Full API reference for ``core``, ``coboller``, ``checkers``, ``cli``, and ``settings``.
* :doc:`consulting` — Enterprise consulting, custom mainframe COBOL/EBCDIC migration pipelines, and automated data-governance audit solutions.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
