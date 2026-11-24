Usage Guide
===========

Installation
------------

Install DataSpector from `PyPI <https://pypi.org/project/dataspector/>`_:

.. code-block:: bash

   pip install dataspector
   # or with uv
   uv add dataspector

Optional extras:

* ``pip install "dataspector[odbc]"`` — enables ``pyodbc`` for SQL Server and MS Access.
* ``pip install "dataspector[docs]"`` — installs Sphinx, ``numpydoc``, and ``pydata-sphinx-theme``.

For local development from a repository checkout using ``uv``:

.. code-block:: bash

   uv sync --all-groups

Locating Data Sources
---------------------

:class:`~dataspector.core.GenericData` (and the ``Location`` column in Excel
driver workbooks) supports a **unified URI/scheme locator syntax**, a structured
:class:`~dataspector.core.DataSourceSpec` dataclass/dict, and backward-compatible
bracketed or tuple locators across single files, COBOL copybook + data pairs, and
any SQLAlchemy-compatible database flavour (SQLite, PostgreSQL, MySQL, MariaDB,
SQL Server, Oracle, DuckDB, Snowflake, MS Access):

.. list-table:: Unified Locator Syntax
   :header-rows: 1
   :widths: 30 70

   * - Source Category
     - Unified Locator Examples
   * - **Single Files (Auto or Explicit Format)**
     - * ``"tests/data/sample_csv.csv"`` *(auto-detected from extension)*
       * ``"csv://data/daily_drop.dat"`` *(forces CSV reader regardless of extension)*
       * ``"tsv://data/export.txt"``
       * ``"fwf://data/fixed.bin?widths=[10,20,15]"`` *(fixed-width text)*
       * ``"parquet://data/events.parquet"`` / ``"json://data/payload.json"`` / ``"jsonl://data/stream.log"``
   * - **Excel Sheets & HDF5 Keys**
     - * ``"excel://tests/data/sample_excel.xlsx#Sheet1"`` or ``"tests/data/sample_excel.xlsx#Sheet1"``
       * ``"hdf5://store/data.h5#measurements"``
       * *(Legacy bracket syntax ``"[tests/data/sample_excel.xlsx][Sheet1]"`` is also supported)*
   * - **COBOL Copybook + Data Extract**
     - * ``"cobol://layout.cbl::records.dat"``
       * ``"cobol://layout.cbl::records.dat?encoding=cp500&include_filler=false"``
       * ``"cobol://layout.cbl?data=records.dat&encoding=cp500"``
       * *(Legacy ``"[layout.cbl][records.dat]"`` and ``(Path("layout.cbl"), Path("records.dat"))`` are also supported)*
   * - **Embedded Databases (SQLite, DuckDB, MS Access)**
     - * ``"sqlite:///tests/data/sample_sqlite.sqlite#Table1"`` *(or ``?table=Table1``)*
       * ``"duckdb:///analytics.duckdb#events"``
       * ``"access://legacy.accdb#Orders"``
       * *(Legacy ``"[tests/data/sample_sqlite.sqlite][Table1]"`` is also supported)*
   * - **SQL Databases (Postgres, MySQL, MariaDB, MSSQL, Oracle, etc.)**
     - * ``"postgresql://user:${DB_PASS}@db.internal:5432/warehouse#public.users"``
       * ``"mysql+pymysql://user:${DB_PASS}@host:3306/shop#orders"``
       * ``"mariadb+pymysql://user:${DB_PASS}@host:3306/app#audit_log"``
       * ``"mssql+pyodbc://server/database?driver=ODBC+Driver+18+for+SQL+Server#dbo.accounts"``
       * ``"oracle+oracledb://user:${DB_PASS}@host:1521/service#ledger"``
       * *(Legacy SQL Server ``"[server][database][table]"`` is also supported)*
   * - **Structured Python / YAML Spec**
     - ``DataSourceSpec(uri="postgresql://...", format="postgres", table="public.users", options={...})``

.. tip::

   **Environment Variable Interpolation**: Any locator string can reference
   environment variables using ``${VAR_NAME}`` (for example,
   ``postgresql://readonly:${PG_PASSWORD}@db.internal:5432/prod#fact_sales`` or
   ``${DATABASE_URL}#fact_sales``) so credentials never need to be stored in
   Excel driver workbooks.

Running Checks from Python
--------------------------

Use :func:`~dataspector.core.run_checks_on_location` to run a list of checks on
a single source:

.. code-block:: python

   import dataspector

   history = dataspector.run_checks_on_location(
       "tests/data/sample_csv.csv",
       [
           ("source_exists", {}),
           ("source_has_N_fields", {"n_fields": 5}),
           ("record_contains", {"field": "Cost Center"}),
           ("record_count", {"nrows": 31}),
           ("record_field_numeric_value_between", {"field": "Cost [CAD]", "constraint": (0, 200000)}),
       ],
   )

   print(history.all_passed)
   dataspector.pretty_print_results(history)

Results, notes, and any captured exceptions are stored on the returned
:class:`~dataspector.core.CheckeredHistory` object keyed by check index.

Running Checks from an Excel Driver File
----------------------------------------

For batch validation across many sources, define locations and checks in an
Excel workbook — download the sample :download:`test_driver.xlsx <../../test_driver.xlsx>`
(also viewable on `GitHub <https://github.com/aberndsen/dataspector/blob/main/test_driver.xlsx>`_,
alongside the sample data files in
`tests/data/ <https://github.com/aberndsen/dataspector/tree/main/tests/data>`_):

1. **Location Details** (header on row 2): columns ``Location``, ``Source Name``,
   and ``Reader Arguments``.
2. **Checks to Run** (header on row 4): columns ``Process`` (``Y``/``1``/``True``),
   ``Source Name``, ``Check``, ``Keyword Arguments``, and ``Severity``
   (``Error`` or ``Warning``).

``Keyword Arguments`` and ``Reader Arguments`` accept JSON objects, brace-less
JSON pairs (``"widths": [32, 32]``), Python literals, ``key=value`` pairs, or
single scalar values (automatically mapped to the check's first parameter).

Execute from the CLI (powered by ``jsonargparse`` and
:class:`~dataspector.settings.DataSpectorSettings`):

.. code-block:: bash

   uv run dataspector --driver test_driver.xlsx --output report.xlsx
   uv run dataspector --driver test_driver.xlsx --output report.xlsx --overwrite true --use_multiprocess true
   uv run dataspector --config run.yaml

Or programmatically via :func:`~dataspector.core.load_and_run_checks` and
:func:`~dataspector.core.write_excel_report`:

.. code-block:: python

   import dataspector

   results = dataspector.load_and_run_checks("test_driver.xlsx", use_multiprocessing=True)
   dataspector.write_excel_report(results, "report.xlsx")

Extending DataSpector
---------------------

Adding Custom Checks
~~~~~~~~~~~~~~~~~~~~

Check functions live in :mod:`dataspector.checkers` (organized into
:mod:`dataspector.checkers.source`, :mod:`dataspector.checkers.record`, and
:mod:`dataspector.checkers.utils`) and follow a clean contract:

* **Source checks** begin with ``source_`` and accept a
  :class:`~dataspector.core.GenericData` as their first argument.
* **Record checks** begin with ``record_`` and accept a
  :class:`pandas.DataFrame` chunk as their first argument.
* Every check returns a :class:`~dataspector.checkers.utils.CheckOutcome` dataclass
  with ``passed`` (``True`` / ``False`` / ``None`` while streaming), optional
  ``notes``, and updated ``kwargs``.
* Multi-chunk checks are decorated with
  :func:`~dataspector.checkers.utils.requires_all_data` and accept
  ``_last_chunk: bool = True``.

Adding New Storage Formats
~~~~~~~~~~~~~~~~~~~~~~~~~~

Extend :class:`~dataspector.core.GenericData` so that its metadata properties
(``exists``, ``columns``, ``last_modified``, ``list_of_tables``,
``number_of_records``) and :meth:`~dataspector.core.GenericData.yield_data`
handle your format.

.. toctree::
   :maxdepth: 2
   :caption: Guides & Benchmarks

   coboller_guide
   checks_guide
