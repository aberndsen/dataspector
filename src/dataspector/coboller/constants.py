"""Enums, compiled regular expressions, and lookup tables for :mod:`dataspector.coboller`."""

from __future__ import annotations

import re
from enum import StrEnum


class Usage(StrEnum):
    """COBOL ``USAGE`` storage representations."""

    DISPLAY = "DISPLAY"
    DISPLAY_1 = "DISPLAY-1"
    COMP = "COMP"
    COMP_1 = "COMP-1"
    COMP_2 = "COMP-2"
    COMP_3 = "COMP-3"
    COMP_5 = "COMP-5"
    COMP_6 = "COMP-6"
    COMP_X = "COMP-X"
    BINARY_CHAR = "BINARY-CHAR"
    BINARY_SHORT = "BINARY-SHORT"
    BINARY_LONG = "BINARY-LONG"
    BINARY_DOUBLE = "BINARY-DOUBLE"
    FLOAT_SHORT = "FLOAT-SHORT"
    FLOAT_LONG = "FLOAT-LONG"
    NATIONAL = "NATIONAL"
    UTF_8 = "UTF-8"
    BIT = "BIT"
    POINTER = "POINTER"
    PROCEDURE_POINTER = "PROCEDURE-POINTER"
    FUNCTION_POINTER = "FUNCTION-POINTER"
    INDEX = "INDEX"


class SignMode(StrEnum):
    """COBOL sign encoding modes for ``USAGE DISPLAY`` signed numeric items."""

    NONE = "NONE"
    TRAILING_OVERPUNCH = "TRAILING"
    LEADING_OVERPUNCH = "LEADING"
    TRAILING_SEPARATE = "TRAILING SEPARATE"
    LEADING_SEPARATE = "LEADING SEPARATE"


class DataCategory(StrEnum):
    """COBOL data category of an elementary item."""

    ALPHABETIC = "ALPHABETIC"
    ALPHANUMERIC = "ALPHANUMERIC"
    NATIONAL = "NATIONAL"
    UTF8 = "UTF8"
    DBCS = "DBCS"
    BIT = "BIT"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    NUMERIC_EDITED = "NUMERIC_EDITED"
    EXTERNAL_FLOAT = "EXTERNAL_FLOAT"
    BINARY = "BINARY"
    PACKED_DECIMAL = "PACKED_DECIMAL"
    PACKED_UNSIGNED = "PACKED_UNSIGNED"
    FLOAT = "FLOAT"
    POINTER = "POINTER"
    INDEX = "INDEX"


FieldKind = DataCategory

USAGE_ALIASES: dict[str, Usage] = {
    "DISPLAY": Usage.DISPLAY,
    "DISPLAY-1": Usage.DISPLAY_1,
    "COMP": Usage.COMP,
    "COMPUTATIONAL": Usage.COMP,
    "COMP-4": Usage.COMP,
    "COMPUTATIONAL-4": Usage.COMP,
    "BINARY": Usage.COMP,
    "COMP-1": Usage.COMP_1,
    "COMPUTATIONAL-1": Usage.COMP_1,
    "COMP-2": Usage.COMP_2,
    "COMPUTATIONAL-2": Usage.COMP_2,
    "COMP-3": Usage.COMP_3,
    "COMPUTATIONAL-3": Usage.COMP_3,
    "PACKED-DECIMAL": Usage.COMP_3,
    "COMP-5": Usage.COMP_5,
    "COMPUTATIONAL-5": Usage.COMP_5,
    "COMP-6": Usage.COMP_6,
    "COMPUTATIONAL-6": Usage.COMP_6,
    "COMP-X": Usage.COMP_X,
    "COMPUTATIONAL-X": Usage.COMP_X,
    "BINARY-CHAR": Usage.BINARY_CHAR,
    "BINARY-SHORT": Usage.BINARY_SHORT,
    "BINARY-LONG": Usage.BINARY_LONG,
    "BINARY-DOUBLE": Usage.BINARY_DOUBLE,
    "FLOAT-SHORT": Usage.FLOAT_SHORT,
    "FLOAT-LONG": Usage.FLOAT_LONG,
    "NATIONAL": Usage.NATIONAL,
    "UTF-8": Usage.UTF_8,
    "BIT": Usage.BIT,
    "POINTER": Usage.POINTER,
    "PROCEDURE-POINTER": Usage.PROCEDURE_POINTER,
    "FUNCTION-POINTER": Usage.FUNCTION_POINTER,
    "INDEX": Usage.INDEX,
}

BINARY_USAGES: frozenset[Usage] = frozenset(
    {
        Usage.DISPLAY_1,
        Usage.COMP,
        Usage.COMP_1,
        Usage.COMP_2,
        Usage.COMP_3,
        Usage.COMP_5,
        Usage.COMP_6,
        Usage.COMP_X,
        Usage.BINARY_CHAR,
        Usage.BINARY_SHORT,
        Usage.BINARY_LONG,
        Usage.BINARY_DOUBLE,
        Usage.FLOAT_SHORT,
        Usage.FLOAT_LONG,
        Usage.NATIONAL,
        Usage.UTF_8,
        Usage.BIT,
        Usage.POINTER,
        Usage.PROCEDURE_POINTER,
        Usage.FUNCTION_POINTER,
        Usage.INDEX,
    }
)

SELF_SIZED_USAGES: frozenset[Usage] = frozenset(
    {
        Usage.COMP_1,
        Usage.COMP_2,
        Usage.FLOAT_SHORT,
        Usage.FLOAT_LONG,
        Usage.BINARY_CHAR,
        Usage.BINARY_SHORT,
        Usage.BINARY_LONG,
        Usage.BINARY_DOUBLE,
        Usage.POINTER,
        Usage.PROCEDURE_POINTER,
        Usage.FUNCTION_POINTER,
        Usage.INDEX,
    }
)

FIXED_BINARY_SIZES: dict[Usage, int] = {
    Usage.BINARY_CHAR: 1,
    Usage.BINARY_SHORT: 2,
    Usage.BINARY_LONG: 4,
    Usage.BINARY_DOUBLE: 8,
}

PIC_REPEAT = re.compile(r"(?P<section>[^\s()])\((?P<repeat>\d+)\)")
PIC_FLOAT = re.compile(r"^S?[9P]*V[9P]+$|^S?[9Z]*[.V][9Z]+$")
PIC_INT = re.compile(r"^S?[9P]+$")
PIC_NUMERIC_PURE = re.compile(r"^S?[9PV]+$")
PIC_EXTERNAL_FLOAT = re.compile(r"^[S+-]?9*(?:[.V,]9*)?E[+-]?9+$")
PIC_ALPHA_ONLY = re.compile(r"^A+$")
PIC_NATIONAL_ONLY = re.compile(r"^N+$")
PIC_DBCS_ONLY = re.compile(r"^G+$")
PIC_UTF8_ONLY = re.compile(r"^U+$")
PIC_BIT_ONLY = re.compile(r"^1+$")
PIC_EDITED_MARKERS = re.compile(r"[Z*$.,+\-]|CR|DB")

LEVEL_START_RE = re.compile(r"^\s*(?P<level>\d{2})\b(?P<rest>.*)$")
REDEFINES_RE = re.compile(r"\bREDEFINES\s+(?P<redefines>[A-Z0-9_-]+)", re.I)
OCCURS_RE = re.compile(
    r"\bOCCURS\s+(?:(?P<min>\d+)\s+TO\s+)?(?P<occurs>\d+)(?:\s+TIMES)?(?:\s+DEPENDING\s+(?:ON\s+)?(?P<depending>[A-Z0-9_-]+))?",
    re.I,
)
INDEXED_RE = re.compile(r"\bINDEXED\s+(?:BY\s+)?(?P<indexedby>[A-Z0-9_-]+)", re.I)
PIC_RE = re.compile(r"\b(?:PICTURE|PIC)\s+(?:IS\s+)?(?P<pic>\S+)", re.I)
BYTE_LENGTH_RE = re.compile(r"\bBYTE-LENGTH\s+(?P<byte_length>\d+)\b", re.I)
USAGE_RE = re.compile(
    r"\b(?:USAGE\s+(?:IS\s+)?)?(?P<usage>"
    r"COMPUTATIONAL-[1-6X]|COMP-[1-6X]|COMPUTATIONAL|COMP|"
    r"PACKED-DECIMAL|BINARY-DOUBLE|BINARY-LONG|BINARY-SHORT|BINARY-CHAR|BINARY|"
    r"FLOAT-SHORT|FLOAT-LONG|DISPLAY-1|DISPLAY|"
    r"PROCEDURE-POINTER|FUNCTION-POINTER|POINTER|NATIONAL|UTF-8|BIT|INDEX)\b",
    re.I,
)
BINARY_SIGN_QUALIFIER_RE = re.compile(
    r"\bBINARY-(?:CHAR|SHORT|LONG|DOUBLE)\s+(?P<qual>SIGNED|UNSIGNED)\b",
    re.I,
)
SIGN_RE = re.compile(
    r"\bSIGN\s+(?:IS\s+)?(?P<pos>LEADING|TRAILING)(?:\s+(?P<sep>SEPARATE)(?:\s+CHARACTER)?)?",
    re.I,
)
VALUE_RE = re.compile(
    r"\bVALUES?\s+(?:IS\s+|ARE\s+)?(?P<value>.+?)(?=\s+(?:REDEFINES|OCCURS|PIC|PICTURE|USAGE|SIGN|BLANK|JUSTIFIED|JUST|SYNC|SYNCHRONIZED|COMP|BINARY|PACKED-DECIMAL|DISPLAY|NATIONAL|UTF-8|BIT|FLOAT-SHORT|FLOAT-LONG|POINTER|PROCEDURE-POINTER|FUNCTION-POINTER|INDEX|BYTE-LENGTH)\b|$)",
    re.I,
)
BLANK_ZERO_RE = re.compile(r"\bBLANK\s+(?:WHEN\s+)?ZEROS?\b", re.I)
JUSTIFIED_RE = re.compile(r"\bJUST(?:IFIED)?(?:\s+RIGHT)?\b", re.I)
DECIMAL_COMMA_RE = re.compile(r"\bDECIMAL-POINT\s+IS\s+COMMA\b", re.I)

SKIP_LINE_PREFIXES: tuple[str, ...] = (
    "IDENTIFICATION",
    "ID ",
    "PROGRAM-ID",
    "ENVIRONMENT",
    "CONFIGURATION",
    "INPUT-OUTPUT",
    "FILE-CONTROL",
    "SELECT ",
    "DATA ",
    "FILE ",
    "WORKING-STORAGE",
    "LOCAL-STORAGE",
    "LINKAGE ",
    "FD ",
    "SD ",
    "LABEL ",
    "RECORD ",
    "BLOCK ",
    "PROCEDURE",
    "STOP ",
    "EXIT",
    "COPY ",
)

CLAUSE_KEYWORDS: frozenset[str] = frozenset(
    {
        "PIC",
        "PICTURE",
        "USAGE",
        "REDEFINES",
        "OCCURS",
        "VALUE",
        "VALUES",
        "SIGN",
        "COMP",
        "COMP-1",
        "COMP-2",
        "COMP-3",
        "COMP-4",
        "COMP-5",
        "COMP-6",
        "COMP-X",
        "COMPUTATIONAL",
        "BINARY",
        "BINARY-CHAR",
        "BINARY-SHORT",
        "BINARY-LONG",
        "BINARY-DOUBLE",
        "FLOAT-SHORT",
        "FLOAT-LONG",
        "PACKED-DECIMAL",
        "DISPLAY",
        "DISPLAY-1",
        "NATIONAL",
        "UTF-8",
        "BIT",
        "POINTER",
        "PROCEDURE-POINTER",
        "FUNCTION-POINTER",
        "INDEX",
    }
)

ASCII_OVERPUNCH_POS: dict[str, str] = {
    "{": "0",
    "A": "1",
    "B": "2",
    "C": "3",
    "D": "4",
    "E": "5",
    "F": "6",
    "G": "7",
    "H": "8",
    "I": "9",
}
ASCII_OVERPUNCH_NEG: dict[str, str] = {
    "}": "0",
    "J": "1",
    "K": "2",
    "L": "3",
    "M": "4",
    "N": "5",
    "O": "6",
    "P": "7",
    "Q": "8",
    "R": "9",
    "p": "0",
    "q": "1",
    "r": "2",
    "s": "3",
    "t": "4",
    "u": "5",
    "v": "6",
    "w": "7",
    "x": "8",
    "y": "9",
}
DIGIT_TO_ASCII_POS: dict[str, str] = {v: k for k, v in ASCII_OVERPUNCH_POS.items()}
DIGIT_TO_ASCII_NEG: dict[str, str] = {
    "0": "}",
    "1": "J",
    "2": "K",
    "3": "L",
    "4": "M",
    "5": "N",
    "6": "O",
    "7": "P",
    "8": "Q",
    "9": "R",
}

EBCDIC_ENCODINGS: frozenset[str] = frozenset(
    {
        "cp037",
        "cp273",
        "cp500",
        "cp875",
        "cp1026",
        "cp1140",
        "ebcdic",
        "ibm037",
        "ibm500",
    }
)
