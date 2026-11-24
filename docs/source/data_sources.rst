.. meta::
   :description: Supported data sources and unified URI/scheme locator syntax in DataSpector across CSV, TSV, Excel, fixed-width text, Parquet, JSON/JSONL, HDF5, COBOL copybook + data pairs, SQLite, PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, DuckDB, and MS Access.
   :keywords: dataspector data sources, unified locator syntax, sqlalchemy data quality, postgresql data audit python, mysql data validation python, duckdb data quality, cobol copybook locator, excel sheet audit, env var interpolation

Supported Data Sources & Unified Locator Syntax
===============================================

:class:`~dataspector.core.GenericData` (and the ``Location`` column of Excel
driver workbooks) accepts a **single, unified locator syntax** across flat
files, spreadsheets, COBOL copybook + mainframe extract pairs, and any
SQLAlchemy-compatible database backend.

You can specify any data source in two clean, interchangeable ways:

1. **Unified URI / Scheme Strings** (or plain file paths with optional
   ``#Sheet`` / ``#Table`` fragments) — ideal for the CLI, Excel driver
   workbooks (``test_driver.xlsx``), and concise Python calls.
2. **Structured :class:`~dataspector.core.DataSourceSpec` (or ``dict``)** —
   ideal for typed Python pipelines and YAML/JSON configurations.

Unified URI / Scheme Reference
------------------------------

.. list-table:: Unified Locator Syntax Across All Formats
   :header-rows: 1
   :widths: 28 72

   * - Source Category
     - Unified Locator Examples
   * - **Single Files (Auto or Explicit Scheme)**
     - * ``"tests/data/sample_csv.csv"`` *(auto-detected from file extension)*
       * ``"csv://drops/daily_drop.dat"`` *(forces CSV reader regardless of extension)*
       * ``"tsv://exports/tab_report.txt"`` *(forces tab-delimited reader)*
       * ``"fwf://extracts/fixed.bin?widths=[10,20,15]"`` *(fixed-width text)*
       * ``"parquet://lake/events.parquet"``
       * ``"json://api/payload.json"`` / ``"jsonl://logs/events.log"``
   * - **Excel Sheets & HDF5 Keys**
     - * ``"excel://reports/q1.xlsx#Sheet1"`` *(or ``"reports/q1.xlsx#Sheet1"``)*
       * ``"excel://reports/q1.xlsx?sheet=Summary"``
       * ``"hdf5://store/data.h5#measurements"``
   * - **COBOL Copybook + Mainframe Extract Pair**
     - * ``"cobol://layouts/acct.cbl::data/acct.dat"``
       * ``"cobol://layouts/acct.cbl::data/acct.dat?encoding=cp500&include_filler=false"``
       * ``"cobol://layouts/acct.txt?data=data/acct.dat&encoding=cp037&float_format=ibm"``
       * *(Using ``cobol://`` forces copybook parsing even if the copybook file has a ``.txt`` or ``.inc`` extension)*
   * - **Embedded Databases (SQLite, DuckDB, MS Access)**
     - * ``"sqlite:///tests/data/sample_sqlite.sqlite#Table1"`` *(or ``?table=Table1``)*
       * ``"duckdb:///analytics/warehouse.duckdb#events"``
       * ``"access://legacy/finance.accdb#Orders"``
   * - **SQL Server, PostgreSQL, MySQL, MariaDB, Oracle & More**
     - * ``"postgresql://user:${PG_PASS}@db.internal:5432/warehouse#public.users"``
       * ``"postgresql+psycopg://user:${PG_PASS}@host:5432/prod#finance.ledger"``
       * ``"mysql+pymysql://user:${MYSQL_PASS}@host:3306/shop#orders"``
       * ``"mariadb+pymysql://user:${DB_PASS}@host:3306/app#audit_log"``
       * ``"mssql+pyodbc://server/db?driver=ODBC+Driver+18+for+SQL+Server#dbo.accounts"``
       * ``"oracle+oracledb://user:${ORA_PASS}@host:1521/service#transactions"``
       * ``"snowflake://user:${SF_PASS}@account_id/database/schema?warehouse=COMPUTE_WH&role=ANALYST#fact_sales"``

.. tip::

   **Environment Variable Interpolation (Keep Secrets Out of Excel & YAML)**

   Any locator string (and :attr:`~dataspector.core.DataSourceSpec.uri` /
   :attr:`~dataspector.core.DataSourceSpec.data`) automatically expands
   ``${VAR_NAME}`` placeholders from :data:`os.environ`:

   .. code-block:: text

      postgresql+psycopg://readonly:${PG_PASSWORD}@db.internal:5432/prod#public.fact_sales
      ${DATABASE_URL}#public.fact_sales
      cobol://${COPYBOOK_DIR}/acct.cbl::${EXTRACT_DIR}/acct.dat?encoding=cp500

   Because credentials are resolved at runtime, analysts can safely commit and
   share Excel driver workbooks without ever embedding database passwords.

Database Backends & Optional Extras (SQLAlchemy)
------------------------------------------------

DataSpector uses `SQLAlchemy <https://www.sqlalchemy.org/>`_ (included by
default) to inspect tables, count rows with dialect-safe SQL quoting, and
stream records across database flavours. **SQLite** works out of the box with
zero extra installs; for other backends, install the lightweight optional extra
matching your database:

.. list-table:: Database & Format Optional Extras
   :header-rows: 1
   :widths: 22 38 40

   * - Backend / Format
     - Install Command
     - Example Locator URL
   * - **SQLite**
     - Included with ``pip install dataspector``
     - ``sqlite:///path/to/db.sqlite#Table1``
   * - **PostgreSQL**
     - ``pip install "dataspector[postgres]"``
     - ``postgresql+psycopg://user:${PASS}@host:5432/db#public.users``
   * - **MySQL / MariaDB**
     - ``pip install "dataspector[mysql]"``
     - ``mysql+pymysql://user:${PASS}@host:3306/db#orders``
   * - **Oracle** *(thin mode)*
     - ``pip install "dataspector[oracle]"``
     - ``oracle+oracledb://user:${PASS}@host:1521/service#ledger``
   * - **DuckDB**
     - ``pip install "dataspector[duckdb]"``
     - ``duckdb:///warehouse.duckdb#events``
   * - **Snowflake**
     - ``pip install "dataspector[snowflake]"``
     - ``snowflake://user:${SF_PASS}@account_id/db/schema?warehouse=WH#table``
   * - **All pure-wheel SQL drivers**
     - ``pip install "dataspector[db]"``
     - Installs ``postgres``, ``mysql``, ``oracle``, and ``duckdb`` extras together
   * - **SQL Server & MS Access (ODBC)**
     - ``pip install "dataspector[odbc]"``
     - ``mssql+pyodbc://server/db?driver=ODBC+Driver+18+for+SQL+Server#dbo.accounts`` or ``access://file.accdb#Orders``
   * - **Parquet**
     - ``pip install "dataspector[parquet]"``
     - ``parquet://lake/events.parquet``

.. note::

   Any other SQLAlchemy dialect (Snowflake, BigQuery, Redshift, Trino,
   ClickHouse) also works immediately as long as its SQLAlchemy dialect package
   is installed in your environment — just append ``#<table_name>`` or
   ``#<schema>.<table_name>`` to the standard SQLAlchemy connection URL.

Structured Python & YAML Specification (``DataSourceSpec``)
-----------------------------------------------------------

For programmatic pipelines or YAML/JSON configs where explicit fields are
clearer than URL query strings, pass a :class:`~dataspector.core.DataSourceSpec`
dataclass (or an equivalent ``dict``) directly to
:class:`~dataspector.core.GenericData` or
:func:`~dataspector.core.run_checks_on_location`:

.. code-block:: python

   import dataspector
   from dataspector import DataSourceSpec, GenericData

   # 1. PostgreSQL table with explicit schema
   pg_source = GenericData(
       DataSourceSpec(
           uri="postgresql+psycopg://readonly:${PG_PASS}@db.internal:5432/warehouse",
           format="postgres",
           table="finance.fact_transactions",
       )
   )

   # 2. COBOL copybook + EBCDIC binary extract (even with a non-standard extension)
   cobol_source = DataSourceSpec(
       uri="layouts/account_layout.txt",
       format="cobol",
       data="extracts/accounts_cp500.dat",
       options={"encoding": "cp500", "include_filler": False},
   )
   results = dataspector.run_checks_on_location(
       cobol_source,
       [("source_exists", {}), ("record_count_greater_than", {"nrows": 0})],
   )

   # 3. Fixed-width text file disguised with a .bin extension (dict form)
   fwf_source = GenericData(
       {
           "format": "fwf",
           "uri": "drops/daily_fixed.bin",
           "options": {"widths": [10, 25, 12]},
       }
   )

Inline Query Parameters vs. ``reader_options``
----------------------------------------------

Query parameters in unified URI strings (such as
``cobol://layout.cbl::data.dat?encoding=cp500&include_filler=false`` or
``fwf://fixed.txt?widths=[4,6]``) are automatically parsed into Python types
(booleans, numbers, lists, strings) and merged into
:attr:`~dataspector.core.GenericData.reader_options`. Explicit
``reader_options`` passed to :class:`~dataspector.core.GenericData` (or the
``Reader Arguments`` column in an Excel driver workbook) override any matching
inline query keys.

Migrating from v1.x Bracket / Tuple Locators
--------------------------------------------

In DataSpector **2.0**, the legacy bracketed (``[...][...]``) and tuple locator
formats were removed in favor of the unified URI/scheme syntax and
:class:`~dataspector.core.DataSourceSpec`:

.. list-table:: v1.x to v2.0 Locator Migration
   :header-rows: 1
   :widths: 45 55

   * - Removed v1.x Syntax
     - v2.0 Unified Replacement
   * - ``"[workbook.xlsx][Sheet1]"`` / ``(path, "Sheet1")``
     - ``"excel://workbook.xlsx#Sheet1"`` *(or ``"workbook.xlsx#Sheet1"``)*
   * - ``"[db.sqlite][Table1]"`` / ``(path, "Table1")``
     - ``"sqlite:///db.sqlite#Table1"``
   * - ``"[layout.cbl][records.dat]"`` / ``(cbl, dat)``
     - ``"cobol://layout.cbl::records.dat"``
   * - ``"[server][database][table]"`` / ``(srv, db, tbl)``
     - ``"mssql+pyodbc://server/database?driver=ODBC+Driver+18+for+SQL+Server#table"``
