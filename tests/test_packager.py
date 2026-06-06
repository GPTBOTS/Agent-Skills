import zipfile

from skillpack.config import Config
from skillpack.packager import package, _excluded
from skillpack.source import load_source


def test_excluded_matches():
    pats = (".git/", ".DS_Store", "__pycache__/", "*.pyc", "metadata.json")
    assert _excluded(".git", pats) is True
    assert _excluded("references/__pycache__", pats) is True
    assert _excluded("a/b.pyc", pats) is True
    assert _excluded(".DS_Store", pats) is True
    assert _excluded("metadata.json", pats) is True
    assert _excluded("references/a.md", pats) is False


def test_package_emits_both_layouts(make_skill, tmp_path):
    d = make_skill(name="gptbots-agent-skill", extra={"references/a.md": "hello", ".DS_Store": "junk"})
    src = load_source(d)
    out = tmp_path / "dist"
    paths = package(src, Config(), out)

    names = {p.name for p in paths}
    assert names == {"gptbots-agent-skill.skill", "gptbots-agent-skill.api.zip"}

    skill_zip = out / "gptbots-agent-skill.skill"
    api_zip = out / "gptbots-agent-skill.api.zip"

    with zipfile.ZipFile(skill_zip) as z:
        n = z.namelist()
        assert "gptbots-agent-skill/SKILL.md" in n           # nested
        assert "gptbots-agent-skill/references/a.md" in n
        assert all(".DS_Store" not in x for x in n)           # junk excluded

    with zipfile.ZipFile(api_zip) as z:
        n = z.namelist()
        assert "SKILL.md" in n                                # top-level
        assert "references/a.md" in n


def test_package_respects_emit_flags(make_skill, tmp_path):
    from dataclasses import replace
    from skillpack.config import PackageConfig

    src = load_source(make_skill())
    cfg = replace(Config(), package=PackageConfig(emit_skill=True, emit_api_zip=False))
    paths = package(src, cfg, tmp_path / "dist")
    assert [p.name for p in paths] == ["gptbots-agent-skill.skill"]
