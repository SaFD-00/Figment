"""`python -m app.cli` → run the CLI and propagate its exit code."""
import sys

from app.cli.app import main

if __name__ == "__main__":
    sys.exit(main())
