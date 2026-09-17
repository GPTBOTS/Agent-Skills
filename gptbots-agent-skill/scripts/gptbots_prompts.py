#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Load node prompts from an external file, so long prompt text lives separately
from the build script (no Python/JSON escaping, easy to review and edit, and the
same prompts can be reused or version-controlled on their own).

Why: a real bot's identity prompt + per-node prompts (classifier rules, answer
LLMs, gather SOPs) can run to thousands of characters. Keeping them inline in the
generation script bloats it and mixes content with structure. Store them in a
`prompts.md` instead and have the generator read them by key.

Recommended format — Markdown, one prompt per `## key` section:

    # Prompts for My Bot   (an optional H1 title is ignored)

    ## identity
    You are ...
    (any length, blank lines, lists, code fences — all preserved verbatim)

    ## intent_classifier
    Classify the message into exactly one category ...

    ## answer_deposit
    Answer strictly from the knowledge base ...

Standard layout for every bot — a `prompts/` folder, one `<node name>.md` per
node (the filename stem is the key):

    prompts/
      identity.md
      Intent_Classifier.md
      Answer_Deposit.md
      Gather_Withdraw.md

This scales cleanly and avoids one giant file even for large flows. Each file's
entire content is that node's prompt.

Convention: **make each file's name equal the component's `name`** in
`b.add(type, name, ...)`, so the wiring reads `role(P[name])` / `P.require(name)`
and a missing/renamed prompt fails loudly instead of silently shipping a blank.

Then in the generation script:

    from gptbots_prompts import load_prompt_store
    P = load_prompt_store("prompts/")
    b.add("Branch", "Intent_Classifier",
          messages=[role(P.require("Intent_Classifier")), user_input()])

`load_prompts()` auto-detects the source: a directory → one file per node (the
standard); a `.json` file → a flat {key: text} object; a `.md` file → Markdown
`## key` sections. The single-file forms are kept for compatibility, but new
bots should use the folder. Use `load_prompt_store(...)` to get `.require()`,
which raises a clear error listing available keys.
"""
import json
import re
from pathlib import Path

_FILE_EXTS = (".md", ".txt")  # per-node prompt files in a folder


def load_prompts(path):
    """Load prompts from a folder (one <node>.md per prompt), a .md file
    (## key sections), or a .json file ({key: text}). Returns a dict
    key -> prompt text (stripped). Raises ValueError on duplicates/empty."""
    p = Path(path)
    if p.is_dir():
        return _load_dir(p)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: JSON prompt file must be a flat object {{key: text}}")
        prompts = {str(k): str(v) for k, v in data.items()}
    else:
        prompts = _parse_markdown(text, path)
    if not prompts:
        raise ValueError(f"{path}: no prompts found (expect '## key' sections, or a JSON object)")
    return prompts


def _load_dir(folder):
    """Load one prompt per file from a folder: key = filename stem, value = the
    whole file (stripped). Reads .md/.txt at the top level, sorted by name.
    A stem that collides (e.g. foo.md and foo.txt) raises ValueError."""
    prompts = {}
    files = sorted(f for f in folder.iterdir()
                   if f.is_file() and f.suffix.lower() in _FILE_EXTS)
    for f in files:
        key = f.stem
        if key in prompts:
            raise ValueError(f"{folder}: duplicate prompt key '{key}' "
                             f"(two files share the stem '{key}')")
        prompts[key] = f.read_text(encoding="utf-8").strip()
    if not prompts:
        raise ValueError(f"{folder}: no {'/'.join(_FILE_EXTS)} prompt files found")
    return prompts


def _parse_markdown(text, path):
    """Split a Markdown doc into {h2_heading: body}. H1 lines are ignored so you
    can title the file. Content runs until the next H2 (or end of file)."""
    prompts = {}
    key = None
    buf = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            if key is not None:
                prompts[key] = "\n".join(buf).strip()
            key = m.group(1).strip()
            if key in prompts:
                raise ValueError(f"{path}: duplicate prompt key '## {key}'")
            buf = []
        elif key is not None:
            buf.append(line)
        # lines before the first '## ' (e.g. an H1 title) are ignored
    if key is not None:
        prompts[key] = "\n".join(buf).strip()
    return prompts


class PromptStore(dict):
    """A dict of prompts with require() for fail-fast missing-key errors."""

    def require(self, *keys):
        """Return one prompt (single key) or a tuple (multiple keys); raise a
        clear error listing available keys if any is missing."""
        missing = [k for k in keys if k not in self]
        if missing:
            raise KeyError(f"prompt key(s) {missing} not found; available: {sorted(self)}")
        vals = tuple(self[k] for k in keys)
        return vals[0] if len(vals) == 1 else vals


def load_prompt_store(path):
    """Same as load_prompts() but returns a PromptStore (has .require())."""
    return PromptStore(load_prompts(path))


if __name__ == "__main__":
    print(__doc__)
