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
