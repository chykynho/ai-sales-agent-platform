from __future__ import annotations

from pathlib import Path
import tomllib

from app.core.config import _default_app_version, settings

ROOT = Path(__file__).resolve().parents[1]


def test_v015_version_contract():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = pyproject["project"]["version"]
    assert project_version == "0.15.0"
    assert _default_app_version() == project_version
    assert settings.app_version == project_version
    config = (ROOT / "app/core/config.py").read_text(encoding="utf-8")
    assert 'app_version: str = "0.15.0"' not in config


def test_ci_workflow_has_required_quality_and_security_gates():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for required in (
        "Quality Gate",
        "Secret Scan",
        "Container Security Gate",
        "Docker Integration Gate",
        "Multi-Architecture Gate",
        "ruff check",
        "bandit -q -r app -ll",
        "pip-audit . --strict",
        "gitleaks/gitleaks-action@v3",
        "aquasecurity/trivy-action@v0.36.0",
        "--cov-fail-under=25",
        "docker/setup-qemu-action@v4",
        "platforms: linux/amd64,linux/arm64",
    ):
        assert required in text
    assert "permissions:\n  contents: read" in text
    assert '"hotfix/**"' in text
    assert "docker compose down --remove-orphans" not in text


def test_release_workflow_publishes_hardened_ghcr_image():
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert 'tags: ["v*"]' in text
    assert "packages: write" in text
    assert "ghcr.io/${{ github.repository }}" in text
    assert "target: production" in text
    assert "provenance: mode=max" in text
    assert "sbom: true" in text
    assert "severity: CRITICAL" in text
    assert "docker/setup-qemu-action@v4" in text
    assert "platforms: linux/amd64,linux/arm64" in text
    assert "docker/build-push-action@v7" in text
    assert "docker/login-action@v4" in text
    assert "docker/metadata-action@v6" in text
    assert "Verificar manifest multi-platform publicado" in text


def test_supply_chain_tool_versions_are_pinned():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for dependency in (
        '"ruff==0.16.6"',
        '"pytest-cov==7.1.0"',
        '"bandit==1.9.4"',
        '"pip-audit==2.10.1"',
        '"cyclonedx-bom==7.3.1"',
    ):
        assert dependency in pyproject


def test_docker_context_excludes_secrets_and_production_is_non_root():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ".env\n" in dockerignore
    assert ".git\n" in dockerignore
    assert "*.zip" in dockerignore

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "AS production" in dockerfile
    assert "AS development" in dockerfile
    assert "USER app" in dockerfile
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'target: development' in compose
    assert 'RUN_MIGRATIONS: ${RUN_MIGRATIONS:-true}' in compose
    assert 'RUN_BOOTSTRAP: ${RUN_BOOTSTRAP:-true}' in compose

    entrypoint = (ROOT / "scripts/entrypoint.sh").read_text(encoding="utf-8")
    assert '${RUN_MIGRATIONS:-false}' in entrypoint
    assert '${RUN_BOOTSTRAP:-false}' in entrypoint


def test_repository_governance_files_exist():
    dependabot = (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    assert "package-ecosystem: pip" in dependabot
    assert "package-ecosystem: docker" in dependabot
    assert "package-ecosystem: github-actions" in dependabot
    assert "@chykynho" in (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
    assert (ROOT / "SECURITY.md").exists()


def test_setuptools_discovers_only_application_package():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '[build-system]' in pyproject
    assert 'build-backend = "setuptools.build_meta"' in pyproject
    assert 'setuptools>=' in pyproject
    assert 'wheel>=' in pyproject
    dev_block = pyproject.split('[project.optional-dependencies]', 1)[1].split('[tool.setuptools.packages.find]', 1)[0]
    assert 'setuptools>=' in dev_block and 'wheel>=' in dev_block
    assert '[tool.setuptools.packages.find]' in pyproject
    assert 'include = ["app*"]' in pyproject
    for excluded in ("alembic*", "fixtures*", "observability*", "scripts*", "tests*"):
        assert excluded in pyproject


def test_operational_scripts_and_docs_exist():
    for path in (
        "scripts/upgrade_v14.ps1",
        "scripts/test_v14.ps1",
        "scripts/test_v14_supply_chain.py",
        "UPGRADE_v0.14.0.md",
        "V0.14.md",
        "VALIDACAO_v0.14_PTBR.md",
        "HOTFIX_v0.14.1_CI_PACKAGE_DISCOVERY_PTBR.md",
        "UPGRADE_v0.14.1.md",
        "VALIDACAO_v0.14.1_PTBR.md",
        "scripts/upgrade_v15.ps1",
        "scripts/test_v15.ps1",
        "UPGRADE_v0.15.0.md",
        "V0.15.md",
        "VALIDACAO_v0.15_PTBR.md",
    ):
        assert (ROOT / path).exists(), path


def test_build_artifacts_are_ignored_untracked_and_wheel_build_is_isolated():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for token in ("build/", "dist/", "*.egg-info/", "*.whl"):
        assert token in gitignore
    for token in ("build", "dist", "*.egg-info", "*.whl"):
        assert token in dockerignore

    # A imagem/container de desenvolvimento não carrega o binário Git nem o diretório .git.
    # A verificação de arquivos rastreados pertence ao host/GitHub Runner, não ao pytest.
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "git ls-files" in workflow
    assert "Repository hygiene - artefatos nao rastreados" in workflow
    assert "rm -rf build dist *.egg-info" in workflow

    upgrade = (ROOT / "scripts/upgrade_v14.ps1").read_text(encoding="utf-8")
    assert "/tmp/v0143-src" in upgrade
    assert "cd /tmp/v0143-src" in upgrade

    # O smoke de resiliencia e legado de v0.13, mas deve validar a versao runtime atual.
    smoke = (ROOT / "scripts/test_v13_resilience.py").read_text(encoding="utf-8")
    assert "expected_version = settings.app_version" in smoke
    assert 'live.json()["version"] == expected_version' in smoke
    assert 'root.json()["version"] == expected_version' in smoke
    assert '== "0.13.0"' not in smoke
