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

:class:`~dataspector.core.GenericData` accepts several location formats:

.. list-table:: Supported Location Syntax
   :header-rows: 1
   :widths: 35 65

   * - Format
     - Example
   * - Local file or directory
     - ``"tests/data/sample_csv.csv"`` or ``Path("tests/data")``
   * - Excel workbook + sheet
     - ``"[tests/data/sample_excel.xlsx][Sheet1]"``
   * - SQLite / MS Access + table
     - ``"[tests/data/sample_sqlite.sqlite][Table1]"`` or ``(path, "Table1")``
   * - COBOL copybook + data file
     - ``"[layout.cbl][records.dat]"`` or ``(Path("layout.cbl"), Path("records.dat"))``
   * - Remote SQL Server (ODBC)
     - ``"[server][database][table]"`` or ``("server", "database", "table")``

Supported file extensions include ``.csv``, ``.tsv``, ``.txt`` (delimited or
fixed-width via ``reader_options={"widths": [...]}``), ``.xlsx``/``.xls``,
``.parquet``, ``.json``/``.jsonl``, ``.hdf``/``.h5``, ``.sqlite``/``.db``,
``.mdb``/``.accdb``, and ``.cbl``/``.cpy``/``.cob`` copybooks.

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
