"""tests/test_install.py - installer + marketplace skill sync tests."""

from pathlib import Path

from nodemonk.install import (
    PLATFORM_ALIASES,
    SKILL_RAW_URL,
    install,
    no_install_howto,
    skill_markdown,
    uninstall,
)


def test_committed_skill_md_matches_generator():
    """skill/SKILL.md is the marketplace artifact agents fetch from raw GitHub.

    It must never drift from install.skill_markdown(); regenerate it with
    `nodemonk install --print > skill/SKILL.md` after changing the template.
    """
    committed = (Path(__file__).parent.parent / "skill" / "SKILL.md").read_text(encoding="utf-8")
    assert committed == skill_markdown()


def test_skill_has_frontmatter_and_bootstrap():
    md = skill_markdown()
    assert md.startswith("---\nname: nodemonk\n")
    assert "uvx --from git+https://github.com/Codingnaveen46/nodemonk" in md
    assert "nodemonk-out/graph.json" in md  # fast-path rule present


def test_antigravity_aliases_to_agents(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    out = install("antigravity")
    assert "unknown platform" not in out
    assert (tmp_path / ".agents" / "skills" / "nodemonk" / "SKILL.md").exists()
    # alias uninstall removes the same location
    out = uninstall("antigravity")
    assert "unknown platform" not in out
    assert not (tmp_path / ".agents" / "skills" / "nodemonk" / "SKILL.md").exists()


def test_no_install_howto_contains_raw_url():
    text = no_install_howto("antigravity")
    assert SKILL_RAW_URL in text
    assert text in no_install_howto() or SKILL_RAW_URL in no_install_howto()


def test_unknown_platform_errors():
    assert "unknown platform" in install("bogus")
    assert "unknown platform" in uninstall("bogus")
    assert PLATFORM_ALIASES["antigravity"] == "agents"
