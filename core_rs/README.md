# jas_vector_core

High-performance vector cosine similarity search and re-ranking engine written in Rust with PyO3 bindings, designed for SES Core (Semantic Engine System).

## Features
- **Zero-copy NumPy Memory Views**: Direct execution over C-contiguous matrix buffers without copying.
- **Standalone Rust API**: Hardware-optimized cosine similarity search over `&[f32]` slices.
- **Threshold Filtering & Top-K Ranking**: Fast single-pass scoring and partial sorting.

## Usage in Rust

```rust
use jas_vector_core::cosine_similarity_scores;

let query = vec![1.0, 0.0, 0.0];
let docs = vec![
    vec![1.0, 0.0, 0.0],
    vec![0.0, 1.0, 0.0],
    vec![0.7, 0.7, 0.0],
];

let top_results = cosine_similarity_scores(&query, &docs, 2, None).unwrap();
for (idx, score) in top_results {
    println!("Doc {idx}: score = {score:.4}");
}
```

## Usage in Python

```python
import numpy as np
import jas_vector_core

query = np.array([1.0, 0.0], dtype=np.float32)
docs = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)

results = jas_vector_core.cosine_similarity_search_numpy(query, docs, top_k=5)
```

## License
GPL-3.0-only
