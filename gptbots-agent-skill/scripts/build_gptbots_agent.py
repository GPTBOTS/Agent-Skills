#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QuestionAnswer `.bot` builder. One of three generators:
  build_gptbots_agent.py     → QuestionAnswer .bot (this file)
  build_gptbots_flowagent.py → FlowAgent .bot
  build_gptbots_workflow.py  → Workflow .flow

A QuestionAnswer agent is a flat config — the leverage is almost entirely in the
identity `prompt` (see *Prompt quality for LLM-capable nodes* in SKILL.md), so
this builder is thin: it fills the required top-level skeleton, keeps model ids
blank for backend backfill, and `save()` runs `validate_gptbots_config.py`.
Keep the prompt as a Python string constant in your generation script and
regenerate the .bot on every revision.

Field names confirmed against a real platform export — note these gotchas:
  • the opening line is `firstMessage` (NOT `welcomeMessage`)
  • the suggested questions are `presetQuestions` (NOT `guidingQuestions`)
  • `maxRespTokens` should be set (default 4096); `creativityLevel` may be null
  • `multiModal.multiModalInput` must be present (else the console auto-save NPEs)

Example
-------
    from build_gptbots_agent import agent_config, save

    cfg = agent_config(
        "My Support Agent",
        prompt=IDENTITY_PROMPT,                # the field worth most of your effort
        first_message="Hello! How can I help you today?",
        preset_questions=["How do I return an item?", "What are the shipping fees?"],
        creativity=0.3, max_tokens=4096,
        description="Customer support agent",
        key_event_config={                     # optional; verify against a real export
            "enable": True, "messageThreshold": 10, "idleTimeoutMinutes": 3,
            "recentEventCount": 5, "extractionRules": "…",
            "eventTypes": [{"name": "refund", "description": "…"}]},
    )
    save(cfg, "my-agent.bot")
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Convenience re-export: keep the (often long) identity prompt in an external
# prompts.md / .json and load it with load_prompts(...).
try:
    from gptbots_prompts import load_prompts, load_prompt_store  # noqa: F401
except ImportError:
    load_prompts = load_prompt_store = None

DEFAULT_MAX_TOKENS = 4096
# Platform built-in avatar — a custom/blank logo URL renders as a broken icon, so
# default to the platform's bundled default avatar (override via logo=).
DEFAULT_AGENT_LOGO = "/developer/static/images/avatar/default_avatar_202506131619.png"


def agent_config(name, prompt, first_message=None, preset_questions=None, creativity=0.3,
                 max_tokens=DEFAULT_MAX_TOKENS, bot_type="QuestionAnswer", description="",
                 brief_introduction="", human_config=None, key_event_config=None, **extra):
    """Build a QuestionAnswer .bot dict.

    Field names match a real platform export: the opening line is `firstMessage`,
    the suggested questions are `presetQuestions` — using `welcomeMessage` /
    `guidingQuestions` imports them as nothing.

    creativity must be in [0, 0.95) or None (the platform allows a null
    creativityLevel); model id is left blank (backend backfills — never invent
    one); plugin auth / cross-org references must stay blank too. Pass any other
    documented top-level field (reasoningEffort, modeType, dataEnable+knowledge
    config, toolsEnable, …) via **extra — copy enum-bearing blocks from a real
    export rather than guessing.
    """
    if creativity is not None and not (0 <= creativity < 0.95):
        raise ValueError("creativityLevel must be in [0, 0.95) or None")
    if not (prompt and prompt.strip()):
        raise ValueError("the identity prompt is the highest-leverage field — it must be non-empty")
    cfg = {"formatVersion": "1.0", "exportType": "BOT",
           "exportTime": int(datetime.now(timezone.utc).timestamp() * 1000),  # epoch ms (Long) — ISO strings are rejected on import
           "name": name, "botType": bot_type,
           # Anti-NPE backfill: import copies `multiModal` verbatim (no default), but console
           # auto-save dereferences multiModalForm.multiModalInput.chatMode without a null
           # check (regression 2025-12-02) → a .bot imported without multiModal 500s on every
           # auto-save. Empty multiModalInput = non-null VO with null enum fields (safe).
           # Don't guess enum values; override via **extra with a block from a real export.
           "logo": DEFAULT_AGENT_LOGO,   # platform default avatar (override via logo= / extra)
           "multiModal": {"multiModalInput": {}},
           "chatModelVersionId": "", "creativityLevel": creativity,
           "maxRespTokens": int(max_tokens), "prompt": prompt}
    if first_message is not None:
        cfg["firstMessage"] = first_message          # the opening line (NOT welcomeMessage)
    if preset_questions:
        cfg["presetQuestions"] = list(preset_questions)  # suggested questions (NOT guidingQuestions)
    if description:
        cfg["description"] = description
    if brief_introduction:
        cfg["briefIntroduction"] = brief_introduction
    if human_config:
        cfg["humanConfig"] = human_config
    if key_event_config:
        cfg["keyEventConfig"] = key_event_config
    cfg.update(extra)
    return cfg


def save(cfg, path, validate=True):
    """Write JSON; then run validate_gptbots_config.py (same dir) if present."""
    p = Path(path)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {p}")
    validator = Path(__file__).resolve().parent / "validate_gptbots_config.py"
    if validate and validator.exists():
        return subprocess.run([sys.executable, str(validator), str(p)]).returncode
    return 0


def _demo(outdir):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    cfg = agent_config(
        "Demo Agent",
        prompt="# Role\nYou are a demo support agent.\n# Boundaries\nOnly answer "
               "demo-related questions; when unsure, say so honestly.",
        first_message="Hello!", preset_questions=["What is this?"], creativity=0.3)
    return save(cfg, out / "demo-agent.bot")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--demo":
        sys.exit(_demo(sys.argv[2]))
    print(__doc__)
