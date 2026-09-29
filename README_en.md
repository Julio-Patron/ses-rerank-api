<div align="center">
  <h1>SES Core: Semantic Engine</h1>
  <p><strong>An offline-first RAG engine for private documents, with a Gateway, Portal, and optional Rust acceleration.</strong></p>

  [![Python](https://img.shields.io/badge/Python-3.9--3.12-blue.svg)](https://www.python.org)
  [![Status](https://img.shields.io/badge/Status-Beta-orange.svg)](#verified-status)
  [![CI](https://github.com/elbuilder77/Semantic-Engine/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/elbuilder77/Semantic-Engine/actions/workflows/ci.yml)
  [![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

  *[Versión en español](README.md)*
</div>

---

## What SES is

SES turns local documents into a searchable semantic index. The Python core
extracts, chunks, embeds, and queries through Qdrant; Redis provides caching and
distributed controls; Ollama generates local answers; the FastAPI Gateway
exposes HTTP contracts; and the Next.js Portal provides the administration UI.

Offline-first means documents and queries can stay in operator-controlled
infrastructure. It does not mean that installation has zero network
dependencies: packages, images, and models must be provisioned before running
without a network.

## Verified status

This repository is a technical beta. Live code and executable validation are
the source of truth.

| Surface | Verified state | Current boundary |
|---|---|---|
| Python core | Pytest validates core behavior, SQLite, and controlled network failures | Successful E2E against real Qdrant/Redis/Ollama remains open |
| Gateway | Auth, SQLite telemetry, CORS, and rate limiting are hardened | PostgreSQL validation and full Docker parity remain open |
| Portal | Next.js 16; lint, build, and eight administration routes validated | Real-service E2E remains open |
| Rust | CPython 3.12 wheel, tests, Clippy, and NumPy API | Optional and used for candidate batches larger than 50 |
| CI | Portal, Python, Rust, wheel, Pytest, and synthetic smoke in GitHub Actions | Does not replace end-to-end testing |
| Packaging | `ses-core` 2.0.3 on PyPI and `jas_vector_core` 0.1.0 on crates.io; five ABI3 wheels, sdist, and checksums verified | Published versions are immutable; each correction requires a new version |
| Mount Mode | Reindexing ingests first and preserves pending cleanup IDs in the manifest | No distributed transaction with Qdrant |

## Architecture

~~~text
Read-only documents
        |
        v
Watcher / Scanner ---> Parsing and chunking ---> Local embeddings
                                                |
                                                v
Next.js Portal ---> FastAPI Gateway ---> Qdrant / Redis / Ollama
                           |
                           +-- PDF reports
                           +-- keys and analytics
                           +-- optional Rust reranking
~~~

Main directories:

- <code>ses/</code>: RAG library, providers, reports, and watcher.
- <code>gateway/</code>: FastAPI, static dashboard, and local SQLite state.
- <code>portal/</code>: Next.js administration client.
- <code>core_rs/</code>: the <code>jas_vector_core</code> PyO3 extension.
- <code>tests/</code>: Python tests and a synthetic microbenchmark.

## Install from PyPI

~~~powershell
python -m pip install "ses-core==2.0.3"
~~~

Version 2.0.3 is published through Trusted Publishing (OIDC) with ABI3 wheels
for Windows, Linux, and macOS, plus the sdist. Artifacts and checksums are also
available from [GitHub Release v2.0.3](https://github.com/elbuilder77/Semantic-Engine/releases/tag/v2.0.3).
The standalone crate is published as
[`jas_vector_core` 0.1.0](https://crates.io/crates/jas_vector_core/0.1.0).

## Install from source

~~~powershell
git clone https://github.com/elbuilder77/Semantic-Engine.git
cd Semantic-Engine
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,server]"
~~~

Package metadata declares Python 3.9–3.12 compatibility; CI currently validates
CPython 3.12.

### Optional Rust extension

~~~powershell
python -m pip install "maturin>=1,<2"
python -m maturin build --release --manifest-path core_rs/Cargo.toml --interpreter python --out core_rs/target/wheels
$wheel = Get-ChildItem core_rs/target/wheels/*.whl | Select-Object -First 1
python -m pip install --force-reinstall $wheel.FullName
~~~

The Rust wheel is separate from the base Python package. SES keeps the Python
path when the module is missing or cannot be used.

## Secure configuration

Use <code>.env.example</code> as the variable inventory. Generate unique local
keys without printing them:

~~~powershell
Copy-Item .env.example .env
python scripts/rotate_local_secrets.py
~~~

The command rotates:

- <code>GATEWAY_ADMIN_KEY</code> in <code>.env</code>;
- previous local administrative SQLite keys when present.

Both secret files and local databases are ignored by Git. In production, use a
secret manager, keep <code>DEBUG=false</code>, and configure non-placeholder
Qdrant and Redis credentials. A Redis outage blocks protected production routes;
the in-memory fallback exists only with <code>DEBUG=true</code>.

The Portal stores the Gateway URL and key in browser <code>localStorage</code>.
Never place an API key in a <code>NEXT_PUBLIC_*</code> variable.

## Local services

The canonical Compose file starts pinned local dependencies with named volumes
and loopback-only ports. Copy the inventory and configure unique values:

~~~powershell
Copy-Item .env.compose.example .env.compose
# Set QDRANT_API_KEY and REDIS_PASSWORD in .env.compose
docker compose --env-file .env.compose up -d
docker compose --env-file .env.compose ps
~~~

This file starts Qdrant, Redis, and Ollama; it does not run the Gateway or
Portal. The configured Ollama and SentenceTransformers models must be
provisioned before network-free operation.

## Run the Gateway and Portal

Gateway:

~~~powershell
python gateway/run.py
~~~

The Gateway listens on <http://127.0.0.1:8000>. Main routes include:

- <code>POST /api/v1/search</code>
- <code>POST /api/v1/ingest/file</code>
- <code>POST /api/v1/ingest/text</code>
- <code>GET /api/v1/documents</code>
- <code>DELETE /api/v1/documents/{doc_id}</code>
- <code>GET /api/v1/health</code> and <code>/api/v1/stats</code>
- key, analytics, and report administration under <code>/api/v1/admin</code>

Portal:

~~~powershell
npm ci --prefix portal
npm --prefix portal run dev -- --hostname 127.0.0.1 --port 3000
~~~

Open <http://127.0.0.1:3000/settings>, enter the Gateway URL and a rotated
administrator key, and use **Test Connection**. Implemented routes are
<code>/dashboard</code>, <code>/search</code>, <code>/documents</code>,
<code>/keys</code>, <code>/analytics</code>, <code>/reports</code>, and
<code>/settings</code>.

## Direct library usage

~~~python
import asyncio

from ses.core.llm import LocalLLMProvider
from ses.core.rag import OfflineRAGEngine


async def main():
    engine = OfflineRAGEngine()

    with open("contract.pdf", "rb") as source:
        await engine.ingest_file(
            namespace="legal",
            file_obj=source,
            filename="contract.pdf",
            metadata={"source_path": "contract.pdf"},
        )

    search = await engine.search(
        namespace="legal",
        query="What are the termination conditions?",
        top_k=5,
    )

    answer = LocalLLMProvider().generate_answer(
        query="Summarize the termination conditions.",
        context_docs=search["results"],
    )
    print(answer)


asyncio.run(main())
~~~

## Mount Mode

The watcher treats observed directories as read-only sources. It performs an
initial scan, filters PDF/DOCX/XLSX/CSV/TXT/MD files, calculates SHA-256, stores
<code>source_path</code>, and skips insertion when content is unchanged.
Filesystem events are grouped with per-path debounce.

Replacing a changed file ingests the new version first. If deleting the old
version fails, its ID remains under <code>pending_delete_document_ids</code> in
the manifest and is retried during the next scan. The flow is recoverable but
is not a distributed Qdrant transaction. See
[docs/MOUNT_MODE.md](docs/MOUNT_MODE.md).

## Validation

Local gates corresponding to CI:

~~~powershell
pytest -q -p no:cacheprovider
npm --prefix portal run lint
npm --prefix portal run test
npm --prefix portal run build
cargo fmt --manifest-path core_rs/Cargo.toml -- --check
cargo test --manifest-path core_rs/Cargo.toml
cargo clippy --manifest-path core_rs/Cargo.toml --all-targets -- -D warnings
~~~

The command above excludes tests marked as <code>integration</code> by default.
With Qdrant and Redis available through the documented Compose stack, run the
E2E gate explicitly:

~~~powershell
pytest -q -m integration tests/integration
~~~

[GitHub Actions](https://github.com/elbuilder77/Semantic-Engine/actions) also
builds and installs the CPython 3.12 Rust wheel. The manual packaging workflow
builds and verifies the sdist/wheel but skips publication. Published GitHub
releases activate the PyPI OIDC and crates.io publication jobs; v2.0.3 passed
that complete path.

The microbenchmark in <code>tests/performance/benchmark.py</code> uses synthetic
vectors. It is a reproducible smoke, not end-to-end ingestion, disk, Qdrant, or
LLM latency, and its numbers are not an SLA.

## Production gaps

- A reproducible dependency Compose exists; full Gateway/Portal Docker parity is not proven.
- SQLite and Qdrant/Redis/Ollama connection failures are covered; successful real-service E2E remains open.
- Persistent telemetry is validated with SQLite; real PostgreSQL validation remains open.
- No named 40–60 GB ingestion/retrieval workload has been executed.
- Changed-file reindexing is manifest-recoverable but not cross-process atomic.
- The repository does not prove corporate SLAs, complete RBAC, or HIPAA/GDPR
  certification.

## Documentation

- [gateway/README.md](gateway/README.md): Gateway operation and contracts.
- [portal/README.md](portal/README.md): Portal routes and validation.
- [docs/MOUNT_MODE.md](docs/MOUNT_MODE.md): watcher contract and limits.

## License

SES Core is distributed under GPLv3. Managed offerings, SLAs, and regulatory
certifications are future commercial objectives, not properties demonstrated
by the current repository state.
