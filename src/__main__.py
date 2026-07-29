"""Allow ``python -m src <command>``."""

import sys

from .cli import main

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BrokenPipeError:
        sys.stdout = None
        raise SystemExit(1)
