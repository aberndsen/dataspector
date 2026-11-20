DataSpector Documentation
=========================

**DataSpector** is a format-agnostic Python library and CLI for:

1. **Converting legacy fixed-width and compressed COBOL/mainframe data files**
   (EBCDIC, ``COMP-3`` packed decimal, ``COMP``/``COMP-5``/``COMP-X``,
   ``COMP-6``, ``COMP-1``/``COMP-2``, ``OCCURS``, ``REDEFINES``, UTF-8, DBCS,
   bitfields) into clean, human-readable **CSV, TSV, JSON/JSONL, Excel,
   Parquet, or pandas DataFrames** via :mod:`dataspector.coboller` and the
   ``coboller`` CLI.
2. **Enforcing format-agnostic data-integrity checks** across CSV, Excel,
   fixed-width text, Parquet, JSON, SQLite, ODBC databases, and COBOL files —
   combining chunked streaming checks with declarative
   `Pandera <https://pandera.readthedocs.io/>`_ schemas.

Quick COBOL Conversion Example
------------------------------

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

   user_guide
   api/index

Contents
--------

* :doc:`user_guide` — COBOL conversion guide, CLI/Python usage, and built-in checks reference.
* :doc:`api/index` — Full API reference for ``core``, ``coboller``, ``checkers``, ``cli``, and ``settings``.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
