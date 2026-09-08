from __future__ import annotations

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8000"


def main() -> int:
    print("=== AI Sales Agent Platform v0.14 - CI/CD Supply Chain Smoke Test ===")

    with httpx.Client(timeout=15.0) as client:
        ready = client.get(f"{BASE_URL}/api/v1/health/ready")
        ready.raise_for_status()
        payload = ready.json()
        assert payload["status"] == "ok"
        assert payload["version"] == "0.14.3"
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    print("\n[2/5] Docker supply-chain hardening...")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ".env\n" in dockerignore and ".git\n" in dockerignore
    assert "build\n" in dockerignore and "*.egg-info\n" in dockerignore
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "build/" in gitignore and "*.egg-info/" in gitignore
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "AS production" in dockerfile and "USER app" in dockerfile
    print("[OK] .env/.git fora do contexto e production non-root")

    print("\n[3/5] GitHub Actions quality/security/CD...")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "pip-audit . --strict" in ci
    assert "Repository hygiene - artefatos nao rastreados" in ci
    assert "git ls-files" in ci
    assert "rm -rf build dist *.egg-info" in ci
    assert "gitleaks/gitleaks-action@v3" in ci
    assert "aquasecurity/trivy-action@v0.36.0" in ci
    assert "ghcr.io/${{ github.repository }}" in release
    assert "provenance: mode=max" in release and "sbom: true" in release
    print("[OK] CI quality/security + CD GHCR/provenance/SBOM")

    print("\n[4/5] Dependabot/CODEOWNERS/Security policy...")
    assert (ROOT / ".github/dependabot.yml").exists()
    assert (ROOT / ".github/CODEOWNERS").exists()
    assert (ROOT / "SECURITY.md").exists()
    print("[OK] governanca de repositorio provisionada")

    print("\n[5/5] Versoes de ferramentas fixadas...")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for token in ("ruff==0.16.6", "bandit==1.9.4", "pip-audit==2.10.1", "cyclonedx-bom==7.3.1"):
        assert token in pyproject
    assert '[build-system]' in pyproject and 'build-backend = "setuptools.build_meta"' in pyproject
    dev_block = pyproject.split('[project.optional-dependencies]', 1)[1].split('[tool.setuptools.packages.find]', 1)[0]
    assert 'setuptools>=' in dev_block and 'wheel>=' in dev_block
    assert '[tool.setuptools.packages.find]' in pyproject and 'include = ["app*"]' in pyproject
    print("[OK] ferramentas de quality/security pinadas + build backend/package discovery explicitos + repo hygiene")

    print("\n=== v0.14 SUPPLY CHAIN CONTRACT VALIDADO ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
