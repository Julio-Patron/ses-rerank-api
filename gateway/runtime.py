"""Process-wide runtime flags.

DEBUG is read from the environment on every check so a production process
cannot ship with a hardcoded development bypass.
"""

import os


def debug_enabled() -> bool:
    return os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
