from pathlib import Path
from skillpack.config import load_config, Config, Limits


def test_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert isinstance(cfg, Config)
    assert cfg.skill_path == "gptbots-agent-skill"
    assert cfg.limits.max_total_size_mb == 30
    assert cfg.limits.max_description_length == 1024
    assert cfg.git.remote == "origin"
    assert cfg.package.emit_skill is True
    assert ".DS_Store" in cfg.exclude_patterns


def test_overrides_from_toml(tmp_path):
    p = tmp_path / "skillpack.toml"
    p.write_text(
        "[skill]\npath = 'foo'\n"
        "[limits]\nmax_total_size_mb = 5\n"
        "[package]\nemit_api_zip = false\n"
        "[exclude]\npatterns = ['*.log']\n"
    )
    cfg = load_config(p)
    assert cfg.skill_path == "foo"
    assert cfg.limits.max_total_size_mb == 5
    assert cfg.limits.max_name_length == 64  # untouched default
    assert cfg.package.emit_api_zip is False
    assert cfg.exclude_patterns == ("*.log",)
