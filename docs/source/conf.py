"""Sphinx documentation configuration for DataSpector."""

from __future__ import annotations

import pathlib
import sys

# Ensure the src package is importable when building docs directly from the checkout
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from dataspector import __version__ as _pkg_version

# -- Project information -----------------------------------------------------

project = "DataSpector"
author = "Aaron Berndsen"
copyright = "2026, Aaron Berndsen"
release = _pkg_version
version = ".".join(release.split(".")[:2])

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "numpydoc",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
source_suffix = {".rst": "restructuredtext"}
master_doc = "index"

# -- Autodoc & NumPyDoc configuration ----------------------------------------

autoclass_content = "both"
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autosummary_generate = False

numpydoc_show_class_members = False
numpydoc_class_members_toctree = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
}

# -- HTML output (PyData Sphinx Theme) ---------------------------------------

html_theme = "pydata_sphinx_theme"
html_title = f"DataSpector {release} Documentation"
html_static_path: list[str] = []

html_sidebars = {
    "index": [],
}

html_theme_options = {
    "logo": {"text": "DataSpector"},
    "show_toc_level": 2,
    "navigation_depth": 3,
    "show_nav_level": 2,
    "navbar_start": ["navbar-logo", "version-badge"],
    "navbar_end": ["theme-switcher"],
    "footer_start": ["copyright"],
    "footer_center": ["package-version"],
    "footer_end": ["sphinx-version"],
}
