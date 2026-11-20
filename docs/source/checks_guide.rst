Checks & Pandera Integration
============================

Built-in Check Catalog
----------------------

Source-Level Checks
~~~~~~~~~~~~~~~~~~~

* :func:`~dataspector.checkers.source.source_exists` — verify file, COBOL pair, or DB table exists.
* :func:`~dataspector.checkers.source.source_fuzzy_find` — wildcard search across files, sheets, or tables.
* :func:`~dataspector.checkers.source.source_has_N_fields` — assert exact column count.
* :func:`~dataspector.checkers.source.source_modified_recently` — assert mtime within ``days_ago`` days.
* :func:`~dataspector.checkers.source.source_modified_on_date` — assert mtime within ``tolerance`` of ``date``.
* :func:`~dataspector.checkers.source.source_storage_size_roughly` — assert byte size within relative tolerance.
* :func:`~dataspector.checkers.source.source_source_same_fields` — compare column sets across two sources.
* :func:`~dataspector.checkers.source.source_source_identical` — byte-level or shallow file equality.
* :func:`~dataspector.checkers.source.source_source_size_roughly_same` — compare file sizes within tolerance.
* :func:`~dataspector.checkers.source.source_source_roughly_same_number_of_records` — compare row counts across two sources.

Record-Level Checks
~~~~~~~~~~~~~~~~~~~

* :func:`~dataspector.checkers.record.record_contains` / :func:`~dataspector.checkers.record.record_contains_at_least`
* :func:`~dataspector.checkers.record.record_field_contains`
* :func:`~dataspector.checkers.record.record_field_contains_at_least`
* :func:`~dataspector.checkers.record.record_field_contains_only`
* :func:`~dataspector.checkers.record.record_field_is_unique`
* :func:`~dataspector.checkers.record.record_if_field1_startswith_field2_contains_only`
* :func:`~dataspector.checkers.record.record_field_not_null` / :func:`~dataspector.checkers.record.record_all_data_not_null`
* :func:`~dataspector.checkers.record.record_field_is_numeric`
* :func:`~dataspector.checkers.record.record_count` / :func:`~dataspector.checkers.record.record_count_greater_than`
* :func:`~dataspector.checkers.record.record_field_numeric_value_between`
* :func:`~dataspector.checkers.record.record_field_date_between`
* :func:`~dataspector.checkers.record.record_validate_schema` (powered by **Pandera**)

Data-Integrity Framework Evaluation & Pandera Integration
---------------------------------------------------------

Modern Python offers mature DataFrame validation frameworks such as
**Pandera**, **Great Expectations**, and **Pydantic**. After evaluating how they
fit DataSpector's architecture:

* **Pandera** was integrated directly into DataSpector because it is lightweight,
  pandas-native, zero-infrastructure, supports YAML/JSON schema serialization,
  and validates each streamed :class:`pandas.DataFrame` chunk cleanly.
* **DataSpector's unique strengths** — format-agnostic :class:`~dataspector.core.GenericData`
  loading, mainframe COBOL/EBCDIC/COMP-3 decoding, source-level file/DB checks,
  cross-source comparisons, chunked streaming aggregation, and Excel driver/report
  workflows — complement Pandera rather than duplicate it.
* **Great Expectations** is well-suited for enterprise data-catalog platforms
  with persistent metadata stores, but introduces substantial runtime weight
  unnecessary for a lightweight CLI/library tool.

Using ``record_validate_schema``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:func:`~dataspector.checkers.record.record_validate_schema` accepts:

1. A :class:`pandera.pandas.DataFrameSchema` instance.
2. A concise Python dictionary (or JSON string) mapping column names to dtypes
   and checks (``gt``, ``ge``, ``lt``, ``le``, ``in_range``, ``isin``, ``notin``,
   ``str_length``, ``str_matches``, ``str_startswith``, ``str_endswith``, ``str_contains``).
3. A path to a Pandera ``.json`` or ``.yaml`` schema file.
4. A path to a COBOL ``.cbl`` copybook (automatically converted via
   :meth:`~dataspector.coboller.copybook.Copybook.to_pandera_schema`).

.. code-block:: python

   import pandera.pandas as pa
   import dataspector

   schema = pa.DataFrameSchema(
       {
           "host": pa.Column(str, unique=True, checks=pa.Check.str_startswith("srv-app-")),
           "domain": pa.Column(int, checks=pa.Check.in_range(1, 10)),
       }
   )

   history = dataspector.run_checks_on_location(
       "tests/data/sample_excel.xlsx",
       [("record_validate_schema", {"schema": schema})],
   )
   assert history.all_passed
