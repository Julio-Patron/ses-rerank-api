"""
RSS stability harness for jas_vector_core.cosine_similarity_search_numpy.

Pass criterion (static + runtime):
- core_rs has no Box::leak / mem::forget in the search path (reviewed).
- After warmup, N repeated searches on a fixed matrix must not grow process RSS
  by more than MAX_RSS_GROWTH_MB (allows allocator freelist noise).

Skipped when the real extension is not built (MagicMock placeholders do not count).
"""

from __future__ import annotations

import gc
import importlib
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

WARMUP_ITERS = 5
STRESS_ITERS = 200
N_DOCS = 1000
DIM = 384
TOP_K = 10
MAX_RSS_GROWTH_MB = 32.0


def _load_real_jas_vector_core():
    """Import the real extension or skip if only a test MagicMock is present."""
    existing = sys.modules.get("jas_vector_core")
    if isinstance(existing, MagicMock):
        pytest.skip("jas_vector_core not built (MagicMock placeholder in sys.modules)")

    try:
        mod = importlib.import_module("jas_vector_core")
    except ImportError:
        pytest.skip("jas_vector_core not built")

    if isinstance(mod, MagicMock) or not hasattr(mod, "cosine_similarity_search_numpy"):
        pytest.skip("jas_vector_core not built")

    # Reject pure MagicMock callables
    fn = mod.cosine_similarity_search_numpy
    if isinstance(fn, MagicMock):
        pytest.skip("jas_vector_core not built (mocked)")
    return mod


def _rss_mb() -> float:
    try:
        import psutil
    except ImportError:
        pytest.skip("psutil not installed; install to run RSS leak harness")
    return psutil.Process().memory_info().rss / (1024 * 1024)


@pytest.mark.performance
def test_jas_vector_core_rss_stable_under_repeated_search():
    jas_vector_core = _load_real_jas_vector_core()

    rng = np.random.default_rng(42)
    query = np.ascontiguousarray(rng.standard_normal(DIM, dtype=np.float32))
    docs = np.ascontiguousarray(rng.standard_normal((N_DOCS, DIM), dtype=np.float32))

    for _ in range(WARMUP_ITERS):
        jas_vector_core.cosine_similarity_search_numpy(query, docs, TOP_K)

    gc.collect()
    rss_before = _rss_mb()

    for _ in range(STRESS_ITERS):
        results = jas_vector_core.cosine_similarity_search_numpy(query, docs, TOP_K)
        assert len(results) == TOP_K

    gc.collect()
    rss_after = _rss_mb()
    growth = rss_after - rss_before

    assert growth < MAX_RSS_GROWTH_MB, (
        f"RSS grew by {growth:.1f} MB over {STRESS_ITERS} searches "
        f"(limit {MAX_RSS_GROWTH_MB} MB). Possible native leak."
    )


def test_jas_vector_core_importable_or_skipped():
    """Documents skip path when the Rust extension is not built."""
    mod = _load_real_jas_vector_core()
    assert hasattr(mod, "cosine_similarity_search_numpy")
