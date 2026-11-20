"""Shared pytest fixtures and sample data paths for DataSpector tests."""

from __future__ import annotations

import pathlib

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="session")
def project_root() -> pathlib.Path:
    """Return the repository root directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def data_dir() -> pathlib.Path:
    """Return the ``tests/data`` fixtures directory."""
    return DATA_DIR


@pytest.fixture(scope="session")
def sample_csv() -> pathlib.Path:
    """Return path to ``sample_csv.csv``."""
    return DATA_DIR / "sample_csv.csv"


@pytest.fixture(scope="session")
def sample_csv0() -> pathlib.Path:
    """Return path to ``sample_csv0.csv`` (differs by one value from ``sample_csv.csv``)."""
    return DATA_DIR / "sample_csv0.csv"


@pytest.fixture(scope="session")
def sample_csv1() -> pathlib.Path:
    """Return path to ``sample_csv1.csv`` (includes ``CC code`` column)."""
    return DATA_DIR / "sample_csv1.csv"


@pytest.fixture(scope="session")
def sample_fwf() -> pathlib.Path:
    """Return path to ``sample_fwf.txt``."""
    return DATA_DIR / "sample_fwf.txt"


@pytest.fixture(scope="session")
def sample_excel() -> pathlib.Path:
    """Return path to ``sample_excel.xlsx``."""
    return DATA_DIR / "sample_excel.xlsx"


@pytest.fixture(scope="session")
def sample_sqlite() -> pathlib.Path:
    """Return path to ``sample_sqlite.sqlite``."""
    return DATA_DIR / "sample_sqlite.sqlite"


@pytest.fixture(scope="session")
def sample_cobol_students() -> str:
    """Return bracketed ``[copybook][data]`` locator for student COBOL data."""
    return f"[{DATA_DIR / 'sample_cobol_students.cbl'}][{DATA_DIR / 'sample_cobol_students.dat'}]"


@pytest.fixture(scope="session")
def sample_cobol_mainframe() -> str:
    """Return bracketed ``[copybook][data]`` locator for binary EBCDIC mainframe data."""
    return f"[{DATA_DIR / 'sample_cobol_mainframe.cbl'}][{DATA_DIR / 'sample_cobol_mainframe.dat'}]"


@pytest.fixture(scope="session")
def sample_cobol_exotic() -> str:
    """Return bracketed ``[copybook][data]`` locator for exotic COBOL data types sample."""
    return f"[{DATA_DIR / 'sample_cobol_exotic.cbl'}][{DATA_DIR / 'sample_cobol_exotic.dat'}]"


@pytest.fixture(scope="session")
def sample_driver() -> pathlib.Path:
    """Return path to root ``test_driver.xlsx``."""
    return PROJECT_ROOT / "test_driver.xlsx"
