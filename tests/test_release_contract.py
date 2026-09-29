from pathlib import Path
import subprocess
import sys
import tomllib

from scripts.validate_release import validate


ROOT = Path(__file__).resolve().parents[1]


def test_release_versions_and_tag_are_consistent():
    assert validate("v2.0.3") == ("2.0.3", "0.1.0")


def test_release_validator_rejects_a_mismatched_tag():
    result = subprocess.run(
        [sys.executable, "scripts/validate_release.py", "--tag", "v9.9.9"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "must match ses-core version v2.0.3" in result.stderr


def test_ses_core_build_embeds_the_rust_extension():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)

    assert config["build-system"]["build-backend"] == "maturin"
    assert config["tool"]["maturin"]["manifest-path"] == "core_rs/Cargo.toml"
    assert config["tool"]["maturin"]["python-packages"] == ["ses"]
    assert config["tool"]["maturin"]["features"] == ["python"]
    assert config["tool"]["maturin"]["include"] == [
        {"path": "LICENSE", "format": "sdist"}
    ]


def test_release_workflow_uses_oidc_and_fails_if_crates_token_is_missing():
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )

    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "skip-existing: true" in workflow
    assert "PYPI_API_TOKEN" not in workflow
    assert "CARGO_REGISTRY_TOKEN is required" in workflow
    assert "if: env.CARGO_REGISTRY_TOKEN != ''" not in workflow
    assert "Crate version already exists; skipping publication." in workflow
    assert "python scripts/check_crate_publication.py" in workflow


def test_ci_runs_the_live_crates_io_preflight():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "python scripts/check_crate_publication.py --allow-missing" in workflow
