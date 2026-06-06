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
