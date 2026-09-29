from pathlib import Path

from scripts.deploy_production import generate_production_env


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_generated_production_env_uses_canonical_gateway_portal_names(tmp_path):
    env_path = tmp_path / ".env.prod"

    assert generate_production_env(env_path)

    contents = env_path.read_text(encoding="utf-8")
    assert "GATEWAY_CORS_ORIGINS=" in contents
    assert "NEXT_PUBLIC_SES_API_URL=" in contents
    assert "\nCORS_ALLOWED_ORIGINS=" not in contents
    assert "\nNEXT_PUBLIC_API_URL=" not in contents


def test_compose_passes_portal_url_at_build_time_and_uses_gateway_healthz():
    compose = (REPOSITORY_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    portal_dockerfile = (REPOSITORY_ROOT / "portal" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    gateway_dockerfile = (REPOSITORY_ROOT / "gateway" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    expected_portal_url = (
        'NEXT_PUBLIC_SES_API_URL: "${NEXT_PUBLIC_SES_API_URL:-http://localhost:8000}"'
    )
    assert expected_portal_url in compose
    assert "ARG NEXT_PUBLIC_SES_API_URL=http://localhost:8000" in portal_dockerfile
    assert "ENV NEXT_PUBLIC_SES_API_URL=$NEXT_PUBLIC_SES_API_URL" in portal_dockerfile
    assert "http://127.0.0.1:8000/healthz" in gateway_dockerfile
