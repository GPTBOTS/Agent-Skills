from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(args, cwd) -> tuple[int, str, str]:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def git_add(repo, paths, run=run_git) -> None:
    code, _out, err = run(["add", *paths], repo)
    if code != 0:
        raise RuntimeError(f"git add failed: {err.strip()}")


def git_commit(repo, message, run=run_git) -> bool:
    code, _out, _err = run(["diff", "--cached", "--quiet"], repo)
    if code == 0:
        return False  # nothing staged
    code, _out, err = run(["commit", "-m", message], repo)
    if code != 0:
        raise RuntimeError(f"git commit failed: {err.strip()}")
    return True


def git_push(repo, remote, branch, run=run_git) -> None:
    code, _out, err = run(["push", remote, branch], repo)
    if code != 0:
        raise RuntimeError(f"git push failed: {err.strip()}")


def publish(repo, skill_path, message, remote, branch,
            assume_yes=False, confirm=None, run=run_git, printer=print) -> dict:
    repo = Path(repo)
    git_add(repo, [skill_path], run=run)
    committed = git_commit(repo, message, run=run)

    code, out, _err = run(["log", f"{remote}/{branch}..HEAD", "--oneline"], repo)
    pending = out.strip() if code == 0 else "(remote branch unknown; will be created on push)"
    printer("Commits to push:\n" + (pending or "(none new)"))

    if not assume_yes:
        if confirm is None:
            def confirm() -> bool:
                return input(f"Push to {remote}/{branch}? [y/N] ").strip().lower() == "y"
        if not confirm():
            return {"committed": committed, "pushed": False}

    git_push(repo, remote, branch, run=run)
    return {"committed": committed, "pushed": True}
