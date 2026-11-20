"""COBOL copybook AST classes (:class:`Copybook`, :class:`GroupItem`, :class:`ElementaryItem`)."""

from __future__ import annotations

import copy
import pathlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

import pandas as pd
import pandera.pandas as pa
from loguru import logger

from dataspector._reporting import chunks_to_dataframe, export_chunks
from dataspector.coboller.codecs import (
    bit_unpack,
    comp3_unpack,
    comp6_unpack,
    comp_float_unpack,
    comp_unpack,
    compute_decimal_exponent,
    expand_pic,
    external_float_unpack,
    is_ebcdic,
    parse_numeric_edited,
    predict_encoding,
    zoned_unpack,
)
from dataspector.coboller.constants import (
    BINARY_USAGES,
    DECIMAL_COMMA_RE,
    FIXED_BINARY_SIZES,
    PIC_ALPHA_ONLY,
    PIC_BIT_ONLY,
    PIC_DBCS_ONLY,
    PIC_EDITED_MARKERS,
    PIC_EXTERNAL_FLOAT,
    PIC_NATIONAL_ONLY,
    PIC_NUMERIC_PURE,
    PIC_UTF8_ONLY,
    SELF_SIZED_USAGES,
    USAGE_ALIASES,
    DataCategory,
    SignMode,
    Usage,
)
from dataspector.coboller.parser import (
    extract_statements,
    parse_condition_values,
    parse_statement,
)


@dataclass(frozen=True, slots=True)
class ConditionName:
    """Level-88 condition-name attached to a COBOL data item."""

    name: str
    raw_value: str
    values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedItem:
    """Flattened elementary item with exact byte offset and width in a record."""

    name: str
    field: ElementaryItem
    offset: int
    byte_length: int
    is_redefines: bool = False


class Copybook:
    """COBOL copybook parser, layout inspector, data reader, and format converter.

    Parameters
    ----------
    copybook
        Path to a COBOL copybook file.
    """

    def __init__(self, copybook: str | pathlib.Path) -> None:
        self._copybook = copybook
        self.copybook: pathlib.Path = pathlib.Path(copybook)
        logger.trace("Loading COBOL copybook from {}", self.copybook)
        self.raw: str = self.copybook.read_text(encoding="utf-8", errors="replace")
        self.records: list[GroupItem | ElementaryItem] = parse_copybook(self.raw)

    @classmethod
    def from_file(cls, path: str | pathlib.Path) -> Copybook:
        """Construct a :class:`Copybook` from a copybook file path.

        Parameters
        ----------
        path
            Path to a COBOL copybook file.

        Returns
        -------
        Copybook
            Parsed copybook instance.
        """
        return cls(path)

    @classmethod
    def from_string(cls, text: str, name: str = "<string>") -> Copybook:
        """Construct a :class:`Copybook` directly from raw copybook source text.

        Parameters
        ----------
        text
            Raw COBOL copybook source code.
        name
            Synthetic display name assigned to :attr:`copybook`.

        Returns
        -------
        Copybook
            Parsed copybook instance.
        """
        instance = cls.__new__(cls)
        instance._copybook = name
        instance.copybook = pathlib.Path(name)
        instance.raw = text
        instance.records = parse_copybook(text)
        return instance

    @property
    def columns(self) -> list[str]:
        """Alias for :attr:`fields`."""
        return self.fields

    @property
    def decimal_comma(self) -> bool:
        """``True`` if the copybook declares ``DECIMAL-POINT IS COMMA``."""
        return bool(DECIMAL_COMMA_RE.search(self.raw))

    @property
    def exists(self) -> bool:
        """``True`` if the underlying copybook file exists on disk."""
        return self.copybook.exists()

    @property
    def fields(self) -> list[str]:
        """Ordered elementary item names in primary record order."""
        return [rf.name for rf in self.layout(include_redefines=False, include_filler=True)]

    @property
    def has_binary_fields(self) -> bool:
        """``True`` if any item uses binary, packed, float, pointer, index, or wide storage."""
        return any(rf.field.is_binary for rf in self.layout(include_redefines=True))

    @property
    def record_length(self) -> int:
        """Total physical byte length of a single record."""
        return sum(rec.byte_length * rec.occurs for rec in self.records if rec.redefines is None)

    def convert(
        self,
        datfile: str | pathlib.Path,
        output: str | pathlib.Path,
        chunksize: int = 5000,
        encoding: str | None = None,
        float_format: Literal["ieee", "ibm"] = "ieee",
        byteorder: Literal["big", "little"] = "big",
        include_redefines: bool = False,
        include_filler: bool = False,
        line_ending: Literal["auto", "none", "lf", "crlf"] = "auto",
        dbcs_encoding: str = "utf-16-be",
        decimal_comma: bool | None = None,
    ) -> pathlib.Path:
        """Convert a fixed-width or compressed COBOL data file into a modern readable format.

        Streams chunk-by-chunk via :meth:`yield_data` for ``.csv``, ``.tsv``,
        and ``.jsonl`` outputs; also supports ``.json``, ``.xlsx``, and
        ``.parquet``. Aligned with :meth:`~dataspector.core.GenericData.convert`.

        Parameters
        ----------
        datfile
            Path to the raw COBOL data file.
        output
            Destination file path whose extension selects the output format.
        chunksize
            Number of rows per streaming chunk.
        encoding
            Character encoding for ``DISPLAY`` items (e.g. ``'cp500'``, ``'ascii'``).
        float_format
            Floating-point representation for ``COMP-1``/``COMP-2`` (``'ieee'`` or ``'ibm'``).
        byteorder
            Byte order for binary fields (``'big'`` or ``'little'``).
        include_redefines
            Include ``REDEFINES`` overlay columns in the converted output.
        include_filler
            Include ``FILLER`` columns (omitted by default for clean exports).
        line_ending
            Record delimiter mode (``'auto'``, ``'none'``, ``'lf'``, or ``'crlf'``).
        dbcs_encoding
            Character encoding for ``PIC G`` / ``DISPLAY-1`` DBCS fields.
        decimal_comma
            Override copybook ``DECIMAL-POINT IS COMMA`` detection.

        Returns
        -------
        pathlib.Path
            Path to the written output file.
        """
        logger.debug("Converting COBOL data {} -> {}", datfile, output)
        resolved = self.layout(
            include_redefines=include_redefines,
            include_filler=include_filler,
        )
        empty_cols = _deduplicate_names([rf.name for rf in resolved])
        chunks = self.yield_data(
            datfile,
            chunksize=chunksize,
            encoding=encoding,
            float_format=float_format,
            byteorder=byteorder,
            include_redefines=include_redefines,
            include_filler=include_filler,
            line_ending=line_ending,
            dbcs_encoding=dbcs_encoding,
            decimal_comma=decimal_comma,
        )
        return export_chunks(chunks, output, empty_columns=empty_cols)

    def find_record(self, name: str) -> GroupItem | ElementaryItem | None:
        """Find the first :class:`GroupItem` or :class:`ElementaryItem` matching *name*.

        Parameters
        ----------
        name
            Exact COBOL item name to search for.

        Returns
        -------
        GroupItem | ElementaryItem | None
            First matching item in depth-first order, or ``None`` if absent.
        """
        for item in self.records:
            if item.name == name:
                return item
            if isinstance(item, GroupItem):
                found = item.find_record(name)
                if found is not None:
                    return found
        return None

    def layout(
        self,
        include_redefines: bool = False,
        include_filler: bool = True,
    ) -> list[ResolvedItem]:
        """Compute flat byte-offset layout of all elementary items in the copybook.

        Parameters
        ----------
        include_redefines
            Include items defined under ``REDEFINES`` overlays.
        include_filler
            Include ``FILLER`` items in the resolved layout.

        Returns
        -------
        list[ResolvedItem]
            Ordered elementary items with exact byte offsets and widths.
        """
        resolved: list[ResolvedItem] = []

        def _walk(
            nodes: list[GroupItem | ElementaryItem],
            start_offset: int,
            is_redef_branch: bool,
            suffix: str = "",
        ) -> int:
            offset = start_offset
            sibling_offsets: dict[str, int] = {}

            for node in nodes:
                is_redef = is_redef_branch or (node.redefines is not None)
                if node.redefines is not None:
                    node_start = sibling_offsets.get(node.redefines, offset)
                    if not include_redefines:
                        continue
                else:
                    node_start = offset
                    sibling_offsets[node.name] = node_start

                curr = node_start
                for occ_idx in range(node.occurs):
                    occ_suffix = ""
                    if node.occurs > 1 and occ_idx > 0:
                        width = 3 if node.occurs >= 100 else 2
                        occ_suffix = f"-{occ_idx:0{width}d}"

                    if isinstance(node, ElementaryItem):
                        col_name = f"{node.name}{suffix}{occ_suffix}"
                        if include_filler or not node.is_filler:
                            resolved.append(
                                ResolvedItem(
                                    name=col_name,
                                    field=node,
                                    offset=curr,
                                    byte_length=node.byte_length,
                                    is_redefines=is_redef,
                                )
                            )
                        curr += node.byte_length
                    else:
                        curr = _walk(
                            node.records,
                            curr,
                            is_redef_branch=is_redef,
                            suffix=f"{suffix}{occ_suffix}",
                        )

                if node.redefines is None:
                    offset = curr
            return offset

        _walk(self.records, 0, is_redef_branch=False)
        return resolved

    def pic_to_fwf_kwargs(self, convert_compressed: bool = True) -> dict[str, Any]:
        """Return keyword arguments for :func:`pandas.read_fwf` on text copybooks.

        Parameters
        ----------
        convert_compressed
            Attach byte-level decoders for binary/compressed fields when ``True``;
            keep raw representations when ``False``.

        Returns
        -------
        dict[str, Any]
            Dictionary containing ``colspecs``, ``names``, and ``converters``
            suitable for unpacking into :func:`pandas.read_fwf`.
        """
        resolved = self.layout(include_redefines=False, include_filler=True)
        colspecs: list[tuple[int, int]] = []
        names: list[str] = []
        converters: dict[int, Callable[[Any], Any]] = {}

        for idx, rf in enumerate(resolved):
            names.append(rf.name)
            colspecs.append((rf.offset, rf.offset + rf.byte_length))
            field_kwargs = rf.field.pic_to_fwf_kwargs(convert_compressed=convert_compressed)
            conv = field_kwargs[0].get("converter")
            if conv is not None:
                converters[idx] = conv

        return {"colspecs": colspecs, "names": names, "converters": converters}

    def summary(
        self,
        include_redefines: bool = False,
        include_filler: bool = True,
    ) -> pd.DataFrame:
        """Return a tabular overview of every elementary item's byte layout and COBOL type.

        Parameters
        ----------
        include_redefines
            Include ``REDEFINES`` overlay items in the summary table.
        include_filler
            Include ``FILLER`` items in the summary table.

        Returns
        -------
        pandas.DataFrame
            Table with columns ``name``, ``level``, ``pic``, ``usage``, ``kind``,
            ``offset``, ``byte_length``, ``signed``, ``decimals``, and
            ``is_redefines``.
        """
        resolved = self.layout(
            include_redefines=include_redefines,
            include_filler=include_filler,
        )
        return pd.DataFrame(
            [
                {
                    "name": rf.name,
                    "level": rf.field.level,
                    "pic": (rf.field.description.get("pic") or "").strip(),
                    "usage": rf.field.usage.value,
                    "kind": rf.field.kind.value,
                    "offset": rf.offset,
                    "byte_length": rf.byte_length,
                    "signed": rf.field.signed,
                    "decimals": rf.field.decimals,
                    "is_redefines": rf.is_redefines,
                }
                for rf in resolved
            ]
        )

    def to_dataframe(
        self,
        datfile: str | pathlib.Path,
        nrows: int | None = None,
        chunksize: int = 500,
        encoding: str | None = None,
        convert_compressed: bool = True,
        drop_converters: bool = False,
        float_format: Literal["ieee", "ibm"] = "ieee",
        byteorder: Literal["big", "little"] = "big",
        as_decimal: bool = False,
        include_redefines: bool = False,
        include_filler: bool = True,
        line_ending: Literal["auto", "none", "lf", "crlf"] = "auto",
        dbcs_encoding: str = "utf-16-be",
        decimal_comma: bool | None = None,
    ) -> pd.DataFrame:
        """Decode *datfile* into a single materialized :class:`pandas.DataFrame`.

        Reads internally via chunked streaming (:meth:`yield_data`) and stops
        early once *nrows* records have been collected. Aligned with
        :meth:`~dataspector.core.GenericData.to_dataframe`.

        Notes
        -----
        Because the return value is a single in-memory DataFrame, pass *nrows*
        for quick previews of very large mainframe files, or iterate directly
        over :meth:`yield_data` when streaming files larger than memory.

        Parameters
        ----------
        datfile
            Path to the COBOL data file.
        nrows
            Optional maximum number of records to return (``None`` reads all).
        chunksize
            Number of rows decoded per internal streaming chunk.
        encoding
            Character encoding for ``DISPLAY`` items (auto-detected if ``None``).
        convert_compressed
            Decode binary/compressed items; retain hex representation if ``False``.
        drop_converters
            Keep all items as raw decoded strings / hex without numeric casting.
        float_format
            Floating-point representation for ``COMP-1``/``COMP-2`` (``'ieee'`` or ``'ibm'``).
        byteorder
            Byte order for binary fields (``'big'`` or ``'little'``).
        as_decimal
            Preserve exact precision with :class:`decimal.Decimal` for fixed-point numbers.
        include_redefines
            Include ``REDEFINES`` overlay columns.
        include_filler
            Include ``FILLER`` columns.
        line_ending
            Record delimiter mode (``'auto'``, ``'none'``, ``'lf'``, or ``'crlf'``).
        dbcs_encoding
            Character encoding for ``PIC G`` / ``DISPLAY-1`` DBCS items.
        decimal_comma
            Override copybook ``DECIMAL-POINT IS COMMA`` detection.

        Returns
        -------
        pandas.DataFrame
            Decoded records (empty DataFrame with copybook columns if no rows).
        """
        eff_chunk = min(chunksize, nrows) if nrows is not None and nrows > 0 else chunksize
        resolved = self.layout(
            include_redefines=include_redefines,
            include_filler=include_filler,
        )
        empty_cols = _deduplicate_names([rf.name for rf in resolved])
        chunks = self.yield_data(
            datfile,
            chunksize=eff_chunk,
            encoding=encoding,
            convert_compressed=convert_compressed,
            drop_converters=drop_converters,
            float_format=float_format,
            byteorder=byteorder,
            as_decimal=as_decimal,
            include_redefines=include_redefines,
            include_filler=include_filler,
            line_ending=line_ending,
            dbcs_encoding=dbcs_encoding,
            decimal_comma=decimal_comma,
        )
        return chunks_to_dataframe(chunks, nrows=nrows, empty_columns=empty_cols)

    def to_pandera_schema(
        self,
        include_redefines: bool = False,
        include_filler: bool = True,
        enforce_conditions: bool = False,
        coerce: bool = False,
    ) -> pa.DataFrameSchema:
        """Generate a :class:`pandera.pandas.DataFrameSchema` from this copybook.

        Parameters
        ----------
        include_redefines
            Include ``REDEFINES`` overlay items as schema columns.
        include_filler
            Include ``FILLER`` items as schema columns.
        enforce_conditions
            Add ``isin`` checks derived from level-88 condition-name values.
        coerce
            Whether the returned schema coerces column dtypes on validation.

        Returns
        -------
        pandera.pandas.DataFrameSchema
            Schema encoding column dtypes, length/range bounds, and optional
            level-88 domain checks.
        """
        resolved = self.layout(
            include_redefines=include_redefines,
            include_filler=include_filler,
        )
        col_names = _deduplicate_names([rf.name for rf in resolved])
        columns: dict[str, pa.Column] = {}

        for col_name, rf in zip(col_names, resolved, strict=True):
            field = rf.field
            checks: list[pa.Check] = []
            dtype: Any = None
            nullable = field.kind is DataCategory.NUMERIC_EDITED and not field.blank_when_zero

            if field.kind in (
                DataCategory.ALPHABETIC,
                DataCategory.ALPHANUMERIC,
                DataCategory.NATIONAL,
                DataCategory.DBCS,
                DataCategory.UTF8,
                DataCategory.BIT,
            ):
                dtype = str
                if field.kind is DataCategory.BIT:
                    bit_len = max(len(field.expanded_pic), 1)
                    checks.append(pa.Check.str_length(min_value=bit_len, max_value=bit_len))
                    checks.append(pa.Check.str_matches(r"^[01]+$"))
                else:
                    max_chars = (
                        len(field.expanded_pic)
                        if field.kind in (DataCategory.NATIONAL, DataCategory.DBCS)
                        else field.byte_length
                    )
                    checks.append(pa.Check.str_length(max_value=max_chars))
            elif field.kind in (
                DataCategory.INTEGER,
                DataCategory.BINARY,
                DataCategory.PACKED_DECIMAL,
                DataCategory.PACKED_UNSIGNED,
            ):
                dtype = float if field.decimals > 0 else int
                if field.usage in FIXED_BINARY_SIZES:
                    bits = FIXED_BINARY_SIZES[field.usage] * 8
                    if field.signed:
                        checks.append(
                            pa.Check.in_range(
                                min_value=-(1 << (bits - 1)),
                                max_value=(1 << (bits - 1)) - 1,
                            )
                        )
                    else:
                        checks.append(pa.Check.in_range(min_value=0, max_value=(1 << bits) - 1))
                elif field.usage is Usage.COMP_X:
                    bits = field.byte_length * 8
                    checks.append(pa.Check.in_range(min_value=0, max_value=(1 << bits) - 1))
                elif field.digits > 0 and field.usage is not Usage.COMP_5:
                    max_abs = (10**field.digits - 1) * (10**field.exponent)
                    min_val = -max_abs if field.signed else 0
                    checks.append(pa.Check.in_range(min_value=min_val, max_value=max_abs))
            elif field.kind in (
                DataCategory.DECIMAL,
                DataCategory.FLOAT,
                DataCategory.EXTERNAL_FLOAT,
                DataCategory.NUMERIC_EDITED,
            ):
                dtype = float
                if field.kind is DataCategory.DECIMAL and field.digits > 0:
                    max_abs = float((10**field.digits - 1) * (10**field.exponent))
                    min_val = -max_abs if field.signed else 0.0
                    checks.append(pa.Check.in_range(min_value=min_val, max_value=max_abs))
            elif field.kind in (DataCategory.POINTER, DataCategory.INDEX):
                dtype = int
                if field.kind is DataCategory.POINTER:
                    checks.append(pa.Check.greater_than_or_equal_to(0))

            if enforce_conditions and field.conditions:
                allowed = [v for cond in field.conditions for v in cond.values]
                if allowed:
                    checks.append(pa.Check.isin(allowed))

            columns[col_name] = pa.Column(dtype, checks=checks, nullable=nullable)

        return pa.DataFrameSchema(columns=columns, coerce=coerce)

    def yield_data(
        self,
        datfile: str | pathlib.Path,
        chunksize: int = 500,
        encoding: str | None = None,
        convert_compressed: bool = True,
        drop_converters: bool = False,
        float_format: Literal["ieee", "ibm"] = "ieee",
        byteorder: Literal["big", "little"] = "big",
        as_decimal: bool = False,
        include_redefines: bool = False,
        include_filler: bool = True,
        line_ending: Literal["auto", "none", "lf", "crlf"] = "auto",
        dbcs_encoding: str = "utf-16-be",
        decimal_comma: bool | None = None,
    ) -> Iterator[pd.DataFrame]:
        """Stream records from *datfile* as :class:`pandas.DataFrame` chunks.

        Parameters
        ----------
        datfile
            Path to the raw COBOL data file.
        chunksize
            Maximum number of decoded records per yielded chunk.
        encoding
            Character encoding for ``DISPLAY`` items (auto-detected if ``None``).
        convert_compressed
            Decode binary/compressed items; retain hex representation if ``False``.
        drop_converters
            Keep all items as raw decoded strings / hex without numeric casting.
        float_format
            Floating-point representation for ``COMP-1``/``COMP-2`` (``'ieee'`` or ``'ibm'``).
        byteorder
            Byte order for binary fields (``'big'`` or ``'little'``).
        as_decimal
            Preserve exact precision with :class:`decimal.Decimal` for fixed-point numbers.
        include_redefines
            Include ``REDEFINES`` overlay columns.
        include_filler
            Include ``FILLER`` columns.
        line_ending
            Record delimiter mode (``'auto'``, ``'none'``, ``'lf'``, or ``'crlf'``).
        dbcs_encoding
            Character encoding for ``PIC G`` / ``DISPLAY-1`` DBCS items.
        decimal_comma
            Override copybook ``DECIMAL-POINT IS COMMA`` detection.

        Yields
        ------
        pandas.DataFrame
            Decoded chunk of up to *chunksize* records.
        """
        if drop_converters and convert_compressed:
            logger.debug("drop_converters=True: disabling compressed field conversion.")
            convert_compressed = False

        datpath = pathlib.Path(datfile)
        resolved = self.layout(
            include_redefines=include_redefines,
            include_filler=include_filler,
        )
        rec_len = self.record_length
        if not resolved or rec_len == 0:
            return

        resolved_encoding: str = (
            encoding
            if encoding is not None
            else ("cp500" if self.has_binary_fields else predict_encoding(datpath))
        )
        col_names = _deduplicate_names([rf.name for rf in resolved])
        detected_ending = self._detect_line_ending(datpath, rec_len, line_ending)
        pad_byte = b"\x40" if is_ebcdic(resolved_encoding) else b" "
        resolved_decimal_comma = self.decimal_comma if decimal_comma is None else decimal_comma
        logger.trace(
            "Streaming {} (rec_len={}, encoding={}, line_ending={})",
            datpath,
            rec_len,
            resolved_encoding,
            detected_ending,
        )

        def _parse_record(raw_rec: bytes) -> list[Any]:
            if len(raw_rec) < rec_len:
                raw_rec = raw_rec + pad_byte * (rec_len - len(raw_rec))
            return [
                rf.field.decode_bytes(
                    raw_rec[rf.offset : rf.offset + rf.byte_length],
                    encoding=resolved_encoding,
                    float_format=float_format,
                    byteorder=byteorder,
                    as_decimal=as_decimal,
                    convert_compressed=convert_compressed,
                    drop_converters=drop_converters,
                    dbcs_encoding=dbcs_encoding,
                    decimal_comma=resolved_decimal_comma,
                )
                for rf in resolved
            ]

        rows: list[list[Any]] = []
        with datpath.open("rb") as fh:
            if detected_ending == "none":
                while True:
                    block = fh.read(rec_len)
                    if not block:
                        break
                    if len(block) < rec_len:
                        logger.warning(
                            "Truncated trailing COBOL record: expected {} bytes, got {}.",
                            rec_len,
                            len(block),
                        )
                    rows.append(_parse_record(block))
                    if len(rows) >= chunksize:
                        yield pd.DataFrame(rows, columns=col_names)
                        rows = []
            else:
                for line in fh:
                    stripped = line.rstrip(b"\r\n")
                    if not stripped:
                        continue
                    rows.append(_parse_record(stripped))
                    if len(rows) >= chunksize:
                        yield pd.DataFrame(rows, columns=col_names)
                        rows = []

        if rows:
            yield pd.DataFrame(rows, columns=col_names)

    def _detect_line_ending(
        self,
        datpath: pathlib.Path,
        rec_len: int,
        line_ending: Literal["auto", "none", "lf", "crlf"],
    ) -> Literal["none", "lf", "crlf"]:
        """Determine whether *datpath* uses fixed binary records or line terminators."""
        if line_ending != "auto":
            return line_ending
        if rec_len <= 0:
            return "lf"

        file_size = datpath.stat().st_size
        with datpath.open("rb") as fh:
            probe = fh.read(rec_len + 2)

        if len(probe) >= rec_len + 2 and probe[rec_len : rec_len + 2] == b"\r\n":
            return "crlf"
        if len(probe) >= rec_len + 1 and probe[rec_len : rec_len + 1] == b"\n":
            return "lf"

        if self.has_binary_fields:
            if file_size % rec_len == 0:
                return "none"
            if file_size % (rec_len + 1) == 0:
                return "lf"
            if file_size % (rec_len + 2) == 0:
                return "crlf"
            return "none"

        if b"\r\n" in probe:
            return "crlf"
        if b"\n" in probe:
            return "lf"
        return "none"


class GroupItem:
    """Hierarchical COBOL group item containing subordinate items."""

    def __init__(self, description: dict[str, Any]) -> None:
        self.description: dict[str, Any] = description
        self.redefinedby: list[str] = []
        self.records: list[GroupItem | ElementaryItem] = []
        self.conditions: list[ConditionName] = []
        raw_usage = (description.get("usage") or description.get("comp") or "").upper()
        self._usage: Usage | None = USAGE_ALIASES.get(raw_usage) if raw_usage else None

    def __repr__(self) -> str:
        suffix = f", {self.occurs} OCCURS" if self.occurs > 1 else ""
        return (
            f"<Group (Level {self.description.get('level')}, {self.name}, "
            f"{len(self.records)} subrecords{suffix}>"
        )

    @property
    def byte_length(self) -> int:
        """Physical byte width of a single occurrence of this group item (excluding redefines)."""
        return sum(rec.byte_length * rec.occurs for rec in self.records if rec.redefines is None)

    @property
    def level(self) -> int:
        """COBOL level number."""
        return int(self.description["level"])

    @property
    def name(self) -> str:
        """Group item name."""
        return str(self.description.get("name") or "FILLER")

    @property
    def occurs(self) -> int:
        """Repetition count from ``OCCURS`` (``1`` when non-repeating)."""
        occ = self.description.get("occurs")
        return int(occ) if occ is not None else 1

    @property
    def redefines(self) -> str | None:
        """Name of the sibling item this group redefines, or ``None``."""
        val = self.description.get("redefines")
        return str(val) if val else None

    @property
    def usage(self) -> Usage | None:
        """Optional group-level ``USAGE`` inherited by subordinate elementary items."""
        return self._usage

    def append(self, level: int, record: GroupItem | ElementaryItem) -> None:
        """Insert *record* at the deepest nested subgroup whose level is ``< level``.

        Parameters
        ----------
        level
            COBOL level number of the item being inserted.
        record
            Group or elementary item to append.
        """
        for rec in reversed(self.records):
            if isinstance(rec, GroupItem) and rec.level < level:
                rec.append(level, record)
                return
        self.records.append(record)

    def find_record(self, name: str) -> GroupItem | ElementaryItem | None:
        """Depth-first search for the first subordinate item named *name*.

        Parameters
        ----------
        name
            Exact COBOL item name to search for.

        Returns
        -------
        GroupItem | ElementaryItem | None
            First matching subordinate item, or ``None`` if not found.
        """
        for gf in self.records:
            if gf.name == name:
                return gf
            if isinstance(gf, GroupItem):
                found = gf.find_record(name)
                if found is not None:
                    return found
        return None

    def pic_to_fwf_kwargs(self, convert_compressed: bool = True) -> list[dict[str, Any]]:
        """Return flattened :func:`pandas.read_fwf` column descriptors for this group item.

        Parameters
        ----------
        convert_compressed
            Attach byte-level decoders for binary/compressed items when ``True``.

        Returns
        -------
        list[dict[str, Any]]
            Column descriptor dictionaries expanded across any ``OCCURS`` repetitions.
        """
        dtypes: list[dict[str, Any]] = []
        for rec in self.records:
            if rec.redefines is not None:
                continue
            dtypes.extend(rec.pic_to_fwf_kwargs(convert_compressed=convert_compressed))

        if self.occurs == 1:
            return dtypes

        expanded: list[dict[str, Any]] = []
        for n in range(self.occurs):
            for dtype in dtypes:
                entry = copy.deepcopy(dtype)
                entry["name"] = _occurs_name(entry["name"], n, self.occurs)
                expanded.append(entry)
        return expanded


class ElementaryItem:
    """COBOL elementary data item carrying a ``PICTURE`` or self-sized ``USAGE``."""

    def __init__(self, description: dict[str, Any]) -> None:
        self.description: dict[str, Any] = description
        self.redefinedby: list[str] = []
        self.conditions: list[ConditionName] = []

        raw_usage = (description.get("usage") or description.get("comp") or "DISPLAY").upper()
        self._usage: Usage = USAGE_ALIASES.get(raw_usage, Usage.DISPLAY)

        raw_pic = (description.get("pic") or "").strip()
        self._expanded_pic: str = expand_pic(raw_pic) if raw_pic else ""
        if self._usage is Usage.DISPLAY and self._expanded_pic:
            if PIC_NATIONAL_ONLY.match(self._expanded_pic):
                self._usage = Usage.NATIONAL
            elif PIC_UTF8_ONLY.match(self._expanded_pic):
                self._usage = Usage.UTF_8
            elif PIC_DBCS_ONLY.match(self._expanded_pic):
                self._usage = Usage.DISPLAY_1
            elif PIC_BIT_ONLY.match(self._expanded_pic):
                self._usage = Usage.BIT

        raw_bl = description.get("byte_length")
        self._explicit_byte_length: int | None = int(raw_bl) if raw_bl is not None else None

        bin_qual = (description.get("binary_sign_qualifier") or "").upper()
        if self._usage in FIXED_BINARY_SIZES:
            self._signed = bin_qual != "UNSIGNED"
        elif self._usage in (Usage.COMP_6, Usage.COMP_X):
            self._signed = False
        else:
            self._signed = self._expanded_pic.startswith("S")
        self._sign_mode: SignMode = self._resolve_sign_mode(description)
        self._exponent: int = (
            compute_decimal_exponent(self._expanded_pic)
            if self._expanded_pic and PIC_NUMERIC_PURE.match(self._expanded_pic)
            else 0
        )

    @classmethod
    def from_clause(cls, statement: str) -> ElementaryItem:
        """Construct an :class:`ElementaryItem` from a single COBOL declaration line.

        Parameters
        ----------
        statement
            Single COBOL data description clause (with or without trailing period).

        Returns
        -------
        ElementaryItem
            Parsed elementary item.
        """
        cleaned = statement.strip().rstrip(".")
        desc = parse_statement(cleaned)
        if desc is None:
            raise ValueError(f"Could not parse COBOL elementary item: {statement!r}")
        return cls(desc)

    def __repr__(self) -> str:
        pic_display = (self.description.get("pic") or "").strip()
        detail = pic_display or self._usage.value
        if pic_display and self._usage is not Usage.DISPLAY:
            detail = f"{pic_display} {self._usage.value}"
        suffix = f", {self.occurs} OCCURS" if self.occurs > 1 else ""
        return f"<Field (Level {self.description.get('level')}, {self.name}, {detail}{suffix}>"

    @property
    def blank_when_zero(self) -> bool:
        """``True`` if ``BLANK WHEN ZERO`` was declared."""
        return bool(self.description.get("blank_when_zero", False))

    @property
    def byte_length(self) -> int:
        """Physical byte width of a single occurrence of this elementary item."""
        if self._explicit_byte_length is not None:
            return self._explicit_byte_length
        if self._usage in FIXED_BINARY_SIZES:
            return FIXED_BINARY_SIZES[self._usage]
        if self._usage in (Usage.COMP_1, Usage.FLOAT_SHORT, Usage.INDEX, Usage.POINTER):
            return 4
        if self._usage in (
            Usage.COMP_2,
            Usage.FLOAT_LONG,
            Usage.PROCEDURE_POINTER,
            Usage.FUNCTION_POINTER,
        ):
            return 8
        if self._usage is Usage.COMP_3:
            return (self.digits // 2) + 1
        if self._usage is Usage.COMP_6:
            return (self.digits + 1) // 2
        if self._usage is Usage.COMP_X:
            if "X" in self._expanded_pic:
                return self._expanded_pic.count("X")
            d = max(self.digits, 1)
            return ((10**d - 1).bit_length() + 7) // 8
        if self._usage in (Usage.COMP, Usage.COMP_5):
            d = self.digits
            if d <= 4:
                return 2
            if d <= 9:
                return 4
            if d <= 18:
                return 8
            return 16
        if self._usage in (Usage.NATIONAL, Usage.DISPLAY_1):
            return len(self._expanded_pic) * 2
        if self._usage is Usage.UTF_8:
            return len(self._expanded_pic) * 4
        if self._usage is Usage.BIT:
            return (max(len(self._expanded_pic), 1) + 7) // 8

        physical = self._expanded_pic.replace("S", "").replace("V", "").replace("P", "")
        extra = (
            1 if self._sign_mode in (SignMode.LEADING_SEPARATE, SignMode.TRAILING_SEPARATE) else 0
        )
        return len(physical) + extra

    @property
    def decimals(self) -> int:
        """Number of implied fractional decimal digits."""
        return max(0, -self._exponent)

    @property
    def digits(self) -> int:
        """Total count of ``9`` digit positions in the ``PIC`` clause."""
        return self._expanded_pic.count("9")

    @property
    def expanded_pic(self) -> str:
        """Fully expanded uppercase ``PIC`` string."""
        return self._expanded_pic

    @property
    def exponent(self) -> int:
        """Base-10 scaling exponent from ``V`` and ``P`` symbols."""
        return self._exponent

    @property
    def is_binary(self) -> bool:
        """``True`` if the item uses binary, packed, float, pointer, index, or wide storage."""
        return self._usage in BINARY_USAGES

    @property
    def is_filler(self) -> bool:
        """``True`` if this item is a ``FILLER`` item."""
        return self.name.upper() == "FILLER"

    @property
    def kind(self) -> DataCategory:
        """COBOL :class:`~dataspector.coboller.constants.DataCategory` of this elementary item."""
        if self._usage in (Usage.COMP_1, Usage.COMP_2, Usage.FLOAT_SHORT, Usage.FLOAT_LONG):
            return DataCategory.FLOAT
        if self._usage in (Usage.POINTER, Usage.PROCEDURE_POINTER, Usage.FUNCTION_POINTER):
            return DataCategory.POINTER
        if self._usage is Usage.INDEX:
            return DataCategory.INDEX
        if self._usage is Usage.COMP_3:
            return DataCategory.PACKED_DECIMAL
        if self._usage is Usage.COMP_6:
            return DataCategory.PACKED_UNSIGNED
        if self._usage in (Usage.COMP, Usage.COMP_5, Usage.COMP_X) or (
            self._usage in FIXED_BINARY_SIZES
        ):
            return DataCategory.BINARY
        if self._usage is Usage.NATIONAL:
            return DataCategory.NATIONAL
        if self._usage is Usage.UTF_8:
            return DataCategory.UTF8
        if self._usage is Usage.DISPLAY_1:
            return DataCategory.DBCS
        if self._usage is Usage.BIT:
            return DataCategory.BIT

        pic = self._expanded_pic
        if not pic:
            return DataCategory.ALPHANUMERIC
        if PIC_EXTERNAL_FLOAT.match(pic):
            return DataCategory.EXTERNAL_FLOAT
        if PIC_NUMERIC_PURE.match(pic):
            return DataCategory.DECIMAL if self._exponent < 0 else DataCategory.INTEGER
        if PIC_ALPHA_ONLY.match(pic):
            return DataCategory.ALPHABETIC
        if "X" not in pic and "A" not in pic and PIC_EDITED_MARKERS.search(pic):
            return DataCategory.NUMERIC_EDITED
        return DataCategory.ALPHANUMERIC

    @property
    def level(self) -> int:
        """COBOL level number."""
        return int(self.description["level"])

    @property
    def name(self) -> str:
        """Item name (``'FILLER'`` if unnamed)."""
        return str(self.description.get("name") or "FILLER")

    @property
    def occurs(self) -> int:
        """Repetition count from ``OCCURS`` (``1`` when non-repeating)."""
        occ = self.description.get("occurs")
        return int(occ) if occ is not None else 1

    @property
    def redefines(self) -> str | None:
        """Name of the sibling item this item redefines, or ``None``."""
        val = self.description.get("redefines")
        return str(val) if val else None

    @property
    def sign_mode(self) -> SignMode:
        """Sign encoding mode for ``USAGE DISPLAY`` signed numeric items."""
        return self._sign_mode

    @property
    def signed(self) -> bool:
        """``True`` if this elementary item is signed."""
        if self._usage in (
            Usage.COMP_1,
            Usage.COMP_2,
            Usage.FLOAT_SHORT,
            Usage.FLOAT_LONG,
            Usage.INDEX,
        ):
            return True
        return self._signed

    @property
    def usage(self) -> Usage:
        """Normalized :class:`~dataspector.coboller.constants.Usage` storage representation."""
        return self._usage

    def decode_bytes(
        self,
        raw: bytes,
        encoding: str = "ascii",
        float_format: Literal["ieee", "ibm"] = "ieee",
        byteorder: Literal["big", "little"] = "big",
        as_decimal: bool = False,
        convert_compressed: bool = True,
        drop_converters: bool = False,
        dbcs_encoding: str = "utf-16-be",
        decimal_comma: bool = False,
    ) -> Any:
        """Decode *raw* bytes for this elementary item into a Python value.

        Parameters
        ----------
        raw
            Byte slice corresponding to this elementary item.
        encoding
            Character encoding for ``DISPLAY`` items (e.g. ``'ascii'``, ``'cp500'``).
        float_format
            Floating-point representation for ``COMP-1``/``COMP-2`` (``'ieee'`` or ``'ibm'``).
        byteorder
            Byte order for binary and UTF-16 items (``'big'`` or ``'little'``).
        as_decimal
            Return :class:`decimal.Decimal` instead of ``float``/``int`` for fixed-point numbers.
        convert_compressed
            Decode binary/packed items when ``True``; return hex strings when ``False``.
        drop_converters
            Return raw decoded text or hex without numeric conversion.
        dbcs_encoding
            Character encoding for ``PIC G`` / ``DISPLAY-1`` DBCS items.
        decimal_comma
            Interpret commas as decimal separators per ``DECIMAL-POINT IS COMMA``.

        Returns
        -------
        Any
            Decoded Python scalar (``str``, ``int``, ``float``, ``Decimal``, or ``None``).
        """
        if self.is_binary:
            if drop_converters or not convert_compressed:
                if self._usage is Usage.NATIONAL:
                    return raw.decode("utf-16-be" if byteorder == "big" else "utf-16-le").rstrip()
                if self._usage is Usage.UTF_8:
                    return raw.decode("utf-8", errors="replace").rstrip()
                if self._usage is Usage.DISPLAY_1:
                    return raw.decode(dbcs_encoding, errors="replace").rstrip(" \u3000")
                return raw.hex()
            if self._usage is Usage.COMP_3:
                return comp3_unpack(raw, exponent=self._exponent, as_decimal=as_decimal)
            if self._usage is Usage.COMP_6:
                return comp6_unpack(raw, exponent=self._exponent, as_decimal=as_decimal)
            if self._usage in (Usage.COMP, Usage.COMP_5, Usage.COMP_X) or (
                self._usage in FIXED_BINARY_SIZES
            ):
                return comp_unpack(
                    raw,
                    signed=self._signed,
                    byteorder=byteorder,
                    exponent=self._exponent,
                    as_decimal=as_decimal,
                )
            if self._usage in (Usage.COMP_1, Usage.COMP_2):
                return comp_float_unpack(raw, float_format=float_format, byteorder=byteorder)
            if self._usage in (Usage.FLOAT_SHORT, Usage.FLOAT_LONG):
                return comp_float_unpack(raw, float_format="ieee", byteorder=byteorder)
            if self._usage in (Usage.POINTER, Usage.PROCEDURE_POINTER, Usage.FUNCTION_POINTER):
                return int.from_bytes(raw, byteorder=byteorder, signed=False)
            if self._usage is Usage.INDEX:
                return int.from_bytes(raw, byteorder=byteorder, signed=True)
            if self._usage is Usage.NATIONAL:
                return raw.decode("utf-16-be" if byteorder == "big" else "utf-16-le").rstrip()
            if self._usage is Usage.UTF_8:
                return raw.decode("utf-8", errors="replace").rstrip()
            if self._usage is Usage.DISPLAY_1:
                return raw.decode(dbcs_encoding, errors="replace").rstrip(" \u3000")
            if self._usage is Usage.BIT:
                return bit_unpack(raw, max(len(self._expanded_pic), 1))

        if drop_converters:
            return raw.decode(encoding, errors="replace").rstrip()

        kind = self.kind
        if kind is DataCategory.EXTERNAL_FLOAT:
            return external_float_unpack(
                raw,
                expanded_pic=self._expanded_pic,
                encoding=encoding,
                decimal_comma=decimal_comma,
            )
        if kind in (DataCategory.INTEGER, DataCategory.DECIMAL):
            return zoned_unpack(
                raw,
                encoding=encoding,
                signed=self._signed,
                sign_mode=self._sign_mode,
                exponent=self._exponent,
                as_decimal=as_decimal,
            )
        if kind is DataCategory.NUMERIC_EDITED:
            text = raw.decode(encoding, errors="replace")
            if "/" in self._expanded_pic:
                return text.strip()
            return parse_numeric_edited(
                text,
                blank_when_zero=self.blank_when_zero,
                decimal_comma=decimal_comma,
            )
        return raw.decode(encoding, errors="replace").rstrip()

    def pic_to_fwf_kwargs(self, convert_compressed: bool = True) -> list[dict[str, Any]]:
        """Convert this item into column descriptor dicts for :func:`pandas.read_fwf`.

        Parameters
        ----------
        convert_compressed
            Attach a byte-level converter for binary/compressed storage when ``True``.

        Returns
        -------
        list[dict[str, Any]]
            One descriptor per ``OCCURS`` repetition containing ``name``,
            ``pic``, and an optional ``converter`` callable.
        """
        dtype: dict[str, Any] = {"name": self.name, "pic": self._expanded_pic}
        if self.is_binary:
            if convert_compressed:
                dtype["converter"] = lambda val, f=self: f.decode_bytes(
                    val.encode("latin-1") if isinstance(val, str) else val
                )
            else:
                logger.warning(
                    "{} uses binary storage ({}); keeping raw representation for text FWF.",
                    self.name,
                    self._usage.value,
                )
        else:
            conv = self._make_text_converter()
            if conv is not None:
                dtype["converter"] = conv

        if self.occurs == 1:
            return [dtype]

        return [
            {**copy.deepcopy(dtype), "name": _occurs_name(self.name, n, self.occurs)}
            for n in range(self.occurs)
        ]

    def _make_text_converter(self) -> Callable[[str], Any] | None:
        """Build a string converter callable for :func:`pandas.read_fwf`."""
        kind = self.kind
        if kind in (DataCategory.INTEGER, DataCategory.DECIMAL):
            signed = self._signed
            sign_mode = self._sign_mode
            exponent = self._exponent

            def _convert_zoned(val: str) -> int | float | Decimal:
                return zoned_unpack(
                    val.encode("ascii"),
                    encoding="ascii",
                    signed=signed,
                    sign_mode=sign_mode,
                    exponent=exponent,
                )

            if not signed and exponent == 0:
                return int
            return _convert_zoned

        if kind is DataCategory.EXTERNAL_FLOAT:
            pic = self._expanded_pic

            def _convert_ext_float(val: str) -> float:
                return external_float_unpack(val.encode("ascii"), expanded_pic=pic)

            return _convert_ext_float

        if kind is DataCategory.NUMERIC_EDITED and "/" not in self._expanded_pic:
            bwz = self.blank_when_zero

            def _convert_edited(val: str) -> float | None:
                return parse_numeric_edited(val, blank_when_zero=bwz)

            return _convert_edited

        return None

    def _resolve_sign_mode(self, description: dict[str, Any]) -> SignMode:
        if not self._signed or self._usage is not Usage.DISPLAY:
            return SignMode.NONE
        raw_sign = description.get("sign_mode")
        if isinstance(raw_sign, SignMode):
            return raw_sign
        return SignMode.TRAILING_OVERPUNCH


def parse_copybook(rawtext: str | pathlib.Path) -> list[GroupItem | ElementaryItem]:
    """Parse COBOL copybook source text or a file path into a record hierarchy.

    Parameters
    ----------
    rawtext
        Raw copybook text or path to a copybook file.

    Returns
    -------
    list[GroupItem | ElementaryItem]
        Top-level record definitions parsed from the copybook.
    """
    if isinstance(rawtext, pathlib.Path):
        text = rawtext.read_text(encoding="utf-8", errors="replace")
    elif "\n" not in rawtext and "\r" not in rawtext and len(rawtext) < 256:
        maybe_path = pathlib.Path(rawtext)
        text = (
            maybe_path.read_text(encoding="utf-8", errors="replace")
            if maybe_path.exists()
            else rawtext
        )
    else:
        text = rawtext

    records: list[GroupItem | ElementaryItem] = []
    last_item: GroupItem | ElementaryItem | None = None

    for stmt in extract_statements(text):
        desc = parse_statement(stmt)
        if desc is None:
            continue

        level = int(desc["level"])

        if level == 88:
            if last_item is not None:
                raw_val = desc.get("value") or ""
                last_item.conditions.append(
                    ConditionName(
                        name=desc["name"],
                        raw_value=raw_val,
                        values=parse_condition_values(raw_val),
                    )
                )
            continue

        if level == 66:
            continue

        parent = _find_parent_group(records, level) if level not in (1, 77) else None

        raw_usage = desc.get("usage")
        usage_enum = USAGE_ALIASES.get(raw_usage.upper()) if raw_usage else None
        if usage_enum is None and parent is not None and parent.usage is not None:
            desc["usage"] = parent.usage.value
            desc["comp"] = parent.usage.value
            usage_enum = parent.usage

        is_elementary = (desc.get("pic") is not None) or (usage_enum in SELF_SIZED_USAGES)
        node: GroupItem | ElementaryItem = (
            ElementaryItem(desc) if is_elementary else GroupItem(desc)
        )

        if level in (1, 77) or parent is None:
            records.append(node)
        else:
            parent.records.append(node)

        if desc.get("redefines"):
            _register_redefines(records, parent, str(desc["redefines"]), node.name)

        last_item = node

    return records


# Backward-compatible aliases
CopyBook = Copybook
Group = GroupItem
Field = ElementaryItem
Condition = ConditionName
ResolvedField = ResolvedItem


# ---------------------------------------------------------------------------
# Internal Layout & Tree Helpers
# ---------------------------------------------------------------------------


def _deduplicate_names(names: list[str]) -> list[str]:
    """Ensure unique DataFrame column names while preserving first occurrences."""
    counts: dict[str, int] = {}
    unique: list[str] = []
    for name in names:
        idx = counts.get(name, 0)
        counts[name] = idx + 1
        unique.append(name if idx == 0 else f"{name}_{idx}")
    return unique


def _find_parent_group(
    records: list[GroupItem | ElementaryItem],
    level: int,
) -> GroupItem | None:
    """Return the deepest open :class:`GroupItem` whose level is strictly less than *level*."""
    for rec in reversed(records):
        if isinstance(rec, GroupItem) and rec.level < level:
            deeper = _find_parent_group(rec.records, level)
            return deeper if deeper is not None else rec
    return None


def _occurs_name(base: str, index: int, total: int) -> str:
    """Format an ``OCCURS`` column name (index 0 keeps the base name)."""
    if index == 0:
        return base
    width = 3 if total >= 100 else 2
    return f"{base}-{index:0{width}d}"


def _register_redefines(
    records: list[GroupItem | ElementaryItem],
    parent: GroupItem | None,
    target_name: str,
    redefiner_name: str,
) -> None:
    """Record *redefiner_name* in the ``redefinedby`` list of *target_name*."""
    siblings = parent.records if parent is not None else records
    for rec in reversed(siblings):
        if rec.name == target_name:
            rec.redefinedby.append(redefiner_name)
            return
