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
