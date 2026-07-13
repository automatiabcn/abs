"""014 — Provider configs YAML loader testleri."""

from __future__ import annotations

from pathlib import Path


def _write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_load_all_reads_yaml_files(tmp_path: Path):
    from app.providers.configs import load_all

    _write_yaml(
        tmp_path / "foo.yaml",
        "provider: foo\ndisplay_name: Foo\nmodels:\n  - alias: a\n    id: m1\n",
    )
    _write_yaml(
        tmp_path / "bar.yaml",
        "provider: bar\ndisplay_name: Bar\nmodels:\n  - alias: b\n    id: m2\n",
    )

    out = load_all(tmp_path)
    assert len(out) == 2
    assert "foo" in out and "bar" in out
    assert out["foo"]["display_name"] == "Foo"


def test_get_model_alias(tmp_path: Path):
    from app.providers.configs import get_model_alias, load_all

    _write_yaml(
        tmp_path / "anthropic.yaml",
        "provider: anthropic\nmodels:\n"
        "  - alias: claude-haiku\n    id: claude-haiku-4-5-20251001\n    context: 200000\n"
        "  - alias: claude-sonnet\n    id: claude-sonnet-4-6\n    context: 200000\n",
    )
    load_all(tmp_path)
    haiku = get_model_alias("anthropic", "claude-haiku")
    assert haiku is not None
    assert haiku["id"] == "claude-haiku-4-5-20251001"
    assert haiku["context"] == 200000
    assert get_model_alias("anthropic", "nonexistent") is None
    assert get_model_alias("missing-provider", "x") is None


def test_invalid_yaml_logged_not_raised(tmp_path: Path):
    from app.providers.configs import load_all

    _write_yaml(tmp_path / "good.yaml", "provider: g1\nmodels: []\n")
    _write_yaml(tmp_path / "broken.yaml", ":::\n  invalid: yaml: [::\n")
    out = load_all(tmp_path)
    assert "g1" in out
    # Broken file just skipped, no exception
    assert len(out) == 1


def test_deprecated_models_filter(tmp_path: Path):
    from app.providers.configs import deprecated_models, load_all

    _write_yaml(
        tmp_path / "x.yaml",
        "provider: x\nmodels:\n"
        "  - alias: a\n    id: m1\n    deprecated: false\n"
        "  - alias: b\n    id: m2-old\n    deprecated: true\n"
        "  - alias: c\n    id: m3-old\n    deprecated: true\n",
    )
    load_all(tmp_path)
    deps = deprecated_models("x")
    assert set(deps) == {"m2-old", "m3-old"}


def test_repo_default_dir_loads_six_providers():
    """Sanity: repo'daki gercek 6 yaml yuklensin (anthropic/groq/gemini/cerebras/cohere/cloudflare)."""
    from app.providers.configs import all_providers, load_all

    out = load_all()
    assert set(out.keys()) >= {
        "anthropic",
        "groq",
        "gemini",
        "cerebras",
        "cohere",
        "cloudflare",
    }
    assert "anthropic" in all_providers()
