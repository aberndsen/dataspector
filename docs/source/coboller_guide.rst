COBOL Copybooks & Data Conversion Guide
=======================================

The :mod:`dataspector.coboller` module (and its ``coboller`` CLI) turns
fixed-width text and compressed binary mainframe files — including EBCDIC,
``COMP-3`` packed decimals, binary ``COMP``/``COMP-5``/``COMP-X`` integers,
``COMP-1``/``COMP-2`` floats, and ``REDEFINES`` overlays — into clean
:class:`pandas.DataFrame` tables and human-readable **CSV, TSV, JSON/JSONL,
Excel, or Parquet** files.

Interactive Exploration & Conversion Walkthrough
------------------------------------------------

Raw mainframe extracts mix EBCDIC characters with binary packed decimals and
floating-point bytes that are unreadable in standard editors:

.. code-block:: python

   >>> import pathlib
   >>> pathlib.Path("tests/data/sample_cobol_mainframe.dat").read_bytes()[:40]
   b'\xd5\xc1\xf1\xf0\xf0\xf0\xf0\xf0\xf1\xf7@@\xc1\xf2\xf0\xf2\xf4\xf0\xf1\xf1\xf5\xf0\xf0\xf1\xf2\xf5\xf5\xc0\x00$\x00\x0b^(=.\x14{?\xf0'

With :class:`~dataspector.coboller.copybook.Copybook`, you can inspect the layout,
preview decoded rows, convert to modern formats, and validate against an
auto-generated Pandera schema in just a few lines:

.. code-block:: python

   >>> from dataspector.coboller import Copybook
   >>> cbl = Copybook("tests/data/sample_cobol_mainframe.cbl")
   >>> cbl.record_length
   67

   # 1. Inspect field names, PIC clauses, storage USAGE, byte offsets, and widths
   >>> cbl.summary(include_filler=False)
                   name  level      pic   usage           kind  offset  byte_length  signed  decimals  is_redefines
   0        ACCT-REGION     10       XX DISPLAY   ALPHANUMERIC       0            2   False         0         False
   1        ACCT-NUMBER     10     X(7) DISPLAY   ALPHANUMERIC       2            7   False         0         False
   2   ACCT-CHECK-DIGIT     10        X DISPLAY   ALPHANUMERIC       9            1   False         0         False
   3        ACCT-STATUS      5        X DISPLAY   ALPHANUMERIC      12            1   False         0         False
   4      ACCT-EFF-DATE      5     9(8) DISPLAY        INTEGER      13            8   False         0         False
   5    ACCT-ADJUSTMENT      5 S9(5)V99 DISPLAY        DECIMAL      21            7    True         2         False
   6   ACCT-TERM-MONTHS      5    S9(4)    COMP         BINARY      28            2    True         0         False
   7         ACCT-SCORE      5    S9(9)    COMP         BINARY      30            4    True         0         False
   8          ACCT-RATE      5           COMP-1          FLOAT      34            4    True         0         False
   9        ACCT-FACTOR      5           COMP-2          FLOAT      38            8    True         0         False
   10      ACCT-BALANCE      5 S9(9)V99  COMP-3 PACKED_DECIMAL      46            6    True         2         False
   11        PERIOD-AMT     10 S9(7)V99  COMP-3 PACKED_DECIMAL      52            5    True         2         False
   12     PERIOD-AMT-01     10 S9(7)V99  COMP-3 PACKED_DECIMAL      57            5    True         2         False
   13     PERIOD-AMT-02     10 S9(7)V99  COMP-3 PACKED_DECIMAL      62            5    True         2         False

   # 2. Decode into a pandas DataFrame (use nrows=... to preview huge files instantly)
   >>> df = cbl.to_dataframe(
   ...     "tests/data/sample_cobol_mainframe.dat",
   ...     encoding="cp500",
   ...     include_filler=False,
   ...     nrows=5,
   ... )
   >>> df[["ACCT-REGION", "ACCT-NUMBER", "ACCT-STATUS", "ACCT-EFF-DATE", "ACCT-ADJUSTMENT", "ACCT-BALANCE"]]
     ACCT-REGION ACCT-NUMBER ACCT-STATUS  ACCT-EFF-DATE  ACCT-ADJUSTMENT  ACCT-BALANCE
   0          NA     1000001           A       20240115           125.50     250000.00
   1          EU     1000002           A       20240220           -42.75     -15000.50
   2          AP     1000003           C       20231201             0.00          0.00
   3          NA     1000004           A       20240630          9999.99    1234567.89

   # 3. Convert fixed-width & compressed COBOL files into human-readable formats
   >>> cbl.convert("tests/data/sample_cobol_mainframe.dat", "accounts.csv", encoding="cp500")
   PosixPath('accounts.csv')
   >>> cbl.convert("tests/data/sample_cobol_mainframe.dat", "accounts.jsonl", encoding="cp500")
   PosixPath('accounts.jsonl')
   >>> cbl.convert("tests/data/sample_cobol_mainframe.dat", "accounts.xlsx", encoding="cp500")
   PosixPath('accounts.xlsx')

.. note::

   :meth:`~dataspector.coboller.copybook.Copybook.convert` streams chunk-by-chunk for
   ``.csv``, ``.tsv``, and ``.jsonl`` outputs, allowing multi-gigabyte
   mainframe files to be converted with constant memory usage.

Command-Line Inspection & Conversion (``coboller``)
---------------------------------------------------

DataSpector ships a dedicated ``coboller`` CLI command for quick terminal
inspection and format conversion:

.. code-block:: bash

   # Print the copybook's field layout and byte offsets
   uv run coboller inspect tests/data/sample_cobol_mainframe.cbl --omit_filler true

   # Preview decoded rows on stdout (default: 10 rows)
   uv run coboller convert tests/data/sample_cobol_mainframe.cbl tests/data/sample_cobol_mainframe.dat \
       --encoding cp500 --nrows 5

   # Convert EBCDIC + COMP-3 binary file to CSV, TSV, JSONL, JSON, Excel, or Parquet
   uv run coboller convert tests/data/sample_cobol_mainframe.cbl tests/data/sample_cobol_mainframe.dat \
       --encoding cp500 --include_redefines true --output accounts.csv

Supported COBOL Data Types
--------------------------

.. list-table:: COBOL Data Type Matrix
   :header-rows: 1
   :widths: 26 24 18 32

   * - COBOL Clause
     - Storage / Usage
     - Physical Width
     - Python Output Type
   * - ``PIC X(n)``
     - ``DISPLAY``
     - ``n`` bytes
     - ``str`` (decoded via encoding)
   * - ``PIC A(n)``
     - ``DISPLAY``
     - ``n`` bytes
     - ``str`` (alphabetic)
   * - ``PIC N(n)`` / ``USAGE NATIONAL``
     - ``NATIONAL`` (UTF-16)
     - ``2 * n`` bytes
     - ``str`` (UTF-16-BE or LE)
   * - ``PIC U(n)`` / ``PIC U BYTE-LENGTH m``
     - ``UTF-8`` (Enterprise COBOL 6.3+)
     - ``4 * n`` or ``m`` bytes
     - ``str`` (UTF-8)
   * - ``PIC G(n)`` / ``USAGE DISPLAY-1``
     - ``DISPLAY-1`` (DBCS graphic)
     - ``2 * n`` bytes
     - ``str`` (configurable ``dbcs_encoding``)
   * - ``PIC 1(n) USAGE BIT``
     - ``BIT`` (COBOL-2002 bitfield)
     - ``ceil(n / 8)`` bytes
     - ``str`` of ``'0'``/``'1'`` bits
   * - ``PIC 9(n)``
     - ``DISPLAY`` (zoned)
     - ``n`` bytes
     - ``int``
   * - ``PIC 9(n)V9(m)``
     - ``DISPLAY`` (implied decimal)
     - ``n + m`` bytes
     - ``float`` (or ``Decimal``)
   * - ``PIC 9(n)P(k)`` / ``VP(k)9(n)``
     - ``DISPLAY`` (scaled)
     - ``n`` bytes
     - ``int`` / ``float`` (or ``Decimal``)
   * - ``PIC S9(n)`` (overpunch)
     - ``DISPLAY`` (EBCDIC/ASCII)
     - ``n`` bytes
     - signed ``int`` / ``float``
   * - ``PIC S9(n) SIGN LEADING/TRAILING SEPARATE``
     - ``DISPLAY``
     - ``n + 1`` bytes
     - signed ``int`` / ``float``
   * - ``PIC $$$,$$9.99-`` / ``Z.ZZ9,99-`` (``DECIMAL-POINT IS COMMA``)
     - ``DISPLAY`` (numeric-edited)
     - expanded length
     - ``float`` (or ``str`` for ``/`` masks)
   * - ``PIC +9.9(5)E+99`` / ``PIC +9(2)V99E+99``
     - ``DISPLAY`` (external float)
     - expanded length
     - ``float``
   * - ``PIC S9(n)V9(m) COMP-3`` / ``PACKED-DECIMAL``
     - ``COMP-3`` (BCD)
     - ``(d // 2) + 1`` bytes
     - ``int`` / ``float`` (or ``Decimal``)
   * - ``PIC 9(n)[V9(m)] COMP-6``
     - ``COMP-6`` (unsigned BCD, no sign nibble)
     - ``ceil(d / 2)`` bytes
     - ``int`` / ``float`` (or ``Decimal``)
   * - ``PIC S9(n) COMP`` / ``COMP-4`` / ``BINARY``
     - ``COMP`` (binary int)
     - 2 / 4 / 8 bytes
     - ``int`` / ``float`` (or ``Decimal``)
   * - ``PIC S9(n) COMP-5``
     - ``COMP-5`` (native binary)
     - 2 / 4 / 8 bytes
     - ``int`` / ``float`` (full binary range)
   * - ``PIC X(n) COMP-X`` / ``PIC 9(n) COMP-X``
     - ``COMP-X`` (variable-width unsigned binary)
     - ``n`` or ``1..8`` bytes
     - ``int``
   * - ``BINARY-CHAR`` / ``SHORT`` / ``LONG`` / ``DOUBLE [UNSIGNED]``
     - COBOL-2002 C-interop binary
     - 1 / 2 / 4 / 8 bytes
     - ``int``
   * - ``USAGE COMP-1`` / ``FLOAT-SHORT``
     - 32-bit float (IEEE / IBM HFP)
     - 4 bytes
     - ``float``
   * - ``USAGE COMP-2`` / ``FLOAT-LONG``
     - 64-bit float (IEEE / IBM HFP)
     - 8 bytes
     - ``float``
   * - ``USAGE POINTER`` / ``FUNCTION-POINTER`` / ``PROCEDURE-POINTER``
     - Unsigned address
     - 4 or 8 bytes
     - ``int``
   * - ``USAGE INDEX``
     - Signed table index
     - 4 bytes
     - ``int``

Structural COBOL Features
-------------------------

* **Fixed-format & free-format source**: strips sequence numbers (columns 1–6),
  identification fields (columns 73–80), column-7 comments (``*``, ``/``), and
  free-format inline comments (``*>``).
* **Hierarchical groups & group-level ``USAGE``**: child fields inherit group
  ``USAGE`` (e.g. ``05 BIN-GROUP USAGE BINARY.``) unless overridden.
* **``OCCURS n [TIMES]``** (and ``OCCURS m TO n DEPENDING ON``): expands nested
  arrays on both fields and groups with zero-padded suffixes (``-01``, ``-02``,
  or 3-digit ``-001`` when ``occurs >= 100``).
* **``REDEFINES``**: tracks overlays on the redefined target without inflating
  primary record length; pass ``include_redefines=True`` to decode overlays at
  the exact same byte offsets alongside the primary fields.
* **Level ``88`` condition names**: attached to their parent
  :class:`~dataspector.coboller.copybook.ElementaryItem` as
  :class:`~dataspector.coboller.copybook.ConditionName`
  objects rather than polluting physical columns.
* **``FILLER`` & unnamed fields**: included in byte-offset calculations and
  optionally omitted from output DataFrames via ``include_filler=False``.

Streaming Large Mainframe Files
-------------------------------

For large files that do not fit in memory, iterate chunk-by-chunk with
:meth:`~dataspector.coboller.copybook.Copybook.yield_data`:

.. code-block:: python

   from dataspector.coboller import CopyBook

   cbl = CopyBook("tests/data/sample_cobol_mainframe.cbl")

   for chunk in cbl.yield_data(
       "tests/data/sample_cobol_mainframe.dat",
       chunksize=500,
       encoding="cp500",          # EBCDIC International (or 'cp037', 'ascii', 'utf-8')
       float_format="ieee",       # or 'ibm' for IBM System/390 HFP COMP-1/COMP-2
       byteorder="big",           # IBM mainframe default ('little' for x86 COBOL)
       as_decimal=False,          # True for exact decimal.Decimal fixed-point values
       include_redefines=True,    # Also decode REDEFINES overlays
       include_filler=False,      # Omit FILLER columns from DataFrame
   ):
       process(chunk)

Automatic Pandera Schema Generation
-----------------------------------

Generate a :class:`pandera.pandas.DataFrameSchema` directly from any copybook
to validate column types, string widths, numeric digit bounds, and level-88
allowed values:

.. code-block:: python

   schema = cbl.to_pandera_schema(include_filler=False, enforce_conditions=True)
   validated_df = schema.validate(df)

Or combine COBOL parsing directly with :func:`~dataspector.core.run_checks_on_location`:

.. code-block:: python

   import dataspector

   history = dataspector.run_checks_on_location(
       dataspector.GenericData(
           "[tests/data/sample_cobol_mainframe.cbl][tests/data/sample_cobol_mainframe.dat]",
           reader_options={"encoding": "cp500", "include_filler": False},
       ),
       [
           ("source_exists", {}),
           ("record_count", {"nrows": 4}),
           ("record_field_numeric_value_between", {"field": "ACCT-TERM-MONTHS", "constraint": (1, 360)}),
           ("record_validate_schema", {"schema": "tests/data/sample_cobol_mainframe.cbl"}),
       ],
   )

Low-Level Packing & Unpacking Helpers
-------------------------------------

``coboller`` also exports standalone, round-trippable binary helpers for custom
pipelines and test data generation:

* :func:`~dataspector.coboller.codecs.comp3_unpack` / :func:`~dataspector.coboller.codecs.comp3_pack`
* :func:`~dataspector.coboller.codecs.comp6_unpack` / :func:`~dataspector.coboller.codecs.comp6_pack`
* :func:`~dataspector.coboller.codecs.comp_unpack` / :func:`~dataspector.coboller.codecs.comp_pack`
* :func:`~dataspector.coboller.codecs.comp_float_unpack` / :func:`~dataspector.coboller.codecs.comp_float_pack`
* :func:`~dataspector.coboller.codecs.ibm_hfp_to_float` / :func:`~dataspector.coboller.codecs.float_to_ibm_hfp`
* :func:`~dataspector.coboller.codecs.external_float_unpack`
* :func:`~dataspector.coboller.codecs.bit_unpack` / :func:`~dataspector.coboller.codecs.bit_pack`
* :func:`~dataspector.coboller.codecs.zoned_unpack` / :func:`~dataspector.coboller.codecs.zoned_pack`
* :func:`~dataspector.coboller.codecs.parse_numeric_edited`
