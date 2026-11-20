"""Enable ``python -m dataspector`` execution."""

from __future__ import annotations

import sys

from dataspector.cli import main

if __name__ == "__main__":
    sys.exit(main())
