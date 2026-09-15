from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gitattributes_forces_shell_scripts_to_lf() -> None:
    gitattributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in gitattributes


def test_shell_scripts_do_not_contain_crlf() -> None:
    scripts = sorted((ROOT / "scripts").rglob("*.sh"))
    assert scripts, "Nenhum script .sh encontrado para validar"

    offenders = [
        str(path.relative_to(ROOT))
        for path in scripts
        if b"\r\n" in path.read_bytes()
    ]
    assert not offenders, f"Scripts .sh com CRLF: {offenders}"


def test_dockerfile_has_defensive_shell_eol_normalization() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "find /app/scripts -type f -name \"*.sh\"" in dockerfile
    assert "sed -i 's/\\r$//'" in dockerfile
