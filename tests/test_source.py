from skillpack.source import load_source, parse_frontmatter


def test_parse_frontmatter_ok():
    data, body, err = parse_frontmatter("---\nname: x\ndescription: y\n---\n# Hi\n")
    assert err is None
    assert data == {"name": "x", "description": "y"}
    assert body.strip() == "# Hi"


def test_parse_frontmatter_missing_delimiters():
    data, body, err = parse_frontmatter("# no frontmatter\n")
    assert data is None
    assert err is not None


def test_parse_frontmatter_bad_yaml():
    data, body, err = parse_frontmatter("---\nname: : :\n bad\n---\nbody\n")
    assert data is None
    assert "YAML" in err or "yaml" in err


def test_load_source_reads_files(make_skill):
    d = make_skill(extra={"references/a.md": "hello", "scripts/x.py": "print(1)"})
    src = load_source(d)
    assert src.is_dir and src.has_skill_md
    assert src.frontmatter["name"] == "gptbots-agent-skill"
    assert src.folder_name == "gptbots-agent-skill"
    rels = {f.relpath for f in src.files}
    assert {"SKILL.md", "references/a.md", "scripts/x.py"} <= rels
    assert src.total_size > 0


def test_load_source_not_a_dir(tmp_path):
    src = load_source(tmp_path / "missing")
    assert src.is_dir is False
    assert src.has_skill_md is False


def test_load_source_detects_symlink(make_skill, tmp_path):
    d = make_skill()
    (d / "link.md").symlink_to(d / "SKILL.md")
    src = load_source(d)
    assert "link.md" in src.symlinks
