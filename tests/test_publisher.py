import subprocess
from pathlib import Path

import pytest

from skillpack.publisher import publish, run_git


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def repo_with_remote(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    work = tmp_path / "work"
    work.mkdir()
    _git(["init", "-b", "main"], work)
    _git(["config", "user.email", "t@t.t"], work)
    _git(["config", "user.name", "t"], work)
    _git(["remote", "add", "origin", str(bare)], work)
    # an initial commit + push so origin/main exists
    (work / "seed.txt").write_text("seed")
    _git(["add", "."], work)
    _git(["commit", "-m", "seed"], work)
    _git(["push", "origin", "main"], work)
    return work, bare


def test_publish_with_yes_pushes(repo_with_remote):
    work, bare = repo_with_remote
    skill = work / "gptbots-agent-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: gptbots-agent-skill\ndescription: d\n---\nbody\n")
    result = publish(work, "gptbots-agent-skill", "skill: add", "origin", "main",
                     assume_yes=True, printer=lambda *a, **k: None)
    assert result["committed"] is True
    assert result["pushed"] is True
    # the bare remote now has the new commit
    log = subprocess.run(["git", "--git-dir", str(bare), "log", "--oneline", "main"],
                         capture_output=True, text=True)
    assert "skill: add" in log.stdout


def test_publish_declined_does_not_push(repo_with_remote):
    work, bare = repo_with_remote
    skill = work / "gptbots-agent-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: gptbots-agent-skill\ndescription: d\n---\nbody\n")
    result = publish(work, "gptbots-agent-skill", "skill: add", "origin", "main",
                     assume_yes=False, confirm=lambda: False, printer=lambda *a, **k: None)
    assert result["pushed"] is False
    log = subprocess.run(["git", "--git-dir", str(bare), "log", "--oneline", "main"],
                         capture_output=True, text=True)
    assert "skill: add" not in log.stdout
