"""Shared test setup: unit tests stay offline and never need the native wheel."""

import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("DEBUG", "true")

# Soft-mock optional native/network deps only when they are not installed, so the
# suite runs on machines without the Rust extension or the redis package.
for _mod in ("jas_vector_core", "redis", "redis.asyncio"):
    if _mod in sys.modules:
        continue
    try:
        __import__(_mod)
    except ImportError:
        sys.modules[_mod] = MagicMock()
