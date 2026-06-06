from skillpack.config import Config
from skillpack.source import load_source
from skillpack.validator import validate, has_blocking


def codes(problems):
    return [p.code for p in problems]


def run(path):
    return validate(load_source(path), Config())


def test_valid_skill_clean(make_skill):
    problems = run(make_skill())
    assert problems == [], codes(problems)


def test_not_a_dir(tmp_path):
    problems = run(tmp_path / "missing")
    assert codes(problems) == ["E001"]


def test_missing_skill_md(make_skill):
    problems = run(make_skill(write_skill_md=False))
    assert "E002" in codes(problems)


def test_bad_frontmatter(make_skill):
    problems = run(make_skill(raw_skill_md="no frontmatter here\n"))
    assert "E003" in codes(problems)


def test_bad_name_uppercase(make_skill):
    problems = run(make_skill(name="GPTBots"))
    assert "E004" in codes(problems)


def test_missing_description(make_skill):
    problems = run(make_skill(description=None))
    assert "E005" in codes(problems)


def test_folder_name_mismatch_warns(make_skill):
    # frontmatter name valid, folder differs
    problems = run(make_skill(name="gptbots-agent-skill", folder="some-other-dir"))
    assert "W001" in codes(problems)
    assert all(p.level != "error" for p in problems)


def test_missing_license_warns(make_skill):
    problems = run(make_skill(license=None))
    assert "W002" in codes(problems)


def test_junk_file_warns(make_skill):
    problems = run(make_skill(extra={".DS_Store": "x"}))
    assert "W004" in codes(problems)


def test_symlink_errors(make_skill):
    d = make_skill()
    (d / "link.md").symlink_to(d / "SKILL.md")
    problems = run(d)
    assert "E006" in codes(problems)


def test_has_blocking_strict(make_skill):
    problems = run(make_skill(license=None))  # only W002
    assert has_blocking(problems, strict=False) is False
    assert has_blocking(problems, strict=True) is True
