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
