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
    valid = set(cls.__dataclass_fields__)
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
