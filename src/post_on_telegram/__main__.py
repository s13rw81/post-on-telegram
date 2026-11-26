# src/post_on_telegram/__main__.py
"""Allow running the package as a module: python -m post_on_telegram."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
