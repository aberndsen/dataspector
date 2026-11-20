"""Comprehensive unit and integration tests for :mod:`dataspector.coboller`."""

from __future__ import annotations

import pathlib
from decimal import Decimal

import pandas as pd
import pandera.pandas as pa
import pytest
from assertpy import assert_that
from pandera.errors import SchemaError, SchemaErrors

from dataspector import coboller
from dataspector.coboller import (
    CopyBook,
    Field,
    FieldKind,
    Group,
    SignMode,
    Usage,
    bit_pack,
    bit_unpack,
    comp3_pack,
    comp3_unpack,
    comp3decompress,
    comp6_pack,
    comp6_unpack,
    comp_float_pack,
    comp_float_unpack,
    comp_pack,
    comp_unpack,
    expand_pic,
    external_float_unpack,
    float_to_ibm_hfp,
    ibm_hfp_to_float,
    parse_copybook,
    parse_numeric_edited,
    predict_encoding,
    zoned_pack,
    zoned_unpack,
)

# ---------------------------------------------------------------------------
# PIC Expansion & Scaling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9(7)", "9999999"),
        ("x(4)", "XXXX"),
        ("S9(5)V9(2)", "S99999V99"),
        ("Z(3),999.99-", "ZZZ,999.99-"),
        ("9(3)P(2)", "999PP"),
        ("N(4)", "NNNN"),
    ],
)
def test_expand_pic(raw: str, expected: str) -> None:
    """expand_pic resolves repeat groups and normalizes case."""
    assert_that(expand_pic(raw)).is_equal_to(expected)


# ---------------------------------------------------------------------------
# COMP-3 Packed Decimal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "digits", "decimals", "signed", "expected_len"),
    [
        (0, 3, 0, True, 2),
        (49, 3, 0, True, 2),
        (-49, 3, 0, True, 2),
        (123456.78, 9, 2, True, 5),
        (-987654.32, 9, 2, True, 5),
        (1000000.00, 11, 2, True, 6),
        (42, 4, 0, False, 3),
    ],
)
def test_comp3_roundtrip(
    value: int | float,
    digits: int,
    decimals: int,
    signed: bool,
    expected_len: int,
) -> None:
    """comp3_pack and comp3_unpack round-trip signed/unsigned integers and decimals."""
    packed = comp3_pack(value, digits, decimals=decimals, signed=signed)
    assert_that(packed).is_length(expected_len)
    unpacked = comp3_unpack(packed, decimals=decimals)
    assert_that(unpacked).is_equal_to(value)
    assert_that(comp3decompress(packed, decimals=decimals)).is_equal_to(value)


def test_comp3_as_decimal_and_positive_scaling() -> None:
    """comp3_unpack preserves exact Decimal precision and positive P scaling."""
    packed = comp3_pack(Decimal("123.45"), 5, decimals=2)
    assert_that(comp3_unpack(packed, decimals=2, as_decimal=True)).is_equal_to(Decimal("123.45"))

    # PIC S9(3)PP COMP-3: stored digits 123 scaled by 10^2 = 12300
    packed_scaled = comp3_pack(12300, 3, exponent=2)
    assert_that(comp3_unpack(packed_scaled, exponent=2)).is_equal_to(12300)


def test_comp3_errors() -> None:
    """comp3_unpack and comp3_pack reject invalid nibbles, signs, and overflows."""
    with pytest.raises(ValueError, match="empty"):
        comp3_unpack(b"")
    with pytest.raises(ValueError, match="BCD nibble"):
        comp3_unpack(b"\xab\x1c")
    with pytest.raises(ValueError, match="final COMP-3"):
        comp3_unpack(b"\x12\xfc")
    with pytest.raises(ValueError, match="sign nibble"):
        comp3_unpack(b"\x12\x30")
    with pytest.raises(ValueError, match="unsigned"):
        comp3_pack(-1, 3, signed=False)
    with pytest.raises(ValueError, match="exceeds"):
        comp3_pack(99999, 3, signed=True)


# ---------------------------------------------------------------------------
# Binary Integers (COMP / COMP-4 / COMP-5 / BINARY)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("byteorder", ["big", "little"])
@pytest.mark.parametrize(
    ("value", "width", "signed", "exp"),
    [
        (1234, 2, True, 0),
        (-1234, 2, True, 0),
        (65000, 2, False, 0),
        (-123456789, 4, True, 0),
        (12345678901234, 8, True, 0),
        (-12345.67, 4, True, -2),
    ],
)
def test_comp_binary_roundtrip(
    value: int | float,
    width: int,
    signed: bool,
    exp: int,
    byteorder: str,
) -> None:
    """comp_pack and comp_unpack support 2/4/8-byte big and little endian values."""
    bo = "big" if byteorder == "big" else "little"
    packed = comp_pack(value, width, signed=signed, byteorder=bo, exponent=exp)
    assert_that(packed).is_length(width)
    assert_that(comp_unpack(packed, signed=signed, byteorder=bo, exponent=exp)).is_equal_to(value)


def test_comp_unpack_empty_raises() -> None:
    """comp_unpack raises ValueError on empty input."""
    with pytest.raises(ValueError, match="empty"):
        comp_unpack(b"")


# ---------------------------------------------------------------------------
# Floating Point (COMP-1 / COMP-2: IEEE-754 & IBM HFP)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [4, 8])
@pytest.mark.parametrize("byteorder", ["big", "little"])
def test_comp_float_ieee_roundtrip(size: int, byteorder: str) -> None:
    """comp_float_pack/unpack handle 32-bit COMP-1 and 64-bit COMP-2 IEEE-754 floats."""
    sz = 4 if size == 4 else 8
    bo = "big" if byteorder == "big" else "little"
    raw = comp_float_pack(-3.125, size=sz, float_format="ieee", byteorder=bo)
    assert_that(raw).is_length(sz)
    assert_that(comp_float_unpack(raw, float_format="ieee", byteorder=bo)).is_close_to(-3.125, 1e-6)


@pytest.mark.parametrize("size", [4, 8])
@pytest.mark.parametrize("value", [0.0, 1.0, -1.0, 0.5, 123.75, -0.00390625, 1e6])
def test_ibm_hfp_roundtrip(size: int, value: float) -> None:
    """IBM Hexadecimal Floating-Point (HFP) encodes and decodes accurately."""
    sz = 4 if size == 4 else 8
    raw = float_to_ibm_hfp(value, size=sz)
    assert_that(raw).is_length(sz)
    decoded = ibm_hfp_to_float(raw)
    tol = 1e-5 if sz == 4 else 1e-12
    assert_that(decoded).is_close_to(value, max(tol, abs(value) * tol))
    assert_that(comp_float_unpack(raw, float_format="ibm")).is_close_to(
        value, max(tol, abs(value) * tol)
    )


def test_ibm_hfp_known_vector_and_errors() -> None:
    """Verify known IBM HFP bit pattern for -118.625 and error handling."""
    # IBM HFP 32-bit for -118.625: sign=1, exp=+2 (0x42 -> 0xC2), frac=0x76A000
    assert_that(ibm_hfp_to_float(b"\xc2\x76\xa0\x00")).is_equal_to(-118.625)
    assert_that(ibm_hfp_to_float(b"\x41\x00\x00\x00")).is_equal_to(0.0)
    with pytest.raises(ValueError, match="4 or 8"):
        ibm_hfp_to_float(b"\x00\x00")
    with pytest.raises(ValueError, match="4 or 8"):
        comp_float_unpack(b"\x00\x00\x00")


# ---------------------------------------------------------------------------
# Zoned Decimal (ASCII, EBCDIC, Overpunch, Separate Sign)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("encoding", ["ascii", "cp500", "cp037"])
@pytest.mark.parametrize(
    "sign_mode",
    [
        SignMode.TRAILING_OVERPUNCH,
        SignMode.LEADING_OVERPUNCH,
        SignMode.TRAILING_SEPARATE,
        SignMode.LEADING_SEPARATE,
    ],
)
@pytest.mark.parametrize("value", [0.0, 123.45, -123.45, -0.05])
def test_zoned_signed_roundtrip(encoding: str, sign_mode: SignMode, value: float) -> None:
    """zoned_pack and zoned_unpack handle ASCII & EBCDIC overpunch and separate signs."""
    raw = zoned_pack(value, 5, encoding=encoding, signed=True, sign_mode=sign_mode, exponent=-2)
    expected_len = 6 if sign_mode in (SignMode.LEADING_SEPARATE, SignMode.TRAILING_SEPARATE) else 5
    assert_that(raw).is_length(expected_len)
    decoded = zoned_unpack(raw, encoding=encoding, signed=True, sign_mode=sign_mode, exponent=-2)
    assert_that(decoded).is_equal_to(value)


def test_zoned_microfocus_and_blank_handling() -> None:
    """zoned_unpack handles Micro Focus negative overpunch, blanks, and scaling."""
    # Micro Focus trailing negative: '123r' -> -1232
    assert_that(
        zoned_unpack(b"123r", encoding="ascii", signed=True, sign_mode=SignMode.TRAILING_OVERPUNCH)
    ).is_equal_to(-1232)
    # Blank EBCDIC and ASCII fields decode to 0
    assert_that(zoned_unpack(b"\x40\x40\x40", encoding="cp500")).is_equal_to(0)
    assert_that(zoned_unpack(b"   ", encoding="ascii")).is_equal_to(0)
    # Plain signed ASCII strings
    assert_that(zoned_unpack(b"-0450", encoding="ascii", signed=True, exponent=-2)).is_equal_to(
        -4.50
    )
    assert_that(zoned_unpack(b"0450-", encoding="ascii", signed=True, exponent=-2)).is_equal_to(
        -4.50
    )
    with pytest.raises(ValueError, match="empty"):
        zoned_unpack(b"")


# ---------------------------------------------------------------------------
# Numeric-Edited Display Parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "bwz", "expected"),
    [
        ("  $1,234.50", False, 1234.50),
        ("  $1,234.50-", False, -1234.50),
        ("***987.65CR", False, -987.65),
        ("  42.00DB", False, -42.00),
        ("+0012.34", False, 12.34),
        ("   -5.50", False, -5.50),
        ("        ", False, None),
        ("        ", True, 0.0),
    ],
)
def test_parse_numeric_edited(text: str, bwz: bool, expected: float | None) -> None:
    """parse_numeric_edited decodes currency, suppression, signs, CR/DB, and blanks."""
    assert_that(parse_numeric_edited(text, blank_when_zero=bwz)).is_equal_to(expected)


# ---------------------------------------------------------------------------
# CopyBook Parsing, Structural Features & Existing Samples
# ---------------------------------------------------------------------------


def test_cobol_sample_students_fields_repr_and_values(data_dir: pathlib.Path) -> None:
    """CopyBook parses sample_cobol_students.cbl and yields typed student records."""
    cbl = CopyBook(data_dir / "sample_cobol_students.cbl")
    expected_fields = [
        "StudentId",
        "Surname",
        "Initials",
        "YOBirth",
        "MOBirth",
        "DOBirth",
        "CourseCode",
        "Gender",
    ]
    assert_that(cbl.exists).is_true()
    assert_that(cbl.fields).is_equal_to(expected_fields)
    assert_that(cbl.columns).is_equal_to(expected_fields)
    assert_that(cbl.record_length).is_equal_to(30)
    root_rec = cbl.records[0]
    assert isinstance(root_rec, Group)
    assert_that(str(root_rec)).is_equal_to("<Group (Level 01, StudentDetails, 5 subrecords>")
    assert_that(str(root_rec.records[0])).is_equal_to("<Field (Level 02, StudentId, 9(7)>")

    for name in ["StudentName", *expected_fields]:
        assert_that(cbl.find_record(name)).is_not_none()
    assert_that(cbl.find_record("DOES-NOT-EXIST")).is_none()

    df = next(cbl.yield_data(data_dir / "sample_cobol_students.dat"))
    assert_that(df).is_length(32)
    assert_that(set(df["Gender"].unique())).is_equal_to({"M", "F"})
    assert_that(int(df["StudentId"].iloc[0])).is_equal_to(8712351)
    assert_that(df["Surname"].iloc[0]).is_equal_to("SMITH")


def test_cobol_pic_to_fwf_kwargs(data_dir: pathlib.Path) -> None:
    """pic_to_fwf_kwargs produces accurate colspecs, names, and converters."""
    cbl = CopyBook(data_dir / "sample_cobol_students.cbl")
    fwf = cbl.pic_to_fwf_kwargs()
    assert_that(fwf["colspecs"]).is_equal_to(
        [(0, 7), (7, 15), (15, 17), (17, 21), (21, 23), (23, 25), (25, 29), (29, 30)]
    )
    assert_that(list(fwf["converters"].keys())).is_equal_to([0, 3, 4, 5])

    cbl_multi = CopyBook(data_dir / "sample_cobol_multiplesubgroups.cbl")
    assert_that(cbl_multi.fields).is_equal_to(
        [
            "COMPANY-NAME",
            "LAST-NAME",
            "FIRST-NAME",
            "LAST-NAME-01",
            "FIRST-NAME-01",
            "LAST-NAME",
            "FIRST-NAME",
            "TITLE",
            "LAST-NAME",
            "FIRST-NAME",
            "ADDRESS",
            "CITY",
            "STATE",
            "ZIP",
        ]
    )
    president_grp = cbl_multi.find_record("PRESIDENT")
    assert isinstance(president_grp, Group)
    assert_that(president_grp.pic_to_fwf_kwargs()).is_equal_to(
        [
            {"name": "LAST-NAME", "pic": "XXXXXXXXXXXXXXX"},
            {"name": "FIRST-NAME", "pic": "XXXXXXXX"},
            {"name": "LAST-NAME-01", "pic": "XXXXXXXXXXXXXXX"},
            {"name": "FIRST-NAME-01", "pic": "XXXXXXXX"},
        ]
    )


def test_cobol_level88_and_studentsorig(data_dir: pathlib.Path) -> None:
    """Level-88 conditions attach to parent items without adding data columns."""
    cbl = CopyBook(data_dir / "sample_cobol_studentsorig.cbl")
    assert_that(cbl.records).is_length(3)
    assert_that(cbl.records[0].conditions).is_length(1)
    assert_that(cbl.records[0].conditions[0].name).is_equal_to("EndOfStudentFile")


def test_cobol_all_extended_data_types_and_clauses(tmp_path: pathlib.Path) -> None:
    """Parse and decode every supported COBOL data type in one end-to-end record."""
    copybook_text = """
000100* FIXED-FORMAT COMMENT WITH SEQUENCE NUMBERS                      00000001
      / PAGE EJECT COMMENT
       01  COMPREHENSIVE-REC.
           05  ALPHA-CODE        PIC A(4).
           05  TEXT-VAL          PIC X(6).
           05  NAT-NAME          PIC N(3) USAGE NATIONAL.
           05  FILLER            PIC XX.
           05                    PIC X(2). *> unnamed filler
           05  INT-UNSIGNED      PIC 9(4).
           05  DEC-IMPLIED       PIC 9(3)V99.
           05  SCALED-BIG        PIC 9(2)PP.
           05  SCALED-SMALL      PIC VPP9(2).
           05  LEAD-SEP          PIC S9(3)V9 SIGN IS LEADING SEPARATE CHARACTER.
           05  TRAIL-SEP         PIC S9(3) SIGN TRAILING SEPARATE.
           05  EDITED-AMT        PIC $$$,$$9.99- BLANK WHEN ZERO.
           05  EDITED-DATE       PIC 99/99/9999.
           05  BIN-GROUP         USAGE BINARY.
               10  BIN-HALF      PIC S9(4).
               10  BIN-FULL      PIC S9(9).
               10  BIN-DOUBLE    PIC S9(18).
           05  NATIVE-BIN        PIC S9(4) COMP-5.
           05  PACKED-VAL        PIC S9(5)V99 PACKED-DECIMAL.
           05  FLT-SINGLE        USAGE IS COMP-1.
           05  FLT-DOUBLE        COMP-2.
           05  PTR-VAL           USAGE POINTER.
           05  IDX-VAL           USAGE INDEX.
           05  STATUS-CD         PIC X.
               88  ST-OK         VALUE 'Y' 'A'.
               88  ST-RANGE      VALUE '0' THRU '9'.
           66  RENAMED-ITEM      RENAMES ALPHA-CODE THRU TEXT-VAL.
       77  STANDALONE-COUNTER    PIC 9(3).
    """
    cbl = CopyBook.from_string(copybook_text)
    assert_that(cbl.has_binary_fields).is_true()

    def _get_field(name: str) -> Field:
        rec = cbl.find_record(name)
        assert isinstance(rec, Field)
        return rec

    # Check field kinds & byte widths
    assert_that(_get_field("ALPHA-CODE").kind).is_equal_to(FieldKind.ALPHABETIC)
    assert_that(_get_field("NAT-NAME").byte_length).is_equal_to(6)
    assert_that(_get_field("LEAD-SEP").byte_length).is_equal_to(5)
    assert_that(_get_field("TRAIL-SEP").byte_length).is_equal_to(4)
    assert_that(_get_field("BIN-HALF").byte_length).is_equal_to(2)
    assert_that(_get_field("BIN-FULL").byte_length).is_equal_to(4)
    assert_that(_get_field("BIN-DOUBLE").byte_length).is_equal_to(8)
    assert_that(_get_field("NATIVE-BIN").usage).is_equal_to(Usage.COMP_5)
    assert_that(_get_field("PACKED-VAL").byte_length).is_equal_to(4)
    assert_that(_get_field("FLT-SINGLE").byte_length).is_equal_to(4)
    assert_that(_get_field("FLT-DOUBLE").byte_length).is_equal_to(8)
    assert_that(_get_field("PTR-VAL").byte_length).is_equal_to(4)
    assert_that(_get_field("IDX-VAL").byte_length).is_equal_to(4)

    status_field = cbl.find_record("STATUS-CD")
    assert isinstance(status_field, Field)
    assert_that(status_field.conditions).is_length(2)
    assert_that(status_field.conditions[0].values).is_equal_to(("Y", "A"))
    assert_that(status_field.conditions[1].values).is_equal_to(())

    # Build a matching binary record (ASCII for DISPLAY, UTF-16-BE for NATIONAL, big-endian binary)
    raw = bytearray()
    raw.extend(b"ABCD")  # ALPHA-CODE
    raw.extend(b"HI    ")  # TEXT-VAL
    raw.extend("XYZ".encode("utf-16-be"))  # NAT-NAME
    raw.extend(b"  ")  # FILLER
    raw.extend(b"  ")  # unnamed FILLER
    raw.extend(b"0042")  # INT-UNSIGNED
    raw.extend(b"12345")  # DEC-IMPLIED -> 123.45
    raw.extend(b"15")  # SCALED-BIG -> 1500
    raw.extend(b"25")  # SCALED-SMALL -> 0.0025
    raw.extend(b"-0125")  # LEAD-SEP -> -12.5
    raw.extend(b"007-")  # TRAIL-SEP -> -7
    raw.extend(b"   $123.45-")  # EDITED-AMT (11 bytes: $$$,$$9.99-)
    raw.extend(b"12/31/2025")  # EDITED-DATE
    raw.extend(comp_pack(-320, 2, signed=True))  # BIN-HALF
    raw.extend(comp_pack(123456, 4, signed=True))  # BIN-FULL
    raw.extend(comp_pack(987654321012, 8, signed=True))  # BIN-DOUBLE
    raw.extend(comp_pack(30000, 2, signed=True))  # NATIVE-BIN (COMP-5 exceeds 9999!)
    raw.extend(comp3_pack(-456.78, 7, decimals=2))  # PACKED-VAL
    raw.extend(comp_float_pack(1.5, 4, float_format="ieee"))  # FLT-SINGLE
    raw.extend(comp_float_pack(2.75, 8, float_format="ieee"))  # FLT-DOUBLE
    raw.extend((4096).to_bytes(4, "big", signed=False))  # PTR-VAL
    raw.extend((99).to_bytes(4, "big", signed=True))  # IDX-VAL
    raw.extend(b"Y")  # STATUS-CD
    raw.extend(b"001")  # STANDALONE-COUNTER

    assert_that(len(raw)).is_equal_to(cbl.record_length)

    dat = tmp_path / "comp_all.dat"
    dat.write_bytes(bytes(raw))

    df = next(cbl.yield_data(dat, encoding="ascii", include_filler=False, line_ending="none"))
    row = df.iloc[0]
    assert_that(row["ALPHA-CODE"]).is_equal_to("ABCD")
    assert_that(row["TEXT-VAL"]).is_equal_to("HI")
    assert_that(row["NAT-NAME"]).is_equal_to("XYZ")
    assert_that(int(row["INT-UNSIGNED"])).is_equal_to(42)
    assert_that(float(row["DEC-IMPLIED"])).is_close_to(123.45, 1e-9)
    assert_that(int(row["SCALED-BIG"])).is_equal_to(1500)
    assert_that(float(row["SCALED-SMALL"])).is_close_to(0.0025, 1e-9)
    assert_that(float(row["LEAD-SEP"])).is_close_to(-12.5, 1e-9)
    assert_that(int(row["TRAIL-SEP"])).is_equal_to(-7)
    assert_that(float(row["EDITED-AMT"])).is_close_to(-123.45, 1e-9)
    assert_that(row["EDITED-DATE"]).is_equal_to("12/31/2025")
    assert_that(int(row["BIN-HALF"])).is_equal_to(-320)
    assert_that(int(row["BIN-FULL"])).is_equal_to(123456)
    assert_that(int(row["BIN-DOUBLE"])).is_equal_to(987654321012)
    assert_that(int(row["NATIVE-BIN"])).is_equal_to(30000)
    assert_that(float(row["PACKED-VAL"])).is_close_to(-456.78, 1e-9)
    assert_that(float(row["FLT-SINGLE"])).is_close_to(1.5, 1e-6)
    assert_that(float(row["FLT-DOUBLE"])).is_close_to(2.75, 1e-12)
    assert_that(int(row["PTR-VAL"])).is_equal_to(4096)
    assert_that(int(row["IDX-VAL"])).is_equal_to(99)
    assert_that(row["STATUS-CD"]).is_equal_to("Y")
    assert_that(int(row["STANDALONE-COUNTER"])).is_equal_to(1)

    # Also test drop_converters & convert_compressed=False
    df_raw = next(
        cbl.yield_data(
            dat, encoding="ascii", include_filler=False, drop_converters=True, line_ending="none"
        )
    )
    assert_that(df_raw["PACKED-VAL"].iloc[0]).is_instance_of(str)


def test_cobol_mainframe_ebcdic_comp3_redefines_and_occurs(data_dir: pathlib.Path) -> None:
    """Mainframe EBCDIC + COMP + COMP-1/2 + COMP-3 + REDEFINES + OCCURS decodes accurately."""
    cbl = CopyBook(data_dir / "sample_cobol_mainframe.cbl")
    dat = data_dir / "sample_cobol_mainframe.dat"

    # REDEFINES metadata recorded on ACCT-EFF-DATE
    eff = cbl.find_record("ACCT-EFF-DATE")
    assert isinstance(eff, Field)
    assert_that(eff.redefinedby).contains("ACCT-EFF-DATE-PARTS")

    # Stream in small chunks of 2 records
    chunks = list(cbl.yield_data(dat, chunksize=2, encoding="cp500", include_filler=False))
    assert_that(chunks).is_length(2)
    df = pd.concat(chunks, ignore_index=True)
    assert_that(df).is_length(4)

    assert_that(df["ACCT-REGION"].tolist()).is_equal_to(["NA", "EU", "AP", "NA"])
    assert_that(df["ACCT-STATUS"].tolist()).is_equal_to(["A", "A", "C", "A"])
    assert_that(df["ACCT-EFF-DATE"].tolist()).is_equal_to([20240115, 20240220, 20231201, 20240630])
    assert_that(df["ACCT-ADJUSTMENT"].tolist()).is_equal_to([125.5, -42.75, 0.0, 9999.99])
    assert_that(df["ACCT-TERM-MONTHS"].tolist()).is_equal_to([36, 60, 12, 120])
    assert_that(df["ACCT-SCORE"].tolist()).is_equal_to([745000, -120000, 999999, 500000])
    assert_that(float(df["ACCT-RATE"].iloc[0])).is_close_to(0.0425, 1e-6)
    assert_that(float(df["ACCT-FACTOR"].iloc[1])).is_close_to(0.9975, 1e-12)
    assert_that(df["ACCT-BALANCE"].tolist()).is_equal_to([250000.0, -15000.5, 0.0, 1234567.89])
    assert_that(df["PERIOD-AMT"].iloc[0]).is_equal_to(1000.0)
    assert_that(df["PERIOD-AMT-01"].iloc[1]).is_equal_to(-25.0)
    assert_that(df["PERIOD-AMT-02"].iloc[3]).is_equal_to(2700.3)

    # With include_redefines=True, ACCT-EFF-YEAR / MONTH / DAY overlay the same bytes!
    df_redef = next(
        cbl.yield_data(dat, encoding="cp500", include_redefines=True, include_filler=False)
    )
    assert_that(df_redef["ACCT-EFF-YEAR"].tolist()).is_equal_to([2024, 2024, 2023, 2024])
    assert_that(df_redef["ACCT-EFF-MONTH"].tolist()).is_equal_to([1, 2, 12, 6])
    assert_that(df_redef["ACCT-EFF-DAY"].tolist()).is_equal_to([15, 20, 1, 30])


def test_cobol_to_pandera_schema(data_dir: pathlib.Path) -> None:
    """CopyBook.to_pandera_schema validates parsed records and flags violations."""
    cbl = CopyBook(data_dir / "sample_cobol_mainframe.cbl")
    df = next(
        cbl.yield_data(
            data_dir / "sample_cobol_mainframe.dat",
            encoding="cp500",
            include_filler=False,
        )
    )
    schema = cbl.to_pandera_schema(include_filler=False, enforce_conditions=True)
    assert_that(schema).is_instance_of(pa.DataFrameSchema)
    validated = schema.validate(df)
    assert_that(validated).is_length(4)

    # Mutate status to an invalid level-88 value -> schema validation fails
    bad_df = df.copy()
    bad_df.loc[0, "ACCT-STATUS"] = "Z"
    with pytest.raises((SchemaError, SchemaErrors)):
        schema.validate(bad_df)


def test_cobol_occurs_100_suffix_and_predict_encoding(data_dir: pathlib.Path) -> None:
    """OCCURS >= 100 uses 3-digit zero-padded suffixes and predict_encoding works on paths."""
    cbl = CopyBook.from_string("01 BIG-VEC.\n   05 ITEM PIC 9(2) OCCURS 104 TIMES.\n")
    assert_that(cbl.fields).is_length(104)
    assert_that(cbl.fields[0]).is_equal_to("ITEM")
    assert_that(cbl.fields[1]).is_equal_to("ITEM-001")
    assert_that(cbl.fields[103]).is_equal_to("ITEM-103")
    assert_that(predict_encoding(data_dir / "sample_cobol_students.dat")).is_not_empty()
    assert_that(parse_copybook(data_dir / "sample_cobol_students.cbl")).is_length(1)
    assert_that(coboller.parse_copybook(str(data_dir / "sample_cobol_students.cbl"))).is_length(1)


def test_cobol_edge_cases_and_line_endings(tmp_path: pathlib.Path) -> None:
    """Cover truncated records, CRLF/LF binary detection, decimal scaling, and copybook-only ops."""
    cbl = CopyBook.from_string(
        "01 REC.\n"
        "   05 AMT PIC S9(3)V99 COMP-3.\n"
        "   05 BIG-COMP PIC S9(20) COMP.\n"
        "   05 HUGE-COMP PIC S9(37) COMP.\n"
        "   05 CNT PIC 9(2) OCCURS 2 TIMES.\n"
    )
    cnt_field = cbl.find_record("CNT")
    assert isinstance(cnt_field, Field)
    assert_that(str(cnt_field)).contains("2 OCCURS")
    assert_that(cnt_field.pic_to_fwf_kwargs()).is_length(2)
    big_comp = cbl.find_record("BIG-COMP")
    assert isinstance(big_comp, Field)
    assert_that(big_comp.byte_length).is_equal_to(9)
    huge_comp = cbl.find_record("HUGE-COMP")
    assert isinstance(huge_comp, Field)
    assert_that(huge_comp.byte_length).is_equal_to(16)

    # Copybook with LF-terminated records and empty lines
    cbl_simple = CopyBook.from_string("01 R.\n   05 A PIC X(3).\n   05 B PIC 9(2).\n")
    dat_lf = tmp_path / "lf.dat"
    dat_lf.write_bytes(b"ABC01\n\nDEF02\n")
    df_lf = next(cbl_simple.yield_data(dat_lf, line_ending="auto"))
    assert_that(df_lf["A"].tolist()).is_equal_to(["ABC", "DEF"])
    assert_that(df_lf["B"].tolist()).is_equal_to([1, 2])

    # Fixed binary with truncated trailing record logs warning and pads gracefully
    dat_trunc = tmp_path / "trunc.dat"
    dat_trunc.write_bytes(b"XYZ99AB")
    df_trunc = next(cbl_simple.yield_data(dat_trunc, line_ending="none"))
    assert_that(df_trunc).is_length(2)

    # Leading P without explicit V -> negative exponent
    cbl_p = CopyBook.from_string("01 R.\n   05 TINY PIC PP99.\n")
    tiny = cbl_p.find_record("TINY")
    assert isinstance(tiny, Field)
    assert_that(tiny.exponent).is_equal_to(-4)
    assert_that(tiny.decode_bytes(b"25")).is_close_to(0.0025, 1e-9)

    # Empty copybook yields nothing
    cbl_empty = CopyBook.from_string("* comment only\n")
    assert_that(list(cbl_empty.yield_data(dat_lf))).is_empty()


# ---------------------------------------------------------------------------
# Exotic / Strange COBOL Data Types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "digits", "decimals", "expected_len"),
    [
        (0, 2, 0, 1),
        (87, 2, 0, 1),
        (1234567, 7, 0, 4),
        (9876.54, 6, 2, 3),
    ],
)
def test_comp6_unsigned_packed_roundtrip(
    value: int | float,
    digits: int,
    decimals: int,
    expected_len: int,
) -> None:
    """comp6_pack/unpack encode unsigned packed decimals with no sign nibble."""
    packed = comp6_pack(value, digits, decimals=decimals)
    assert_that(packed).is_length(expected_len)
    assert_that(comp6_unpack(packed, decimals=decimals)).is_equal_to(value)
    assert_that(comp6_unpack(packed, decimals=decimals, as_decimal=True)).is_equal_to(
        Decimal(str(value))
    )


def test_comp6_and_bit_errors() -> None:
    """comp6 and bit helpers reject invalid inputs cleanly."""
    with pytest.raises(ValueError, match="empty"):
        comp6_unpack(b"")
    with pytest.raises(ValueError, match="BCD nibble"):
        comp6_unpack(b"\x1c")
    with pytest.raises(ValueError, match="negative"):
        comp6_pack(-1, 4)
    with pytest.raises(ValueError, match="exceeds"):
        comp6_pack(99999, 4)

    packed_bits = bit_pack("101100101101")
    assert_that(packed_bits).is_length(2)
    assert_that(bit_unpack(packed_bits, 12)).is_equal_to("101100101101")
    with pytest.raises(ValueError, match="Invalid bit string"):
        bit_pack("102")


def test_external_float_and_decimal_comma(tmp_path: pathlib.Path) -> None:
    """External DISPLAY floats and European DECIMAL-POINT IS COMMA decode accurately."""
    assert_that(external_float_unpack(b"+1.23456E+04")).is_close_to(12345.6, 1e-6)
    assert_that(external_float_unpack(b"-1234E-02", expanded_pic="-99V99E-99")).is_close_to(
        -0.1234, 1e-9
    )
    assert_that(external_float_unpack(b"+1,50E+02", decimal_comma=True)).is_close_to(150.0, 1e-9)
    assert_that(external_float_unpack(b"    ")).is_equal_to(0.0)
    eu_val = parse_numeric_edited("1.234,56-", decimal_comma=True)
    assert eu_val is not None
    assert_that(eu_val).is_close_to(-1234.56, 1e-9)

    eu_cbl = CopyBook.from_string(
        "       SPECIAL-NAMES.\n"
        "           DECIMAL-POINT IS COMMA.\n"
        "       01  EU-REC.\n"
        "           05  EU-AMOUNT  PIC Z.ZZ9,99-.\n"
        "           05  EU-SCI     PIC +9,99E+99.\n"
    )
    assert_that(eu_cbl.decimal_comma).is_true()
    dat = tmp_path / "eu.dat"
    dat.write_bytes(b"1.234,56-+2,50E+01\n")
    df = next(eu_cbl.yield_data(dat, encoding="ascii"))
    assert_that(float(df["EU-AMOUNT"].iloc[0])).is_close_to(-1234.56, 1e-9)
    assert_that(float(df["EU-SCI"].iloc[0])).is_close_to(25.0, 1e-9)


def test_cobol_exotic_sample_file_end_to_end(
    data_dir: pathlib.Path,
    sample_cobol_exotic: str,
) -> None:
    """End-to-end test of sample_cobol_exotic.cbl/.dat and DataSpector + Pandera integration."""
    import dataspector

    cbl = CopyBook(data_dir / "sample_cobol_exotic.cbl")
    dat = data_dir / "sample_cobol_exotic.dat"

    assert_that(cbl.record_length).is_equal_to(111)
    assert_that(cbl.fields).is_length(20)

    def _field(name: str) -> Field:
        rec = cbl.find_record(name)
        assert isinstance(rec, Field)
        return rec

    assert_that(_field("PACKED-UNSIGNED-CNT").usage).is_equal_to(Usage.COMP_6)
    assert_that(_field("PACKED-UNSIGNED-CNT").byte_length).is_equal_to(4)
    assert_that(_field("PACKED-UNSIGNED-AMT").byte_length).is_equal_to(3)
    assert_that(_field("VAR-BIN-24BIT").usage).is_equal_to(Usage.COMP_X)
    assert_that(_field("VAR-BIN-24BIT").byte_length).is_equal_to(3)
    assert_that(_field("VAR-BIN-DIGITS").byte_length).is_equal_to(3)
    assert_that(_field("EXT-FLOAT-SCI").kind).is_equal_to(FieldKind.EXTERNAL_FLOAT)
    assert_that(_field("C-INT8").byte_length).is_equal_to(1)
    assert_that(_field("C-INT8").signed).is_true()
    assert_that(_field("C-UINT8").signed).is_false()
    assert_that(_field("C-UINT32").signed).is_false()
    assert_that(_field("UTF8-FIXED-CHARS").byte_length).is_equal_to(16)
    assert_that(_field("UTF8-FIXED-BYTES").byte_length).is_equal_to(12)
    assert_that(_field("DBCS-KANJI").byte_length).is_equal_to(6)
    assert_that(_field("FLAG-BYTE").byte_length).is_equal_to(1)
    assert_that(_field("FLAG-12BIT").byte_length).is_equal_to(2)
    assert_that(_field("CALLBACK-PTR").byte_length).is_equal_to(8)

    df = next(cbl.yield_data(dat, encoding="ascii"))
    assert_that(df).is_length(3)
    assert_that(df["PACKED-UNSIGNED-CNT"].tolist()).is_equal_to([1234567, 0, 9999999])
    assert_that(df["PACKED-UNSIGNED-AMT"].tolist()).is_equal_to([9876.54, 0.0, 12.05])
    assert_that(df["VAR-BIN-24BIT"].tolist()).is_equal_to([0xABCDEF, 1, 16777215])
    assert_that(df["VAR-BIN-DIGITS"].tolist()).is_equal_to([65535, 99999, 42])
    assert_that(float(df["EXT-FLOAT-SCI"].iloc[0])).is_close_to(12345.6, 1e-6)
    assert_that(float(df["EXT-FLOAT-IMPLIED"].iloc[1])).is_close_to(-0.55, 1e-9)
    assert_that(df["C-INT8"].tolist()).is_equal_to([-42, 127, -128])
    assert_that(df["C-UINT8"].tolist()).is_equal_to([250, 0, 128])
    assert_that(df["C-UINT32"].tolist()).is_equal_to([3000000000, 4294967295, 1024])
    assert_that(df["C-INT64"].tolist()).is_equal_to([-900000000000, 1234567890123, 0])
    assert_that(float(df["IEEE-SINGLE"].iloc[0])).is_close_to(1.5, 1e-6)
    assert_that(float(df["IEEE-DOUBLE"].iloc[0])).is_close_to(3.1415926535, 1e-9)
    assert_that(df["UTF8-FIXED-CHARS"].tolist()).is_equal_to(["café", "naïve", "αβγδ"])
    assert_that(df["UTF8-FIXED-BYTES"].tolist()).is_equal_to(["hello 🌍", "UTF-8 OK", "¡Hola!"])
    assert_that(df["DBCS-KANJI"].tolist()).is_equal_to(["東京府", "大阪市", "京都"])
    assert_that(df["FLAG-BYTE"].tolist()).is_equal_to(["10110010", "00000001", "11111111"])
    assert_that(df["FLAG-12BIT"].tolist()).is_equal_to(
        ["110010101111", "010101010101", "100000000001"]
    )
    assert_that(df["CALLBACK-PTR"].tolist()).is_equal_to([0x7FFF00001234, 0xDEADBEEF, 0])

    # Auto-generated Pandera schema + DataSpector runner end-to-end
    res = dataspector.run_checks_on_location(
        dataspector.GenericData(sample_cobol_exotic, reader_options={"encoding": "ascii"}),
        [
            ("source_exists", {}),
            ("source_has_N_fields", {"n_fields": 20}),
            ("record_count", {"nrows": 3}),
            ("record_validate_schema", {"schema": data_dir / "sample_cobol_exotic.cbl"}),
        ],
    )
    assert_that(res.all_passed).is_true()


def test_cobol_summary_to_dataframe_and_convert(
    data_dir: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    """CopyBook.summary, to_dataframe (with nrows), and convert export to CSV/TSV/JSONL/JSON/Excel."""
    cbl = CopyBook(data_dir / "sample_cobol_mainframe.cbl")
    dat = data_dir / "sample_cobol_mainframe.dat"

    summary = cbl.summary(include_filler=False)
    assert_that(list(summary.columns)).contains("name", "pic", "usage", "offset", "byte_length")
    assert_that(summary["name"].tolist()).does_not_contain("FILLER")
    assert_that(summary).is_length(14)

    # Preview first 2 rows via to_dataframe(nrows=2)
    preview = cbl.to_dataframe(dat, encoding="cp500", include_filler=False, nrows=2)
    assert_that(preview).is_length(2)
    assert_that(preview["ACCT-REGION"].tolist()).is_equal_to(["NA", "EU"])

    # Empty data file returns empty DataFrame with proper columns
    empty_dat = tmp_path / "empty.dat"
    empty_dat.write_bytes(b"")
    empty_df = cbl.to_dataframe(empty_dat, encoding="cp500", include_filler=False)
    assert_that(empty_df).is_empty()
    assert_that(list(empty_df.columns)).contains("ACCT-REGION", "ACCT-BALANCE")

    # Convert to CSV (chunked), TSV, JSONL, JSON, and Excel
    csv_out = cbl.convert(dat, tmp_path / "out.csv", chunksize=2, encoding="cp500")
    tsv_out = cbl.convert(dat, tmp_path / "out.tsv", chunksize=2, encoding="cp500")
    jsonl_out = cbl.convert(dat, tmp_path / "out.jsonl", chunksize=2, encoding="cp500")
    json_out = cbl.convert(dat, tmp_path / "out.json", encoding="cp500")
    xlsx_out = cbl.convert(dat, tmp_path / "out.xlsx", encoding="cp500")

    assert_that(pd.read_csv(csv_out)).is_length(4)
    assert_that(pd.read_csv(tsv_out, sep="\t")).is_length(4)
    assert_that(pd.read_json(jsonl_out, lines=True)).is_length(4)
    assert_that(pd.read_json(json_out)).is_length(4)
    assert_that(pd.read_excel(xlsx_out)).is_length(4)

    # Empty input still writes header CSV and empty JSONL cleanly
    empty_csv = cbl.convert(empty_dat, tmp_path / "empty.csv", encoding="cp500")
    empty_jsonl = cbl.convert(empty_dat, tmp_path / "empty.jsonl", encoding="cp500")
    assert_that(pd.read_csv(empty_csv)).is_empty()
    assert_that(empty_jsonl.read_text(encoding="utf-8")).is_equal_to("")

    # Unsupported extension raises ValueError
    with pytest.raises(ValueError, match="Unsupported output format"):
        cbl.convert(dat, tmp_path / "out.xml", encoding="cp500")


def test_cobol_aligned_names_and_classmethods(data_dir: pathlib.Path) -> None:
    """COBOL-aligned class names and @classmethod constructors work alongside legacy aliases."""
    cbl = coboller.Copybook.from_file(data_dir / "sample_cobol_students.cbl")
    assert_that(cbl).is_instance_of(coboller.CopyBook)
    assert_that(cbl.records[0]).is_instance_of(coboller.GroupItem)

    item = coboller.ElementaryItem.from_clause("05 AMT PIC S9(5)V99 COMP-3.")
    assert_that(item).is_instance_of(coboller.Field)
    assert_that(item.kind).is_equal_to(coboller.DataCategory.PACKED_DECIMAL)
    assert_that(item.byte_length).is_equal_to(4)
    assert_that(item.decode_bytes(comp3_pack(-123.45, 7, decimals=2))).is_equal_to(-123.45)

    with pytest.raises(ValueError, match="Could not parse"):
        coboller.ElementaryItem.from_clause("NOT A COBOL FIELD")


def test_real_world_mainframe_extract_edge_cases(tmp_path: pathlib.Path) -> None:
    """Cover wider REDEFINES, inactive REDEFINES overlays, LOW-VALUES/spaces, and overpunched edited decimals."""
    assert_that(comp3_unpack(b"\x40\x40\x40")).is_equal_to(0)
    assert_that(comp3_unpack(b"\x00\x00\x00")).is_equal_to(0)
    assert_that(comp6_unpack(b"\x40\x40")).is_equal_to(0)
    assert_that(comp6_unpack(b"\x00\x00")).is_equal_to(0)
    assert_that(zoned_unpack(b"\x00\x00\x00", encoding="cp037")).is_equal_to(0)

    # Explicit-decimal overpunched display numbers (e.g. PIC S9(3).99 in Cobrix)
    assert_that(parse_numeric_edited("305.0L")).is_equal_to(-305.03)
    assert_that(parse_numeric_edited("305.0C")).is_equal_to(305.03)
    assert_that(parse_numeric_edited("L05.03")).is_equal_to(-305.03)
    assert_that(parse_numeric_edited("C05.03")).is_equal_to(305.03)

    # SIGN SEPARATE without 'S' in PIC
    sep_item = coboller.ElementaryItem.from_clause(
        "05 RATE PIC 99V99 SIGN IS LEADING SEPARATE CHARACTER."
    )
    assert_that(sep_item.signed).is_true()
    assert_that(sep_item.byte_length).is_equal_to(5)
    assert_that(sep_item.decode_bytes(b"-1234")).is_equal_to(-12.34)

    # Wider REDEFINES expands record_length and inactive REDEFINES returns None for invalid numeric overlay
    cbl = coboller.Copybook.from_string(
        "01 EXPORT-REC.\n"
        "   05 REC-TYPE PIC X(1).\n"
        "   05 PAYLOAD PIC X(3).\n"
        "   05 NUM-OVERLAY REDEFINES PAYLOAD.\n"
        "      10 AMT PIC S9(5) COMP-3.\n"
        "      10 EXTRA PIC X(2).\n"
    )
    assert_that(cbl.record_length).is_equal_to(6)
    dat = tmp_path / "multi.dat"
    # Row 1: text record ('T', 'ABCDE') where AMT COMP-3 overlay is invalid ('ABC')
    # Row 2: numeric record ('N', packed 12345 + 'OK')
    dat.write_bytes(b"TABCDE" + b"N" + comp3_pack(12345, 5) + b"OK")
    df = cbl.to_dataframe(dat, encoding="ascii", include_redefines=True, line_ending="none")
    assert_that(df).is_length(2)
    assert_that(pd.isna(df.loc[0, "AMT"])).is_true()
    assert_that(df.loc[1, "AMT"]).is_equal_to(12345.0)
