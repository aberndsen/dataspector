"""COBOL copybook parser, data decoder, and modern format converter.

Organized into four focused submodules:

* :mod:`dataspector.coboller.copybook` —
  :class:`~dataspector.coboller.copybook.Copybook`,
  :class:`~dataspector.coboller.copybook.GroupItem`,
  :class:`~dataspector.coboller.copybook.ElementaryItem`,
  :class:`~dataspector.coboller.copybook.ConditionName`,
  :class:`~dataspector.coboller.copybook.ResolvedItem`, and
  :func:`~dataspector.coboller.copybook.parse_copybook`
* :mod:`dataspector.coboller.codecs` — pure binary/text pack & unpack codecs
  (``COMP-3``, ``COMP-6``, ``COMP``/``COMP-5``/``COMP-X``, ``COMP-1``/``COMP-2``
  IEEE & IBM HFP, zoned decimal, numeric-edited, external float, ``USAGE BIT``)
* :mod:`dataspector.coboller.parser` — fixed-format & free-format COBOL line
  cleaning and clause parsing
* :mod:`dataspector.coboller.constants` —
  :class:`~dataspector.coboller.constants.Usage`,
  :class:`~dataspector.coboller.constants.SignMode`,
  :class:`~dataspector.coboller.constants.DataCategory`, compiled regexes, and
  lookup tables

References
----------
* IBM Enterprise COBOL Language Reference — PICTURE & USAGE clauses:
  https://www.ibm.com/docs/en/cobol-zos/latest?topic=division-data-description-entry
* IBM Enterprise COBOL — UTF-8 (``PIC U`` / ``BYTE-LENGTH``) & National (``PIC N``):
  https://www.ibm.com/docs/en/cobol-zos/latest?topic=clause-usage
* IBM z/Architecture Hexadecimal Floating-Point (HFP):
  https://en.wikipedia.org/wiki/IBM_hexadecimal_floating-point
* GnuCOBOL Programmer's Guide (``COMP-6``, ``COMP-X``, ``BINARY-*``, ``FLOAT-*``, ``USAGE BIT``):
  https://gnucobol.sourceforge.io/guides.html
* Reading COBOL Layouts:
  http://www.3480-3590-data-conversion.com/article-reading-cobol-layouts-1.html
* COBOL Code Format:
  https://en.wikipedia.org/wiki/COBOL#Code_format
"""

from __future__ import annotations

from dataspector.coboller.codecs import (
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
    parse_numeric_edited,
    predict_encoding,
    zoned_pack,
    zoned_unpack,
)
from dataspector.coboller.constants import (
    PIC_FLOAT,
    PIC_INT,
    PIC_REPEAT,
    DataCategory,
    FieldKind,
    SignMode,
    Usage,
)
from dataspector.coboller.copybook import (
    Condition,
    ConditionName,
    CopyBook,
    Copybook,
    ElementaryItem,
    Field,
    Group,
    GroupItem,
    ResolvedField,
    ResolvedItem,
    parse_copybook,
)

__all__ = [
    "PIC_FLOAT",
    "PIC_INT",
    "PIC_REPEAT",
    "Condition",
    "ConditionName",
    "CopyBook",
    "Copybook",
    "DataCategory",
    "ElementaryItem",
    "Field",
    "FieldKind",
    "Group",
    "GroupItem",
    "ResolvedField",
    "ResolvedItem",
    "SignMode",
    "Usage",
    "bit_pack",
    "bit_unpack",
    "comp3_pack",
    "comp3_unpack",
    "comp3decompress",
    "comp6_pack",
    "comp6_unpack",
    "comp_float_pack",
    "comp_float_unpack",
    "comp_pack",
    "comp_unpack",
    "expand_pic",
    "external_float_unpack",
    "float_to_ibm_hfp",
    "ibm_hfp_to_float",
    "parse_copybook",
    "parse_numeric_edited",
    "predict_encoding",
    "zoned_pack",
    "zoned_unpack",
]
