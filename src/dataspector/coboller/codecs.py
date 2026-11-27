"""Pure binary and text codecs for COBOL data representations (alphabetical)."""

from __future__ import annotations

import math
import pathlib
import struct
from decimal import Decimal
from typing import Literal

import chardet
from loguru import logger

from dataspector.coboller.constants import (
    ASCII_OVERPUNCH_NEG,
    ASCII_OVERPUNCH_POS,
    DIGIT_TO_ASCII_NEG,
    DIGIT_TO_ASCII_POS,
    EBCDIC_ENCODINGS,
    PIC_REPEAT,
    SignMode,
)

# ---------------------------------------------------------------------------
# Public Codec Functions (Alphabetical)
# ---------------------------------------------------------------------------


def bit_pack(bits: str) -> bytes:
    """Pack a ``'0'``/``'1'`` bit string into COBOL ``USAGE BIT`` bytes (zero-padded right).

    Parameters
    ----------
    bits
        Non-empty string of ``'0'`` and ``'1'`` characters.

    Returns
    -------
    bytes
        MSB-first packed bytes right-padded with zero bits to a byte boundary.
    """
    if not bits or any(ch not in ("0", "1") for ch in bits):
        raise ValueError(f"Invalid bit string: {bits!r}")
    padded = bits.ljust(((len(bits) + 7) // 8) * 8, "0")
    return bytes(int(padded[i : i + 8], 2) for i in range(0, len(padded), 8))


def bit_unpack(raw: bytes, n_bits: int) -> str:
    """Decode a COBOL-2002 ``PIC 1(n) USAGE BIT`` byte sequence into a bit string.

    Parameters
    ----------
    raw
        Raw packed bytes.
    n_bits
        Number of leading bits to extract.

    Returns
    -------
    str
        Bit string of length *n_bits* containing ``'0'`` and ``'1'`` characters.
    """
    bits = "".join(f"{b:08b}" for b in raw)
    return bits[:n_bits]


def comp3_pack(
    value: int | float | Decimal,
    digits: int,
    decimals: int = 0,
    exponent: int | None = None,
    signed: bool = True,
) -> bytes:
    """Pack a numeric value into COBOL ``COMP-3`` (BCD packed decimal) bytes.

    Parameters
    ----------
    value
        Numeric value to pack.
    digits
        Total number of decimal digit positions in the ``PIC`` clause.
    decimals
        Number of implied fractional decimal digits (ignored when *exponent* is set).
    exponent
        Optional explicit base-10 scaling exponent (e.g. ``-2`` for ``V99``, ``3`` for ``P(3)``).
    signed
        Encode sign nibble ``0xC``/``0xD`` when ``True``, or unsigned ``0xF`` when ``False``.

    Returns
    -------
    bytes
        Packed BCD byte sequence of length ``(digits // 2) + 1``.
    """
    exp = -decimals if exponent is None else exponent
    dec = Decimal(str(value))
    negative = dec < 0
    if negative and not signed:
        raise ValueError("Cannot pack negative value into unsigned COMP-3 field.")

    scaled = int(abs(dec).scaleb(-exp).to_integral_value())
    n_bytes = (digits // 2) + 1
    total_digit_slots = n_bytes * 2 - 1
    digit_str = str(scaled).zfill(total_digit_slots)
    if len(digit_str) > total_digit_slots:
        raise ValueError(f"Value {value} exceeds {digits}-digit COMP-3 capacity.")

    sign_nibble = 0x0D if negative else (0x0C if signed else 0x0F)
    nibbles = [int(ch) for ch in digit_str] + [sign_nibble]
    return bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))


def comp3_unpack(
    raw: bytes,
    decimals: int = 0,
    exponent: int | None = None,
    as_decimal: bool = False,
) -> int | float | Decimal:
    """Unpack a COBOL ``COMP-3`` / ``PACKED-DECIMAL`` byte sequence.

    Parameters
    ----------
    raw
        Packed BCD bytes whose final low nibble carries the sign.
    decimals
        Number of implied fractional decimal digits (ignored when *exponent* is set).
    exponent
        Optional explicit base-10 scaling exponent.
    as_decimal
        Return a :class:`decimal.Decimal` when ``True`` instead of ``int``/``float``.

    Returns
    -------
    int | float | Decimal
        Decoded numeric value.
    """
    if not raw:
        raise ValueError("Cannot unpack empty COMP-3 byte sequence.")

    exp = -decimals if exponent is None else exponent
    if all(b == 0x40 for b in raw) or all(b == 0x20 for b in raw) or all(b == 0x00 for b in raw):
        return scale_integer(0, exp, as_decimal=as_decimal)
    digits: list[int] = []
    for byte in raw[:-1]:
        hi = (byte >> 4) & 0x0F
        lo = byte & 0x0F
        if hi > 9 or lo > 9:
            raise ValueError(f"Invalid BCD nibble in COMP-3 byte 0x{byte:02X}.")
        digits.append(hi)
        digits.append(lo)

    last = raw[-1]
    last_digit = (last >> 4) & 0x0F
    sign_nibble = last & 0x0F
    if last_digit > 9:
        raise ValueError(f"Invalid BCD digit in final COMP-3 byte 0x{last:02X}.")
    digits.append(last_digit)

    if sign_nibble in (0xC, 0xF, 0xA, 0xE):
        sign = 1
    elif sign_nibble in (0xD, 0xB):
        sign = -1
    else:
        raise ValueError(f"Invalid COMP-3 sign nibble 0x{sign_nibble:X}.")

    int_val = 0
    for d in digits:
        int_val = int_val * 10 + d
    int_val *= sign
    return scale_integer(int_val, exp, as_decimal=as_decimal)


def comp3decompress(
    x: bytes,
    decimals: int = 0,
    as_decimal: bool = False,
) -> int | float | Decimal:
    """Backward-compatible alias for :func:`comp3_unpack`.

    Parameters
    ----------
    x
        Packed BCD bytes.
    decimals
        Number of implied fractional decimal digits.
    as_decimal
        Return a :class:`decimal.Decimal` when ``True``.

    Returns
    -------
    int | float | Decimal
        Decoded numeric value.
    """
    return comp3_unpack(x, decimals=decimals, as_decimal=as_decimal)


def comp6_pack(
    value: int | float | Decimal,
    digits: int,
    decimals: int = 0,
    exponent: int | None = None,
) -> bytes:
    """Pack a non-negative value into COBOL ``COMP-6`` (unsigned packed decimal) bytes.

    Parameters
    ----------
    value
        Non-negative numeric value to pack.
    digits
        Total number of decimal digit positions in the ``PIC`` clause.
    decimals
        Number of implied fractional decimal digits (ignored when *exponent* is set).
    exponent
        Optional explicit base-10 scaling exponent.

    Returns
    -------
    bytes
        Signless packed BCD byte sequence of length ``(digits + 1) // 2``.
    """
    exp = -decimals if exponent is None else exponent
    dec = Decimal(str(value))
    if dec < 0:
        raise ValueError("COMP-6 is unsigned and cannot pack negative values.")
    scaled = int(dec.scaleb(-exp).to_integral_value())
    n_bytes = (digits + 1) // 2
    slot_count = n_bytes * 2
    digit_str = str(scaled).zfill(slot_count)
    if len(digit_str) > slot_count:
        raise ValueError(f"Value {value} exceeds {digits}-digit COMP-6 capacity.")
    nibbles = [int(ch) for ch in digit_str]
    return bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))


def comp6_unpack(
    raw: bytes,
    decimals: int = 0,
    exponent: int | None = None,
    as_decimal: bool = False,
) -> int | float | Decimal:
    """Unpack a COBOL ``COMP-6`` (unsigned packed decimal, no sign nibble) byte sequence.

    Parameters
    ----------
    raw
        Signless packed BCD bytes (two decimal digits per byte).
    decimals
        Number of implied fractional decimal digits (ignored when *exponent* is set).
    exponent
        Optional explicit base-10 scaling exponent.
    as_decimal
        Return a :class:`decimal.Decimal` when ``True``.

    Returns
    -------
    int | float | Decimal
        Decoded non-negative numeric value.
    """
    if not raw:
        raise ValueError("Cannot unpack empty COMP-6 byte sequence.")
    exp = -decimals if exponent is None else exponent
    if all(b == 0x40 for b in raw) or all(b == 0x20 for b in raw) or all(b == 0x00 for b in raw):
        return scale_integer(0, exp, as_decimal=as_decimal)
    int_val = 0
    for byte in raw:
        hi = (byte >> 4) & 0x0F
        lo = byte & 0x0F
        if hi > 9 or lo > 9:
            raise ValueError(f"Invalid BCD nibble in COMP-6 byte 0x{byte:02X}.")
        int_val = int_val * 100 + hi * 10 + lo
    return scale_integer(int_val, exp, as_decimal=as_decimal)


def comp_float_pack(
    value: float,
    size: Literal[4, 8] = 4,
    float_format: Literal["ieee", "ibm"] = "ieee",
    byteorder: Literal["big", "little"] = "big",
) -> bytes:
    """Pack a Python ``float`` into ``COMP-1`` (4-byte) or ``COMP-2`` (8-byte) bytes.

    Parameters
    ----------
    value
        Floating-point number to encode.
    size
        Target storage width in bytes (``4`` for ``COMP-1``, ``8`` for ``COMP-2``).
    float_format
        Binary floating-point format (``'ieee'`` or ``'ibm'`` HFP).
    byteorder
        Byte order for IEEE 754 encoding (``'big'`` or ``'little'``).

    Returns
    -------
    bytes
        Encoded 4-byte or 8-byte floating-point sequence.
    """
    if size not in (4, 8):
        raise ValueError(f"COMP-1/COMP-2 size must be 4 or 8, got {size}.")
    if float_format == "ibm":
        return float_to_ibm_hfp(value, size=size)
    prefix = ">" if byteorder == "big" else "<"
    fmt = f"{prefix}{'f' if size == 4 else 'd'}"
    return struct.pack(fmt, value)


def comp_float_unpack(
    raw: bytes,
    float_format: Literal["ieee", "ibm"] = "ieee",
    byteorder: Literal["big", "little"] = "big",
) -> float:
    """Unpack a COBOL ``COMP-1`` (4-byte) or ``COMP-2`` (8-byte) floating-point value.

    Parameters
    ----------
    raw
        4-byte or 8-byte floating-point representation.
    float_format
        Binary floating-point format (``'ieee'`` or ``'ibm'`` HFP).
    byteorder
        Byte order for IEEE 754 decoding (``'big'`` or ``'little'``).

    Returns
    -------
    float
        Decoded Python floating-point number.
    """
    if len(raw) not in (4, 8):
        raise ValueError(f"COMP-1/COMP-2 expects 4 or 8 bytes, got {len(raw)}.")
    if float_format == "ibm":
        return ibm_hfp_to_float(raw)
    prefix = ">" if byteorder == "big" else "<"
    fmt = f"{prefix}{'f' if len(raw) == 4 else 'd'}"
    return float(struct.unpack(fmt, raw)[0])


def comp_pack(
    value: int | float | Decimal,
    byte_length: int,
    signed: bool = True,
    byteorder: Literal["big", "little"] = "big",
    exponent: int = 0,
) -> bytes:
    """Pack a numeric value into COBOL binary ``COMP`` bytes.

    Parameters
    ----------
    value
        Numeric value to pack.
    byte_length
        Exact width in bytes of the target binary integer field.
    signed
        Use two's-complement signed encoding when ``True``, unsigned when ``False``.
    byteorder
        Byte order (``'big'`` or ``'little'``).
    exponent
        Base-10 scaling exponent applied before integer packing.

    Returns
    -------
    bytes
        Binary integer byte sequence of length *byte_length*.
    """
    scaled = int(Decimal(str(value)).scaleb(-exponent).to_integral_value())
    return scaled.to_bytes(byte_length, byteorder=byteorder, signed=signed)


def comp_unpack(
    raw: bytes,
    signed: bool = True,
    byteorder: Literal["big", "little"] = "big",
    exponent: int = 0,
    as_decimal: bool = False,
) -> int | float | Decimal:
    """Unpack a COBOL binary integer (``COMP``, ``COMP-4``, ``COMP-5``, ``COMP-X``, ``BINARY-*``).

    Parameters
    ----------
    raw
        Raw binary integer bytes.
    signed
        Interpret as two's-complement signed when ``True``, unsigned when ``False``.
    byteorder
        Byte order (``'big'`` or ``'little'``).
    exponent
        Base-10 scaling exponent applied to the unpacked integer.
    as_decimal
        Return a :class:`decimal.Decimal` when ``True``.

    Returns
    -------
    int | float | Decimal
        Decoded numeric value.
    """
    if not raw:
        raise ValueError("Cannot unpack empty binary COMP byte sequence.")
    int_val = int.from_bytes(raw, byteorder=byteorder, signed=signed)
    return scale_integer(int_val, exponent, as_decimal=as_decimal)


MAX_PIC_REPEAT: int = 100_000


def expand_pic(pic: str, max_repeat: int = MAX_PIC_REPEAT) -> str:
    """Expand repeat counts in a COBOL ``PIC`` string (e.g. ``'S9(5)V9(2)'`` -> ``'S99999V99'``).

    Parameters
    ----------
    pic
        Raw COBOL ``PICTURE`` clause string.
    max_repeat
        Upper bound on any single repeat factor or expanded string length
        (guards against memory exhaustion on malformed copybooks).

    Returns
    -------
    str
        Uppercase expanded ``PICTURE`` string with repeat factors unfolded.
    """
    picstr = pic.strip().upper()
    while (match := PIC_REPEAT.search(picstr)) is not None:
        repeat = int(match.group("repeat"))
        if repeat > max_repeat:
            raise ValueError(
                f"COBOL PIC repeat count {repeat} exceeds maximum allowed ({max_repeat})."
            )
        section = match.group("section")
        if len(picstr) + len(section) * repeat > max_repeat:
            raise ValueError(f"Expanded COBOL PIC length exceeds maximum allowed ({max_repeat}).")
        picstr = PIC_REPEAT.sub(section * repeat, picstr, count=1)
    return picstr


def external_float_unpack(
    raw: bytes,
    expanded_pic: str = "",
    encoding: str = "ascii",
    decimal_comma: bool = False,
) -> float:
    """Decode a COBOL external floating-point ``USAGE DISPLAY`` item.

    Parameters
    ----------
    raw
        Encoded character bytes representing the external floating-point value.
    expanded_pic
        Expanded ``PICTURE`` clause used to infer implied ``V`` decimal placement.
    encoding
        Character encoding of *raw* (e.g. ``'ascii'``, ``'cp500'``).
    decimal_comma
        Interpret commas as decimal points when ``True``.

    Returns
    -------
    float
        Decoded floating-point value.
    """
    text = raw.decode(encoding, errors="replace").strip()
    if not text:
        return 0.0
    if decimal_comma:
        text = text.replace(",", ".")

    if "." not in text and "V" in expanded_pic.upper():
        mantissa_pic = expanded_pic.upper().split("E", 1)[0]
        frac_digits = mantissa_pic.split("V", 1)[1].count("9")
        mant_str, _, exp_str = text.upper().partition("E")
        sign = -1 if mant_str.startswith("-") else 1
        digits_only = mant_str.lstrip("+-")
        mant_val = sign * int(digits_only or "0") * (10.0 ** (-frac_digits))
        exp_val = int(exp_str) if exp_str else 0
        return mant_val * (10.0**exp_val)

    return float(text)


def float_to_ibm_hfp(value: float, size: Literal[4, 8] = 4) -> bytes:
    """Encode a Python ``float`` into 4-byte or 8-byte IBM Hexadecimal Floating-Point.

    Parameters
    ----------
    value
        Floating-point value to encode.
    size
        Target HFP storage size in bytes (``4`` short or ``8`` long).

    Returns
    -------
    bytes
        Big-endian IBM S/360 / z/Architecture HFP bytes.
    """
    if size not in (4, 8):
        raise ValueError(f"IBM HFP size must be 4 or 8, got {size}.")
    if value == 0.0:
        return b"\x00" * size

    sign_bit = 0x80 if value < 0 else 0x00
    abs_val = abs(value)
    _m2, e2 = math.frexp(abs_val)
    e16 = math.ceil(e2 / 4)
    frac = abs_val / math.ldexp(1.0, 4 * e16)
    while frac >= 1.0:
        frac /= 16.0
        e16 += 1
    while 0.0 < frac < 1.0 / 16.0:
        frac *= 16.0
        e16 -= 1

    biased = e16 + 64
    if not (0 <= biased <= 127):
        raise OverflowError(f"Value {value} out of IBM HFP exponent range.")

    frac_bits = (size - 1) * 8
    mantissa = round(frac * (1 << frac_bits))
    if mantissa == (1 << frac_bits):
        mantissa >>= 4
        biased += 1
        if biased > 127:
            raise OverflowError(f"Value {value} out of IBM HFP exponent range.")

    first_byte = sign_bit | (biased & 0x7F)
    return bytes([first_byte]) + mantissa.to_bytes(size - 1, byteorder="big", signed=False)


def ibm_hfp_to_float(raw: bytes) -> float:
    """Decode a 32-bit or 64-bit IBM Hexadecimal Floating-Point (HFP) byte sequence.

    Parameters
    ----------
    raw
        4-byte (short) or 8-byte (long) big-endian IBM HFP bytes.

    Returns
    -------
    float
        Decoded Python floating-point value.
    """
    if len(raw) not in (4, 8):
        raise ValueError(f"IBM HFP requires 4 or 8 bytes, got {len(raw)}.")
    if all(b == 0 for b in raw):
        return 0.0

    sign = -1.0 if (raw[0] & 0x80) else 1.0
    exponent = (raw[0] & 0x7F) - 64
    frac_bits = (len(raw) - 1) * 8
    mantissa_int = int.from_bytes(raw[1:], byteorder="big", signed=False)
    if mantissa_int == 0:
        return 0.0
    fraction = mantissa_int / (1 << frac_bits)
    return sign * fraction * math.ldexp(1.0, 4 * exponent)


def parse_numeric_edited(
    text: str,
    blank_when_zero: bool = False,
    decimal_comma: bool = False,
) -> float | None:
    """Parse a COBOL numeric-edited display string (e.g. ``'  $1,234.50-'``) to ``float``.

    Parameters
    ----------
    text
        Formatted numeric-edited string containing currency, suppression, or sign tokens.
    blank_when_zero
        Return ``0.0`` instead of ``None`` for all-blank fields when ``True``.
    decimal_comma
        Interpret commas as decimal points and periods as thousands separators when ``True``.

    Returns
    -------
    float | None
        Parsed numeric value, or ``None`` for blank fields when *blank_when_zero* is ``False``.
    """
    cleaned = text.strip()
    if not cleaned:
        return 0.0 if blank_when_zero else None

    negative = False
    upper = cleaned.upper()
    if upper.endswith(("CR", "DB")):
        negative = True
        cleaned = cleaned[:-2].strip()
    elif cleaned.endswith("-"):
        negative = True
        cleaned = cleaned[:-1].strip()
    elif cleaned.endswith("+"):
        cleaned = cleaned[:-1].strip()

    if decimal_comma:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")

    cleaned = cleaned.replace("$", "").replace("*", "").replace(" ", "")
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:]

    if not cleaned:
        return 0.0
    if cleaned[-1] in ASCII_OVERPUNCH_POS:
        cleaned = cleaned[:-1] + ASCII_OVERPUNCH_POS[cleaned[-1]]
    elif cleaned[-1] in ASCII_OVERPUNCH_NEG:
        negative = True
        cleaned = cleaned[:-1] + ASCII_OVERPUNCH_NEG[cleaned[-1]]
    elif cleaned[0] in ASCII_OVERPUNCH_POS:
        cleaned = ASCII_OVERPUNCH_POS[cleaned[0]] + cleaned[1:]
    elif cleaned[0] in ASCII_OVERPUNCH_NEG:
        negative = True
        cleaned = ASCII_OVERPUNCH_NEG[cleaned[0]] + cleaned[1:]
    val = float(cleaned)
    return -val if negative else val


def predict_encoding(file_path: str | pathlib.Path, n_lines: int = 20) -> str:
    """Predict a file's character encoding via :mod:`chardet`, falling back to ``'ascii'``.

    Parameters
    ----------
    file_path
        Path to the file to inspect.
    n_lines
        Number of leading lines to sample for detection.

    Returns
    -------
    str
        Detected encoding name, or ``'ascii'`` if detection is inconclusive.
    """
    path = pathlib.Path(file_path)
    with path.open(mode="rb") as fh:
        rawdata = b"".join(fh.readline() for _ in range(n_lines))
    detected = chardet.detect(rawdata).get("encoding")
    logger.trace("Predicted encoding for {}: {}", path, detected or "ascii")
    return detected or "ascii"


def zoned_pack(
    value: int | float | Decimal,
    digits: int,
    encoding: str = "ascii",
    signed: bool = False,
    sign_mode: SignMode = SignMode.TRAILING_OVERPUNCH,
    exponent: int = 0,
) -> bytes:
    """Pack a numeric value into COBOL ``USAGE DISPLAY`` zoned decimal bytes.

    Parameters
    ----------
    value
        Numeric value to encode.
    digits
        Total number of digit positions in the ``PIC`` clause.
    encoding
        Target character encoding (EBCDIC codepage or ASCII-compatible encoding).
    signed
        Encode sign information when ``True``.
    sign_mode
        Sign placement/encoding convention (leading/trailing, overpunch/separate).
    exponent
        Base-10 scaling exponent applied before encoding digits.

    Returns
    -------
    bytes
        Encoded zoned decimal byte sequence.
    """
    dec = Decimal(str(value))
    negative = dec < 0
    if negative and not signed:
        raise ValueError("Cannot pack negative value into unsigned zoned decimal field.")

    scaled = int(abs(dec).scaleb(-exponent).to_integral_value())
    digit_str = str(scaled).zfill(digits)
    if len(digit_str) > digits:
        raise ValueError(f"Value {value} exceeds {digits}-digit zoned decimal capacity.")

    if signed and sign_mode is SignMode.LEADING_SEPARATE:
        return (("-" if negative else "+") + digit_str).encode(encoding)
    if signed and sign_mode is SignMode.TRAILING_SEPARATE:
        return (digit_str + ("-" if negative else "+")).encode(encoding)

    if is_ebcdic(encoding):
        out = bytearray(0xF0 | int(ch) for ch in digit_str)
        if signed:
            idx = 0 if sign_mode is SignMode.LEADING_OVERPUNCH else len(out) - 1
            zone = 0xD0 if negative else 0xC0
            out[idx] = zone | (out[idx] & 0x0F)
        return bytes(out)

    chars = list(digit_str)
    if signed:
        idx = 0 if sign_mode is SignMode.LEADING_OVERPUNCH else len(chars) - 1
        chars[idx] = (DIGIT_TO_ASCII_NEG if negative else DIGIT_TO_ASCII_POS)[chars[idx]]
    return "".join(chars).encode(encoding)


def zoned_unpack(
    raw: bytes,
    encoding: str = "ascii",
    signed: bool = False,
    sign_mode: SignMode = SignMode.TRAILING_OVERPUNCH,
    exponent: int = 0,
    as_decimal: bool = False,
) -> int | float | Decimal:
    """Unpack a COBOL ``USAGE DISPLAY`` zoned decimal byte sequence.

    Parameters
    ----------
    raw
        Encoded zoned decimal bytes.
    encoding
        Character encoding of *raw* (EBCDIC or ASCII-compatible).
    signed
        Decode sign overpunch or separate sign character when ``True``.
    sign_mode
        Sign placement/encoding convention (leading/trailing, overpunch/separate).
    exponent
        Base-10 scaling exponent applied to the decoded integer.
    as_decimal
        Return a :class:`decimal.Decimal` when ``True``.

    Returns
    -------
    int | float | Decimal
        Decoded numeric value.
    """
    if not raw:
        raise ValueError("Cannot unpack empty zoned decimal bytes.")
    if all(b == 0x00 for b in raw):
        return scale_integer(0, exponent, as_decimal=as_decimal)

    if signed and sign_mode in (SignMode.LEADING_SEPARATE, SignMode.TRAILING_SEPARATE):
        text = raw.decode(encoding).strip()
        if not text:
            return scale_integer(0, exponent, as_decimal=as_decimal)
        if sign_mode is SignMode.TRAILING_SEPARATE:
            sign = -1 if text.endswith("-") else 1
            digits_str = text[:-1].strip() if text[-1] in "+-" else text
        else:
            sign = -1 if text.startswith("-") else 1
            digits_str = text[1:].strip() if text[0] in "+-" else text
        return scale_integer(sign * int(digits_str or "0"), exponent, as_decimal=as_decimal)

    if is_ebcdic(encoding):
        if all(b == 0x40 for b in raw):
            return scale_integer(0, exponent, as_decimal=as_decimal)
        sign = 1
        sign_idx = 0 if (signed and sign_mode is SignMode.LEADING_OVERPUNCH) else len(raw) - 1
        digits_list: list[str] = []
        for idx, b in enumerate(raw):
            if b == 0x40:
                continue
            zone = (b >> 4) & 0x0F
            digit = b & 0x0F
            if digit > 9:
                raise ValueError(f"Invalid EBCDIC zoned digit byte 0x{b:02X}.")
            if signed and idx == sign_idx:
                if zone in (0xD, 0xB):
                    sign = -1
                elif zone in (0xC, 0xF, 0xA, 0xE):
                    sign = 1
                else:
                    raise ValueError(f"Invalid EBCDIC sign zone 0x{zone:X} in byte 0x{b:02X}.")
            digits_list.append(str(digit))
        int_val = sign * int("".join(digits_list) or "0")
        return scale_integer(int_val, exponent, as_decimal=as_decimal)

    text = raw.decode(encoding).strip()
    if not text:
        return scale_integer(0, exponent, as_decimal=as_decimal)

    sign = 1
    if text[0] in "+-":
        sign = -1 if text[0] == "-" else 1
        text = text[1:].strip()
    elif text[-1] in "+-":
        sign = -1 if text[-1] == "-" else 1
        text = text[:-1].strip()
    elif signed:
        pos = 0 if sign_mode is SignMode.LEADING_OVERPUNCH else len(text) - 1
        ch = text[pos]
        if ch in ASCII_OVERPUNCH_POS:
            text = text[:pos] + ASCII_OVERPUNCH_POS[ch] + text[pos + 1 :]
        elif ch in ASCII_OVERPUNCH_NEG:
            sign = -1
            text = text[:pos] + ASCII_OVERPUNCH_NEG[ch] + text[pos + 1 :]

    return scale_integer(sign * int(text or "0"), exponent, as_decimal=as_decimal)


# ---------------------------------------------------------------------------
# Internal Shared Codec Helpers
# ---------------------------------------------------------------------------


def compute_decimal_exponent(expanded_pic: str) -> int:
    """Return base-10 exponent implied by ``V`` and ``P`` symbols in a PIC string.

    Parameters
    ----------
    expanded_pic
        Expanded uppercase COBOL ``PICTURE`` string.

    Returns
    -------
    int
        Base-10 exponent (negative for fractional digits, positive for trailing ``P``).
    """
    body = expanded_pic.lstrip("S")
    if "V" in body:
        before_v, after_v = body.split("V", 1)
        if "P" in before_v:
            return before_v.count("P")
        return -(after_v.count("9") + after_v.count("P"))
    if body.startswith("P"):
        return -(body.count("P") + body.count("9"))
    if body.endswith("P"):
        return body.count("P")
    return 0


def is_ebcdic(encoding: str) -> bool:
    """Return ``True`` if *encoding* refers to an EBCDIC codepage.

    Parameters
    ----------
    encoding
        Character encoding name (e.g. ``'cp500'``, ``'cp037'``, ``'ascii'``).

    Returns
    -------
    bool
        ``True`` for recognized EBCDIC codepages, ``False`` otherwise.
    """
    norm = encoding.lower().replace("-", "").replace("_", "")
    return norm in EBCDIC_ENCODINGS or norm.startswith(("cp037", "cp500", "cp114", "ebcdic"))


def scale_integer(
    value: int,
    exponent: int,
    as_decimal: bool = False,
) -> int | float | Decimal:
    """Scale an integer by ``10 ** exponent``.

    Parameters
    ----------
    value
        Unscaled integer value.
    exponent
        Base-10 exponent to apply.
    as_decimal
        Return an exact :class:`decimal.Decimal` when ``True``.

    Returns
    -------
    int | float | Decimal
        Scaled numeric value.
    """
    if exponent == 0:
        return Decimal(value) if as_decimal else value
    scaled = Decimal(value).scaleb(exponent)
    if as_decimal:
        return scaled
    if exponent > 0:
        return int(scaled)
    return float(scaled)
