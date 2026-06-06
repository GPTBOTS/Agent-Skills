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
