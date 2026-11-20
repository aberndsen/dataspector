"""Stateless COBOL copybook line cleaning and clause parsing helpers."""

from __future__ import annotations

import re
from typing import Any

from dataspector.coboller.constants import (
    BINARY_SIGN_QUALIFIER_RE,
    BLANK_ZERO_RE,
    BYTE_LENGTH_RE,
    CLAUSE_KEYWORDS,
    INDEXED_RE,
    JUSTIFIED_RE,
    LEVEL_START_RE,
    OCCURS_RE,
    PIC_RE,
    REDEFINES_RE,
    SIGN_RE,
    SKIP_LINE_PREFIXES,
    USAGE_RE,
    VALUE_RE,
    SignMode,
)


def clean_cobol_line(line: str) -> str:
    """Strip fixed-format COBOL sequence/comment/ID areas and return code text.

    Parameters
    ----------
    line
        Raw single line from a COBOL copybook.

    Returns
    -------
    str
        Cleaned statement fragment, or ``""`` for blank/comment lines.
    """
    seq_area = line[:6].replace(" ", "")
    has_seq_area = not seq_area or seq_area.isdigit()
    if len(line) >= 7 and line[6] in ("*", "/") and has_seq_area:
        return ""
    if len(line) >= 7 and seq_area.isdigit() and line[6] == " ":
        line = line[7:72] if len(line) > 72 else line[7:]
    elif len(line) > 72 and line[72:].strip().isdigit():
        line = line[:72]

    if "*>" in line:
        line = line.split("*>", 1)[0]

    stripped = line.strip()
    if not stripped or stripped.startswith("*"):
        return ""
    return stripped


def extract_statements(rawtext: str) -> list[str]:
    """Join multi-line COBOL statements and split on terminating periods.

    Parameters
    ----------
    rawtext
        Full COBOL copybook text.

    Returns
    -------
    list[str]
        Cleaned period-stripped COBOL statements.
    """
    statements: list[str] = []
    buffer = ""
    for raw_line in rawtext.splitlines():
        cleaned = clean_cobol_line(raw_line)
        if not cleaned:
            continue
        buffer = f"{buffer} {cleaned}".strip() if buffer else cleaned
        if buffer.endswith("."):
            statements.append(buffer[:-1].strip())
            buffer = ""
    return statements


def parse_condition_values(raw_value: str) -> tuple[str, ...]:
    """Parse discrete literal values from a level-88 ``VALUE`` clause.

    Parameters
    ----------
    raw_value
        Raw substring following ``VALUE``/``VALUES`` in a level-88 declaration.

    Returns
    -------
    tuple[str, ...]
        Tuple of normalized discrete literal values (empty for ``THRU`` ranges).
    """
    upper = raw_value.upper()
    if " THRU " in upper or " THROUGH " in upper:
        return ()
    tokens = re.findall(r"'([^']*)'|\"([^\"]*)\"|(\S+)", raw_value)
    values: list[str] = []
    figurative = {
        "SPACE": " ",
        "SPACES": " ",
        "ZERO": "0",
        "ZEROS": "0",
        "ZEROES": "0",
    }
    for single_q, double_q, bare in tokens:
        if single_q or (single_q == "" and not double_q and not bare):
            values.append(single_q)
        elif double_q:
            values.append(double_q)
        else:
            b_up = bare.upper()
            if b_up in ("ALL", "IS", "ARE"):
                continue
            values.append(figurative.get(b_up, bare))
    return tuple(values)


def parse_statement(stmt: str) -> dict[str, Any] | None:
    """Parse a single period-stripped COBOL data description statement.

    Parameters
    ----------
    stmt
        Cleaned COBOL statement without its trailing period.

    Returns
    -------
    dict[str, Any] | None
        Dictionary of extracted clauses (``level``, ``name``, ``pic``,
        ``usage``, ``occurs``, ``redefines``, etc.), or ``None`` if *stmt* is
        not a data description entry.
    """
    upper = stmt.upper()
    if upper.startswith(SKIP_LINE_PREFIXES):
        return None

    m = LEVEL_START_RE.match(stmt)
    if m is None:
        return None

    level_str = m.group("level")
    rest = m.group("rest").strip()
    if not rest:
        return None

    parts = rest.split(None, 1)
    first_token = parts[0]
    if first_token.upper() in CLAUSE_KEYWORDS:
        name = "FILLER"
        clauses = rest
    else:
        name = first_token
        clauses = parts[1] if len(parts) > 1 else ""

    redefines_m = REDEFINES_RE.search(clauses)
    occurs_m = OCCURS_RE.search(clauses)
    indexed_m = INDEXED_RE.search(clauses)
    pic_m = PIC_RE.search(clauses)
    byte_length_m = BYTE_LENGTH_RE.search(clauses)
    usage_m = USAGE_RE.search(clauses)
    bin_sign_m = BINARY_SIGN_QUALIFIER_RE.search(clauses)
    sign_m = SIGN_RE.search(clauses)
    value_m = VALUE_RE.search(clauses)

    sign_mode: SignMode | None = None
    if sign_m is not None:
        is_leading = sign_m.group("pos").upper() == "LEADING"
        is_separate = sign_m.group("sep") is not None
        if is_leading and is_separate:
            sign_mode = SignMode.LEADING_SEPARATE
        elif is_leading:
            sign_mode = SignMode.LEADING_OVERPUNCH
        elif is_separate:
            sign_mode = SignMode.TRAILING_SEPARATE
        else:
            sign_mode = SignMode.TRAILING_OVERPUNCH

    usage_str = usage_m.group("usage").upper() if usage_m is not None else None

    return {
        "level": level_str,
        "name": name,
        "redefines": redefines_m.group("redefines") if redefines_m else None,
        "occurs": occurs_m.group("occurs") if occurs_m else None,
        "occurs_min": occurs_m.group("min") if occurs_m else None,
        "depending_on": occurs_m.group("depending") if occurs_m else None,
        "indexedby": indexed_m.group("indexedby") if indexed_m else None,
        "pic": pic_m.group("pic") if pic_m else None,
        "byte_length": byte_length_m.group("byte_length") if byte_length_m else None,
        "comp": usage_str,
        "usage": usage_str,
        "binary_sign_qualifier": bin_sign_m.group("qual").upper() if bin_sign_m else None,
        "sign_mode": sign_mode,
        "value": value_m.group("value").strip() if value_m else None,
        "blank_when_zero": bool(BLANK_ZERO_RE.search(clauses)),
        "justified": bool(JUSTIFIED_RE.search(clauses)),
    }
