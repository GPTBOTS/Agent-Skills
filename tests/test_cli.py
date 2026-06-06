from skillpack.cli import main


def test_validate_ok_exit_zero(make_skill, capsys, monkeypatch, tmp_path):
    d = make_skill()
    monkeypatch.chdir(tmp_path)  # no skillpack.toml -> defaults
    rc = main(["validate", str(d)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "0 error(s)" in out


def test_validate_bad_exit_one(make_skill, capsys, monkeypatch, tmp_path):
    d = make_skill(name="BadName")
    monkeypatch.chdir(tmp_path)
    rc = main(["validate", str(d)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "E004" in out


def test_validate_strict_promotes_warning(make_skill, monkeypatch, tmp_path):
    d = make_skill(license=None)  # only W002
    monkeypatch.chdir(tmp_path)
    assert main(["validate", str(d)]) == 0
    assert main(["validate", str(d), "--strict"]) == 1


def test_package_writes_files(make_skill, capsys, monkeypatch, tmp_path):
    d = make_skill()
    monkeypatch.chdir(tmp_path)
    rc = main(["package", str(d), "--out", str(tmp_path / "dist")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "gptbots-agent-skill.skill" in out
    assert (tmp_path / "dist" / "gptbots-agent-skill.skill").exists()


def test_package_blocked_by_validation(make_skill, monkeypatch, tmp_path):
    d = make_skill(name="BadName")
    monkeypatch.chdir(tmp_path)
    rc = main(["package", str(d), "--out", str(tmp_path / "dist")])
    assert rc == 1
