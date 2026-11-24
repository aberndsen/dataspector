.. meta::
   :description: Enterprise data-quality and integrity auditing with automated Excel reporting, plus pure-Python COBOL copybook and mainframe EBCDIC/COMP-3 extract conversion to CSV, Parquet, JSON, Excel, or pandas DataFrames.
   :keywords: data quality python, data integrity checks, automated excel audit report, read cobol python, read mainframe file python, convert cobol mainframe extract, cobol copybook parser, ebcdic to csv, comp-3 packed decimal python, cobol to parquet, cobol to pandas, data validation, pandera

DataSpector Documentation
=========================

**DataSpector** is a pure-Python library and CLI combining **enterprise
data-quality & integrity auditing** (``dataspector``) with **COBOL copybook &
mainframe data extract conversion** (``coboller``):

1. **Enforce format-agnostic data-integrity checks & automated audit reporting**
   across CSV, TSV, Excel, fixed-width text, Parquet, JSON/JSONL, HDF5, COBOL
   datasets, and any SQLAlchemy database (**SQLite, PostgreSQL, MySQL, MariaDB,
   SQL Server, Oracle, DuckDB, MS Access**) using a **unified URI locator syntax**
   (see :doc:`data_sources`) — inspired by replacing million-dollar enterprise
   data-governance suites (like Varonis) with an open-source engine that runs
   **22+ source, record, cross-source reconciliation, and declarative**
   `Pandera <https://pandera.readthedocs.io/>`_ **schema checks** from Python or
   an Excel driver workbook and exports color-coded Excel audit reports.
2. **Read & convert COBOL mainframe extracts in pure Python** — decode EBCDIC
   (``cp500``, ``cp037``), ``COMP-3`` packed decimals, ``COMP-6``,
   ``COMP``/``COMP-5``/``COMP-X``, ``COMP-1``/``COMP-2`` (IEEE & IBM HFP), signed
   zoned decimals, ``OCCURS``, ``REDEFINES``, UTF-8, DBCS, and bitfields directly
   into clean, human-readable **CSV, TSV, JSON/JSONL, Excel, Parquet, or pandas
   DataFrames** via :mod:`dataspector.coboller` and the ``coboller`` CLI.

.. image:: _static/dataspector-architecture.jpg
   :alt: Mainframe/COBOL, SQL databases, spreadsheets, and flat files flow through DataSpector into data-quality reports and modern data formats
   :align: center
   :width: 100%

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

Address any file, COBOL extract, or SQL database using the same unified locator
syntax (see :doc:`data_sources` for the full reference, ``DataSourceSpec``, and
optional SQLAlchemy DB extras):

.. code-block:: text

   csv://drops/daily_drop.dat
   excel://reports/q1.xlsx#Sheet1
   cobol://layouts/acct.cbl::extracts/acct.dat?encoding=cp500
   sqlite:///data/warehouse.sqlite#accounts
   postgresql+psycopg://${PG_USER}:${PG_PASS}@db.internal:5432/prod#public.users
   mysql+pymysql://${MYSQL_USER}:${MYSQL_PASS}@host:3306/shop#orders

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

* :doc:`usage` — Installation, CLI/Python usage, Excel driver workbooks, and extending DataSpector.
* :doc:`data_sources` — Unified URI/scheme locator syntax, ``DataSourceSpec``, ``${ENV_VAR}`` secret interpolation, and optional SQLAlchemy DB extras (PostgreSQL, MySQL/MariaDB, Oracle, DuckDB, SQL Server, SQLite, MS Access).
* :doc:`coboller_guide` — Reading COBOL copybooks, converting mainframe EBCDIC/COMP-3 extracts, and the 69-copybook / 37-extract benchmark.
* :doc:`checks_guide` — Built-in source/record checks and Pandera schema integration.
* :doc:`api/index` — Full API reference for ``core``, ``coboller``, ``checkers``, ``cli``, and ``settings``.
* :doc:`consulting` — Enterprise consulting, custom mainframe COBOL/EBCDIC migration pipelines, and automated data-governance audit solutions.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
