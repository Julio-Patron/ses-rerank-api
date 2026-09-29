#!/usr/bin/env python3
"""Validate that release tags and Python/Rust package versions agree."""

import argparse
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def project_version(path: Path) -> str:
    with path.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def crate_version(path: Path) -> str:
    with path.open("rb") as handle:
        return tomllib.load(handle)["package"]["version"]


def validate(tag: str = "") -> tuple[str, str]:
    ses_version = project_version(ROOT / "pyproject.toml")
    rust_python_version = project_version(ROOT / "core_rs" / "pyproject.toml")
    rust_crate_version = crate_version(ROOT / "core_rs" / "Cargo.toml")

    if rust_python_version != rust_crate_version:
        raise ValueError(
            "core_rs/pyproject.toml and core_rs/Cargo.toml versions differ: "
            f"{rust_python_version} != {rust_crate_version}"
        )
    if tag and tag != f"v{ses_version}":
        raise ValueError(
            f"release tag {tag!r} must match ses-core version v{ses_version}"
        )
    return ses_version, rust_crate_version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    try:
        ses_version, rust_version = validate(args.tag)
    except ValueError as error:
        parser.error(str(error))

    print(f"ses-core={ses_version}")
    print(f"jas_vector_core={rust_version}")
    if args.tag:
        print(f"release-tag={args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
