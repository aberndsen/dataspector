.. meta::
   :description: Read COBOL copybooks and convert mainframe EBCDIC, COMP-3, binary, and fixed-width extracts to CSV, Parquet, JSON, Excel, or pandas DataFrames in pure Python — with format-agnostic data-integrity and Pandera validation.
   :keywords: read cobol python, read mainframe file python, convert cobol mainframe extract, cobol copybook parser, ebcdic to csv, comp-3 packed decimal python, cobol to parquet, cobol to pandas, data validation, pandera

DataSpector Documentation
=========================

**DataSpector** is a pure-Python library and CLI to **read COBOL & mainframe
extracts**, **convert legacy fixed-width and binary files into modern formats**,
and **validate data integrity** across heterogeneous sources:

1. **Read & convert COBOL mainframe extracts** — decode EBCDIC (``cp500``,
   ``cp037``), ``COMP-3`` packed decimals, ``COMP-6``, ``COMP``/``COMP-5``/``COMP-X``,
   ``COMP-1``/``COMP-2`` (IEEE & IBM HFP), signed zoned decimals, ``OCCURS``,
   ``REDEFINES``, UTF-8, DBCS, and bitfields directly into clean, human-readable
   **CSV, TSV, JSON/JSONL, Excel, Parquet, or pandas DataFrames** via
   :mod:`dataspector.coboller` and the ``coboller`` CLI.
2. **Enforce format-agnostic data-integrity checks** across COBOL, CSV, Excel,
   fixed-width text, Parquet, JSON, SQLite, and ODBC databases — combining
   chunked streaming checks with declarative
   `Pandera <https://pandera.readthedocs.io/>`_ schemas.

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

Contents
--------

* :doc:`usage` — Installation, locating data sources, CLI/Python usage, Excel driver workbooks, and extending DataSpector.
* :doc:`coboller_guide` — Reading COBOL copybooks, converting mainframe EBCDIC/COMP-3 extracts, and the 69-copybook / 37-extract benchmark.
* :doc:`checks_guide` — Built-in source/record checks and Pandera schema integration.
* :doc:`api/index` — Full API reference for ``core``, ``coboller``, ``checkers``, ``cli``, and ``settings``.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
