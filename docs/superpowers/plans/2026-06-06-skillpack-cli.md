# skillpack CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `skillpack`, a Python CLI that validates, packages, and publishes the single GPTBots Agent Skill, and tidy the skill into a publishable `GPTBOTS/Agent-Skills` repo.

**Architecture:** A small package `skillpack/` (loaded as `pip install -e .`) with focused modules — `source` (load + parse SKILL.md), `validator` + `limits` (lint), `archive` + `packager` (deterministic `.skill` / `.api.zip`), `publisher` (git add/commit/push with confirm), `cli` (argparse). The skill itself lives in a sibling folder `gptbots-agent-skill/` so the `skills` CLI never ships the tooling.

**Tech Stack:** Python 3.11+ (uses stdlib `tomllib`, `zipfile`, `subprocess`), PyYAML for frontmatter, pytest for tests.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | package metadata, `skillpack` entry point, deps |
| `skillpack.toml` | default config (skill path, limits, git, package, exclude) |
| `skillpack/problem.py` | `Problem` dataclass (shared by validator + limits) |
| `skillpack/config.py` | `Config`/`Limits`/`PackageConfig`/`GitConfig` + `load_config` |
| `skillpack/source.py` | `SkillSource`, `parse_frontmatter`, `load_source` |
| `skillpack/limits.py` | `check_limits` (size/count → Problems) |
| `skillpack/validator.py` | `validate` (structure/frontmatter/symlink/junk + limits), `has_blocking` |
| `skillpack/archive.py` | `write_zip` (deterministic) |
| `skillpack/packager.py` | `package` (`.skill` nested + `.api.zip` top-level) |
| `skillpack/publisher.py` | `git_add`/`git_commit`/`git_push`/`publish` |
| `skillpack/cli.py` | argparse subcommands `validate`/`package`/`publish`, `main` |
| `tests/conftest.py` | `make_skill` fixture |
| `tests/test_*.py` | one per module |
| `gptbots-agent-skill/` | the skill (renamed from `GPTBots-Agent-Skill/`) |

Tasks are ordered so each builds only on earlier ones. Run all commands from the repo root `/Users/liujishi/Documents/GPTBots-Skill`.

---

## Task 0: Project scaffolding + dev env

**Files:**
- Create: `pyproject.toml`, `skillpack.toml`, `skillpack/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "skillpack"
version = "0.1.0"
description = "Validate, package, and publish the GPTBots Agent Skill"
requires-python = ">=3.11"
dependencies = ["PyYAML>=6.0"]

[project.scripts]
skillpack = "skillpack.cli:main"

[project.optional-dependencies]
dev = ["pytest>=7"]

[tool.setuptools.packages.find]
include = ["skillpack*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write `skillpack.toml`**

```toml
[skill]
path = "gptbots-agent-skill"

[git]
remote = "origin"
branch = "main"

[limits]
max_total_size_mb      = 30
max_file_count         = 1000
max_file_size_mb       = 10
max_skill_md_bytes     = 65536
max_name_length        = 64
max_description_length = 1024

[package]
emit_skill   = true
emit_api_zip = true

[exclude]
patterns = [".git/", ".DS_Store", "__pycache__/", "*.pyc", "metadata.json"]
```

- [ ] **Step 3: Create empty package marker**

`skillpack/__init__.py`:

```python
"""skillpack: validate, package, and publish the GPTBots Agent Skill."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Append to `.gitignore`**

Add these lines to the existing `.gitignore`:

```
.pytest_cache/
dist/
```

(`dist/` and `__pycache__/` may already be present — duplicates are harmless.)

- [ ] **Step 5: Create venv and install**

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Expected: installs skillpack (editable), PyYAML, pytest. No errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml skillpack.toml skillpack/__init__.py .gitignore
git commit -m "chore: scaffold skillpack package + config"
```

---

## Task 1: Rename skill folder + frontmatter name

**Files:**
- Rename: `GPTBots-Agent-Skill/` → `gptbots-agent-skill/`
- Modify: `gptbots-agent-skill/SKILL.md:2`

- [ ] **Step 1: Rename the folder**

```bash
mv GPTBots-Agent-Skill gptbots-agent-skill
```

- [ ] **Step 2: Update the frontmatter name**

In `gptbots-agent-skill/SKILL.md`, change line 2 from:

```
name: gptbots-skill
```

to:

```
name: gptbots-agent-skill
```

- [ ] **Step 3: Verify no stragglers**

Run: `grep -rn "gptbots-skill\b" gptbots-agent-skill || echo "clean"`
Expected: only matches for `gptbots-agent-skill` (the new name) or `clean`. There must be no bare `gptbots-skill` left in `SKILL.md` frontmatter.

- [ ] **Step 4: Commit**

```bash
git add gptbots-agent-skill
git commit -m "skill: rename folder + name to gptbots-agent-skill"
```

---

## Task 2: `problem.py` + `config.py`

**Files:**
- Create: `skillpack/problem.py`, `skillpack/config.py`, `tests/test_config.py`, `tests/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/__init__.py`: (empty file)

`tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL (ModuleNotFoundError: skillpack.config).

- [ ] **Step 3: Write `skillpack/problem.py`**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    level: str  # "error" | "warning"
    code: str
    message: str
    hint: str = ""
```

- [ ] **Step 4: Write `skillpack/config.py`**

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class Limits:
    max_total_size_mb: int = 30
    max_file_count: int = 1000
    max_file_size_mb: int = 10
    max_skill_md_bytes: int = 65536
    max_name_length: int = 64
    max_description_length: int = 1024


@dataclass(frozen=True)
class PackageConfig:
    emit_skill: bool = True
    emit_api_zip: bool = True


@dataclass(frozen=True)
class GitConfig:
    remote: str = "origin"
    branch: str = "main"


@dataclass(frozen=True)
class Config:
    skill_path: str = "gptbots-agent-skill"
    limits: Limits = field(default_factory=Limits)
    package: PackageConfig = field(default_factory=PackageConfig)
    git: GitConfig = field(default_factory=GitConfig)
    exclude_patterns: tuple[str, ...] = (
        ".git/",
        ".DS_Store",
        "__pycache__/",
        "*.pyc",
        "metadata.json",
    )


def _filtered(cls, data: dict) -> dict:
    valid = {f for f in cls.__dataclass_fields__}
    return {k: v for k, v in data.items() if k in valid}


def load_config(config_path: Path | None = None) -> Config:
    path = config_path if config_path is not None else Path("skillpack.toml")
    if not path.exists():
        return Config()
    raw = tomllib.loads(path.read_text())
    cfg = Config()
    skill = raw.get("skill", {})
    limits = Limits(**{**Limits().__dict__, **_filtered(Limits, raw.get("limits", {}))})
    package = PackageConfig(**{**PackageConfig().__dict__, **_filtered(PackageConfig, raw.get("package", {}))})
    git = GitConfig(**{**GitConfig().__dict__, **_filtered(GitConfig, raw.get("git", {}))})
    exclude = raw.get("exclude", {}).get("patterns")
    return replace(
        cfg,
        skill_path=skill.get("path", cfg.skill_path),
        limits=limits,
        package=package,
        git=git,
        exclude_patterns=tuple(exclude) if exclude is not None else cfg.exclude_patterns,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add skillpack/problem.py skillpack/config.py tests/test_config.py tests/__init__.py
git commit -m "feat(skillpack): config + problem types"
```

---

## Task 3: `source.py` (frontmatter + load)

**Files:**
- Create: `skillpack/source.py`, `tests/conftest.py`, `tests/test_source.py`

- [ ] **Step 1: Write the shared fixture `tests/conftest.py`**

```python
from pathlib import Path

import pytest


@pytest.fixture
def make_skill(tmp_path):
    def _make(
        name="gptbots-agent-skill",
        description="A test skill used for validating behavior in tests.",
        license="MIT",
        body="# Skill\n\nDo the thing.",
        extra=None,
        frontmatter_extra=None,
        folder=None,
        raw_skill_md=None,
        write_skill_md=True,
    ):
        folder_name = folder or name or "skill"
        d = tmp_path / folder_name
        d.mkdir(parents=True, exist_ok=True)
        if write_skill_md:
            if raw_skill_md is not None:
                (d / "SKILL.md").write_text(raw_skill_md)
            else:
                lines = []
                if name is not None:
                    lines.append(f"name: {name}")
                if description is not None:
                    lines.append(f"description: {description}")
                if license is not None:
                    lines.append(f"license: {license}")
                for k, v in (frontmatter_extra or {}).items():
                    lines.append(f"{k}: {v}")
                fm = "\n".join(lines)
                (d / "SKILL.md").write_text(f"---\n{fm}\n---\n{body}\n")
        for rel, content in (extra or {}).items():
            fp = d / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                fp.write_bytes(content)
            else:
                fp.write_text(content)
        return d

    return _make
```

- [ ] **Step 2: Write the failing test `tests/test_source.py`**

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_source.py -v`
Expected: FAIL (ModuleNotFoundError: skillpack.source).

- [ ] **Step 4: Write `skillpack/source.py`**

```python
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


@dataclass(frozen=True)
class FileInfo:
    relpath: str
    size: int


@dataclass(frozen=True)
class SkillSource:
    path: Path
    folder_name: str
    is_dir: bool
    has_skill_md: bool
    skill_md_text: str | None
    skill_md_bytes: int
    frontmatter: dict | None
    frontmatter_error: str | None
    body: str | None
    files: tuple[FileInfo, ...]
    symlinks: tuple[str, ...]
    total_size: int


def parse_frontmatter(text: str) -> tuple[dict | None, str, str | None]:
    m = _FM_RE.match(text)
    if not m:
        return None, text, "SKILL.md is missing YAML frontmatter (must start with --- ... ---)"
    raw, body = m.group(1), m.group(2)
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        return None, body, f"invalid YAML frontmatter: {e}"
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, body, "frontmatter is not a YAML mapping"
    return data, body, None


def load_source(path: str | Path) -> SkillSource:
    path = Path(path)
    folder_name = path.name
    if not path.is_dir():
        return SkillSource(path, folder_name, False, False, None, 0, None, None, None, (), (), 0)

    skill_md = path / "SKILL.md"
    has = skill_md.is_file()
    text = None
    fm = None
    fm_err = None
    body = None
    md_bytes = 0
    if has:
        data = skill_md.read_bytes()
        md_bytes = len(data)
        text = data.decode("utf-8", errors="replace")
        fm, body, fm_err = parse_frontmatter(text)

    files: list[FileInfo] = []
    symlinks: list[str] = []
    total = 0
    for root, dirs, fnames in os.walk(path, followlinks=False):
        rootp = Path(root)
        for d in list(dirs):
            dp = rootp / d
            if dp.is_symlink():
                symlinks.append(dp.relative_to(path).as_posix())
                dirs.remove(d)
        for f in fnames:
            fp = rootp / f
            rel = fp.relative_to(path).as_posix()
            if fp.is_symlink():
                symlinks.append(rel)
                continue
            size = fp.stat().st_size
            files.append(FileInfo(rel, size))
            total += size

    files.sort(key=lambda fi: fi.relpath)
    symlinks.sort()
    return SkillSource(
        path, folder_name, True, has, text, md_bytes, fm, fm_err, body,
        tuple(files), tuple(symlinks), total,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_source.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add skillpack/source.py tests/conftest.py tests/test_source.py
git commit -m "feat(skillpack): source loading + frontmatter parsing"
```

---

## Task 4: `limits.py`

**Files:**
- Create: `skillpack/limits.py`, `tests/test_limits.py`

- [ ] **Step 1: Write the failing test `tests/test_limits.py`**

```python
from skillpack.config import Limits
from skillpack.limits import check_limits
from skillpack.source import load_source


def codes(problems):
    return [p.code for p in problems]


def test_within_limits_no_problems(make_skill):
    src = load_source(make_skill())
    assert check_limits(src, Limits()) == []


def test_total_size_exceeded(make_skill):
    src = load_source(make_skill(extra={"big.bin": b"x" * 2048}))
    limits = Limits(max_total_size_mb=0)  # 0 MB -> any content exceeds
    problems = check_limits(src, limits)
    assert "E007" in codes(problems)
    assert any(p.level == "error" for p in problems if p.code == "E007")


def test_file_count_warns(make_skill):
    src = load_source(make_skill(extra={f"f{i}.txt": "x" for i in range(3)}))
    problems = check_limits(src, Limits(max_file_count=2))
    assert "W005" in codes(problems)


def test_skill_md_too_big_warns(make_skill):
    src = load_source(make_skill(body="x" * 100))
    problems = check_limits(src, Limits(max_skill_md_bytes=10))
    assert "W005" in codes(problems)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_limits.py -v`
Expected: FAIL (ModuleNotFoundError: skillpack.limits).

- [ ] **Step 3: Write `skillpack/limits.py`**

```python
from __future__ import annotations

from .config import Limits
from .problem import Problem
from .source import SkillSource


def check_limits(source: SkillSource, limits: Limits) -> list[Problem]:
    problems: list[Problem] = []

    max_total = limits.max_total_size_mb * 1024 * 1024
    if source.total_size > max_total:
        problems.append(Problem(
            "error", "E007",
            f"total size {source.total_size} bytes exceeds limit ({limits.max_total_size_mb} MB)",
            "Remove large files or raise max_total_size_mb",
        ))

    if len(source.files) > limits.max_file_count:
        problems.append(Problem(
            "warning", "W005",
            f"file count {len(source.files)} exceeds {limits.max_file_count}",
            "Reduce file count or raise max_file_count",
        ))

    max_file = limits.max_file_size_mb * 1024 * 1024
    for fi in source.files:
        if fi.size > max_file:
            problems.append(Problem(
                "warning", "W005",
                f"file {fi.relpath} is {fi.size} bytes, exceeds {limits.max_file_size_mb} MB",
                "Reduce file size or raise max_file_size_mb",
            ))

    if source.skill_md_bytes > limits.max_skill_md_bytes:
        problems.append(Problem(
            "warning", "W005",
            f"SKILL.md is {source.skill_md_bytes} bytes, exceeds {limits.max_skill_md_bytes}",
            "Trim SKILL.md or raise max_skill_md_bytes",
        ))

    return problems
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_limits.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add skillpack/limits.py tests/test_limits.py
git commit -m "feat(skillpack): size/count limit checks"
```

---

## Task 5: `validator.py`

**Files:**
- Create: `skillpack/validator.py`, `tests/test_validator.py`

- [ ] **Step 1: Write the failing test `tests/test_validator.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_validator.py -v`
Expected: FAIL (ModuleNotFoundError: skillpack.validator).

- [ ] **Step 3: Write `skillpack/validator.py`**

```python
from __future__ import annotations

import fnmatch
import re

from .config import Config
from .limits import check_limits
from .problem import Problem
from .source import SkillSource

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
JUNK_NAMES = {".DS_Store", "Thumbs.db"}
JUNK_GLOBS = ("*.swp", "*~", "*.tmp")


def _is_junk(relpath: str) -> bool:
    base = relpath.rsplit("/", 1)[-1]
    if base in JUNK_NAMES:
        return True
    return any(fnmatch.fnmatch(base, g) for g in JUNK_GLOBS)


def validate(source: SkillSource, config: Config) -> list[Problem]:
    problems: list[Problem] = []

    if not source.is_dir:
        problems.append(Problem("error", "E001", f"path is not a directory: {source.path}",
                                "Pass the skill folder path"))
        return problems

    if not source.has_skill_md:
        problems.append(Problem("error", "E002", "SKILL.md not found in skill folder root",
                                "Add a SKILL.md with name + description"))

    if source.has_skill_md:
        if source.frontmatter is None:
            problems.append(Problem("error", "E003", f"invalid frontmatter: {source.frontmatter_error}",
                                    "Wrap metadata in --- ... --- as valid YAML"))
        else:
            fm = source.frontmatter
            name = fm.get("name")
            if not isinstance(name, str) or not name.strip():
                problems.append(Problem("error", "E004",
                                        "frontmatter 'name' is required and must be a non-empty string",
                                        "Add name: your-skill-name"))
            elif not NAME_RE.match(name):
                problems.append(Problem("error", "E004",
                                        f"name '{name}' must match ^[a-z0-9]+(-[a-z0-9]+)*$",
                                        "Use lowercase letters, digits, hyphens"))
            elif len(name) > config.limits.max_name_length:
                problems.append(Problem("error", "E004",
                                        f"name '{name}' exceeds {config.limits.max_name_length} chars",
                                        "Shorten the name"))
            elif source.folder_name != name:
                problems.append(Problem("warning", "W001",
                                        f"folder name '{source.folder_name}' differs from frontmatter name '{name}'",
                                        "Rename the folder to match name (skills CLI installs under the frontmatter name)"))

            desc = fm.get("description")
            if not isinstance(desc, str) or not desc.strip():
                problems.append(Problem("error", "E005",
                                        "frontmatter 'description' is required and must be a non-empty string",
                                        "Describe what the skill does and when to use it"))
            elif len(desc) > config.limits.max_description_length:
                problems.append(Problem("error", "E005",
                                        f"description exceeds {config.limits.max_description_length} chars ({len(desc)})",
                                        "Shorten the description"))

            if "license" not in fm:
                problems.append(Problem("warning", "W002", "frontmatter has no 'license'",
                                        "Add license: MIT (or your license)"))

        if not (source.body and source.body.strip()):
            problems.append(Problem("warning", "W003", "SKILL.md body is empty (only frontmatter)",
                                    "Add the skill instructions after the frontmatter"))

    if source.symlinks:
        problems.append(Problem("error", "E006",
                                f"symlinks are not allowed: {', '.join(source.symlinks)}",
                                "Replace symlinks with real files"))

    junk = [fi.relpath for fi in source.files if _is_junk(fi.relpath)]
    if junk:
        problems.append(Problem("warning", "W004",
                                f"junk files will be shipped to users: {', '.join(junk)}",
                                "Delete them; skills CLI only auto-excludes .git/__pycache__/__pypackages__/metadata.json"))

    problems.extend(check_limits(source, config.limits))
    return problems


def has_blocking(problems: list[Problem], strict: bool = False) -> bool:
    if any(p.level == "error" for p in problems):
        return True
    return strict and any(p.level == "warning" for p in problems)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_validator.py -v`
Expected: PASS (11 passed).

- [ ] **Step 5: Commit**

```bash
git add skillpack/validator.py tests/test_validator.py
git commit -m "feat(skillpack): validator (structure/frontmatter/symlink/junk)"
```

---

## Task 6: `archive.py`

**Files:**
- Create: `skillpack/archive.py`, `tests/test_archive.py`

- [ ] **Step 1: Write the failing test `tests/test_archive.py`**

```python
import zipfile

from skillpack.archive import write_zip


def test_write_zip_contents_and_determinism(tmp_path):
    entries = [("b.txt", b"two"), ("a/x.txt", b"one")]
    out1 = tmp_path / "one.zip"
    out2 = tmp_path / "two.zip"
    write_zip(entries, out1)
    write_zip(list(reversed(entries)), out2)  # different input order

    with zipfile.ZipFile(out1) as z:
        names = z.namelist()
        assert names == ["a/x.txt", "b.txt"]  # sorted
        assert z.read("a/x.txt") == b"one"

    # byte-identical regardless of input order
    assert out1.read_bytes() == out2.read_bytes()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_archive.py -v`
Expected: FAIL (ModuleNotFoundError: skillpack.archive).

- [ ] **Step 3: Write `skillpack/archive.py`**

```python
from __future__ import annotations

import zipfile
from pathlib import Path

_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def write_zip(entries: list[tuple[str, bytes]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    items = sorted(entries, key=lambda e: e[0])
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in items:
            zi = zipfile.ZipInfo(arcname, date_time=_FIXED_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_archive.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add skillpack/archive.py tests/test_archive.py
git commit -m "feat(skillpack): deterministic zip writer"
```

---

## Task 7: `packager.py`

**Files:**
- Create: `skillpack/packager.py`, `tests/test_packager.py`

- [ ] **Step 1: Write the failing test `tests/test_packager.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_packager.py -v`
Expected: FAIL (ModuleNotFoundError: skillpack.packager).

- [ ] **Step 3: Write `skillpack/packager.py`**

```python
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from .archive import write_zip
from .config import Config
from .source import SkillSource


def _excluded(relpath: str, patterns) -> bool:
    parts = [p for p in relpath.split("/") if p]
    base = parts[-1] if parts else ""
    for pat in patterns:
        if pat.endswith("/"):
            if pat[:-1] in parts:
                return True
        elif "*" in pat or "?" in pat:
            if fnmatch.fnmatch(base, pat):
                return True
        elif base == pat:
            return True
    return False


def collect_entries(skill_dir: Path, prefix: str, patterns) -> list[tuple[str, bytes]]:
    entries: list[tuple[str, bytes]] = []
    for root, dirs, fnames in os.walk(skill_dir, followlinks=False):
        rootp = Path(root)
        for d in list(dirs):
            rel = (rootp / d).relative_to(skill_dir).as_posix()
            if _excluded(rel, patterns):
                dirs.remove(d)
        for f in fnames:
            fp = rootp / f
            rel = fp.relative_to(skill_dir).as_posix()
            if _excluded(rel, patterns):
                continue
            entries.append((prefix + rel, fp.read_bytes()))
    return entries


def _check_size(entries, max_total_mb: int) -> None:
    total = sum(len(d) for _, d in entries)
    max_total = max_total_mb * 1024 * 1024
    if total > max_total:
        raise ValueError(f"packaged content {total} bytes exceeds {max_total_mb} MB")


def package(source: SkillSource, config: Config, out_dir: Path) -> list[Path]:
    name = source.frontmatter["name"]
    outputs: list[Path] = []

    if config.package.emit_skill:
        entries = collect_entries(source.path, f"{name}/", config.exclude_patterns)
        _check_size(entries, config.limits.max_total_size_mb)
        out = out_dir / f"{name}.skill"
        write_zip(entries, out)
        outputs.append(out)

    if config.package.emit_api_zip:
        entries = collect_entries(source.path, "", config.exclude_patterns)
        _check_size(entries, config.limits.max_total_size_mb)
        out = out_dir / f"{name}.api.zip"
        write_zip(entries, out)
        outputs.append(out)

    return outputs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_packager.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add skillpack/packager.py tests/test_packager.py
git commit -m "feat(skillpack): packager (.skill nested + .api.zip top-level)"
```

---

## Task 8: `publisher.py`

**Files:**
- Create: `skillpack/publisher.py`, `tests/test_publisher.py`

- [ ] **Step 1: Write the failing test `tests/test_publisher.py`**

```python
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
    # the bare remote now has 2 commits
    log = subprocess.run(["git", "log", "--oneline"], cwd=str(bare), capture_output=True, text=True)
    assert "skill: add" in log.stdout


def test_publish_declined_does_not_push(repo_with_remote):
    work, bare = repo_with_remote
    skill = work / "gptbots-agent-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: gptbots-agent-skill\ndescription: d\n---\nbody\n")
    result = publish(work, "gptbots-agent-skill", "skill: add", "origin", "main",
                     assume_yes=False, confirm=lambda: False, printer=lambda *a, **k: None)
    assert result["pushed"] is False
    log = subprocess.run(["git", "log", "--oneline"], cwd=str(bare), capture_output=True, text=True)
    assert "skill: add" not in log.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_publisher.py -v`
Expected: FAIL (ModuleNotFoundError: skillpack.publisher).

- [ ] **Step 3: Write `skillpack/publisher.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_publisher.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add skillpack/publisher.py tests/test_publisher.py
git commit -m "feat(skillpack): publisher (git add/commit/push with confirm)"
```

---

## Task 9: `cli.py`

**Files:**
- Create: `skillpack/cli.py`, `tests/test_cli.py`

- [ ] **Step 1: Write the failing test `tests/test_cli.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL (ModuleNotFoundError: skillpack.cli).

- [ ] **Step 3: Write `skillpack/cli.py`**

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import publisher
from .config import load_config
from .packager import package
from .source import load_source
from .validator import has_blocking, validate


def _render(problems) -> str:
    lines = []
    for p in problems:
        prefix = "ERROR" if p.level == "error" else "WARN"
        line = f"{prefix}: [{p.code}] {p.message}"
        if p.hint:
            line += f"\n        hint: {p.hint}"
        lines.append(line)
    return "\n".join(lines)


def _load(args):
    config = load_config(Path(args.config) if args.config else None)
    path = args.path or config.skill_path
    return config, path, load_source(path)


def _print_summary(problems) -> None:
    if problems:
        print(_render(problems))
    errs = sum(1 for p in problems if p.level == "error")
    warns = sum(1 for p in problems if p.level == "warning")
    print(f"\n{errs} error(s), {warns} warning(s)")


def cmd_validate(args) -> int:
    config, _path, source = _load(args)
    problems = validate(source, config)
    _print_summary(problems)
    return 1 if has_blocking(problems, args.strict) else 0


def cmd_package(args) -> int:
    config, _path, source = _load(args)
    problems = validate(source, config)
    _print_summary(problems)
    if has_blocking(problems, strict=False):
        print("\nValidation failed; not packaging.")
        return 1
    outputs = package(source, config, Path(args.out))
    print("\nWrote:")
    for o in outputs:
        print(f"  {o}")
    return 0


def cmd_publish(args) -> int:
    config, path, source = _load(args)
    problems = validate(source, config)
    _print_summary(problems)
    if has_blocking(problems, strict=False):
        print("\nValidation failed; not publishing.")
        return 1
    name = source.frontmatter["name"]
    message = args.message or f"skill: update {name}"
    result = publisher.publish(Path("."), path, message, config.git.remote, config.git.branch,
                               assume_yes=args.yes)
    print(result)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="skillpack")
    parser.add_argument("--config")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("validate")
    pv.add_argument("path", nargs="?")
    pv.add_argument("--strict", action="store_true")
    pv.set_defaults(func=cmd_validate)

    pp = sub.add_parser("package")
    pp.add_argument("path", nargs="?")
    pp.add_argument("--out", default="dist")
    pp.set_defaults(func=cmd_package)

    pu = sub.add_parser("publish")
    pu.add_argument("path", nargs="?")
    pu.add_argument("--message")
    pu.add_argument("--yes", action="store_true")
    pu.set_defaults(func=cmd_publish)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: all tests pass (about 32).

- [ ] **Step 6: Commit**

```bash
git add skillpack/cli.py tests/test_cli.py
git commit -m "feat(skillpack): CLI (validate/package/publish)"
```

---

## Task 10: Content fix — integrate the FlowAgent generation rules

**Files:**
- Modify: `gptbots-agent-skill/references/flowagent-components.md` (append a section)
- Modify: `gptbots-agent-skill/references/create-gptbots-flowagent.md:16` (add a bullet)
- Delete: `bot-flow-generation-spec.md`

- [ ] **Step 1: Append the must-checks section to `flowagent-components.md`**

Append this to the END of `gptbots-agent-skill/references/flowagent-components.md`:

```markdown

---

# Generation must-checks (Branch rules / Human config / branchId)

These come from the canvas/import contract; the backend cannot backfill them, so the generator MUST produce them directly.

1. **Branch (Classifier) rules must be non-empty.** Each classifier category = one `nextComponents` entry whose `condition` (the branch-rule text) MUST be non-empty — the frontend rejects an empty rule with "Cannot be empty" and the node becomes unusable. Write the matching rule text for every category (do not emit a `name` with `condition: null`). The same applies to any decision field on `Condition` / `Regular` nodes — never leave it empty.

2. **`branchId` must be a stable, unique id reused in both places.** For each classifier category the `sourceHandle` is `right{id}-branch_{branchId}`, and the *same* `branchId` must appear in the component's branch config. Use a stable unique id (the frontend uses a timestamp, e.g. `branch_1780657352928`); the fallback category is always `right{id}-branch_other`. Do NOT invent keys like `branch1` / `product` — a missing `branch_` segment or a semantic name will not resolve to the port (distorted/misrouted line).

3. **Human nodes need a component-level `humanConfig`.** The transfer-to-human form renders from the `humanConfig` on the `Human` component itself, not only the bot-level `humanConfig`. Set `humanConfig` (manufacturer/status per the Human Service section) on the Human component so the node config is not blank. The backend backfills entity→component on import, but the generator should write it directly.
```

- [ ] **Step 2: Add the pointer bullet to `create-gptbots-flowagent.md`**

In `gptbots-agent-skill/references/create-gptbots-flowagent.md`, after line 16 (the `Use If/Else (free)...` bullet at the end of step 2), add:

```markdown
- **Generation must-checks** (see `./flowagent-components.md` → *Generation must-checks*): classifier branch `condition` non-empty, stable unique `branchId`, Human component-level `humanConfig`.
```

- [ ] **Step 3: Delete the now-redundant standalone spec**

```bash
rm bot-flow-generation-spec.md
```

- [ ] **Step 4: Verify integration**

Run: `grep -n "Generation must-checks" gptbots-agent-skill/references/flowagent-components.md gptbots-agent-skill/references/create-gptbots-flowagent.md`
Expected: a match in both files.

Run: `test ! -f bot-flow-generation-spec.md && echo "deleted"`
Expected: `deleted`.

- [ ] **Step 5: Commit**

```bash
git add gptbots-agent-skill/references/flowagent-components.md gptbots-agent-skill/references/create-gptbots-flowagent.md
git rm --cached bot-flow-generation-spec.md 2>/dev/null; true
git commit -m "skill: integrate FlowAgent generation must-checks; drop standalone spec"
```

(Note: `bot-flow-generation-spec.md` was never committed, so `git rm --cached` may report nothing — that is fine; the `rm` in Step 3 removed it from disk.)

---

## Task 11: README + LICENSE

**Files:**
- Create: `README.md`, `LICENSE`

- [ ] **Step 1: Write `LICENSE` (MIT)**

```
MIT License

Copyright (c) 2026 GPTBots

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Write `README.md`**

```markdown
# GPTBots Agent Skill

The GPTBots Agent Skill helps you create and optimize GPTBots Agents and Workflows, and drive
published ones via the public API. This repo holds the skill (`gptbots-agent-skill/`) plus
`skillpack`, a small tool to validate, package, and publish it.

## Install the skill

With the [`skills`](https://github.com/vercel-labs/skills) CLI (installs into Claude Code, Codex,
Cursor, Copilot, and other agents automatically):

```bash
npx skills add https://github.com/GPTBOTS/Agent-Skills/tree/main/gptbots-agent-skill
# or
npx skills add GPTBOTS/Agent-Skills --skill gptbots-agent-skill
```

### Anthropic-only channels

- **Claude app / Cowork** — share `gptbots-agent-skill.skill` (built by `skillpack package`); it shows
  a one-click "Save skill" button.
- **claude.ai web** — Settings → Capabilities → Skills → upload the same file (rename `.skill` to `.zip`
  if the form requires it).
- **Anthropic Skills API** — upload `gptbots-agent-skill.api.zip` (SKILL.md at the archive root).

## Maintain the skill (skillpack)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

.venv/bin/skillpack validate            # lint the skill before publishing
.venv/bin/skillpack package             # write dist/*.skill and dist/*.api.zip
.venv/bin/skillpack publish             # validate, commit, then push (asks before pushing)
```

`skillpack` defaults to the skill at `gptbots-agent-skill/` (configurable in `skillpack.toml`).

## License

MIT — see [LICENSE](LICENSE).
```

- [ ] **Step 3: Commit**

```bash
git add README.md LICENSE
git commit -m "docs: repo README + MIT license"
```

---

## Task 12: Final integration check

**Files:** none (verification only)

- [ ] **Step 1: Full test suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 2: Validate the real skill**

Run: `.venv/bin/skillpack validate`
Expected: `0 error(s)` (warnings, if any, are acceptable). If there are errors, fix the skill per the messages and re-run.

- [ ] **Step 3: Package the real skill and verify artifacts**

Run:
```bash
.venv/bin/skillpack package
unzip -l dist/gptbots-agent-skill.skill | grep "gptbots-agent-skill/SKILL.md"
unzip -l dist/gptbots-agent-skill.api.zip | grep -E "^.* SKILL.md$"
```
Expected: the `.skill` lists `gptbots-agent-skill/SKILL.md` (nested); the `.api.zip` lists `SKILL.md` at the root.

- [ ] **Step 4: Commit any skill fixes**

If Step 2 required edits to the skill:
```bash
git add gptbots-agent-skill
git commit -m "skill: fix issues found by skillpack validate"
```

- [ ] **Step 5: Publish (requires user authorization)**

Do NOT push automatically. When the user authorizes it:
```bash
.venv/bin/skillpack publish
# answer 'y' at the push confirmation
```
This validates, commits, and pushes `gptbots-agent-skill/` to `GPTBOTS/Agent-Skills`. After it lands on GitHub, the install commands above work and skills.sh indexes it on first install.

---

## Self-Review notes

- **Spec coverage:** §3 naming → Task 1; §5.1 validate (E001–E007/W001–W005) → Tasks 4–5; §5.2 package (.skill + .api.zip) → Tasks 6–7; §5.3 publish → Task 8; §5.4 config → Task 2; §5.5 modules → Tasks 2–9; §6 content fix → Task 10; §7 README → Task 11; §8 tests → every task; §9 order → task order; scaffolding → Task 0.
- **Type consistency:** `Problem(level, code, message, hint)`, `SkillSource` fields, `Config`/`Limits` fields, and `package(source, config, out_dir)` / `validate(source, config)` / `has_blocking(problems, strict)` / `publish(repo, skill_path, message, remote, branch, ...)` signatures are used identically across tasks.
- **Limits split:** `limits.py` owns size/count Problems (E007/W005); `validator.py` calls it and owns structural/frontmatter/symlink/junk Problems. `Problem` lives in `problem.py` to avoid an import cycle (minor addition beyond the spec's module list, noted here).
```
