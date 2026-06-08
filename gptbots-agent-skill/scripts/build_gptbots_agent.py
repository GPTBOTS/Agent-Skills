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

Example
-------
    from build_gptbots_agent import agent_config, save

    cfg = agent_config(
        "My Support Agent",
        prompt=IDENTITY_PROMPT,                # the field worth most of your effort
        welcome="Hello! How can I help you today?",
        guiding_questions=["How do I return an item?", "What are the shipping fees?"],
        creativity=0.3,
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


def agent_config(name, prompt, welcome=None, guiding_questions=None, creativity=0.3,
                 bot_type="QuestionAnswer", description="", brief_introduction="",
                 human_config=None, key_event_config=None, **extra):
    """Build a QuestionAnswer .bot dict.

    creativity must be in [0, 0.95); model id is left blank (backend backfills —
    never invent one); plugin auth / cross-org references must stay blank too.
    Pass any additional documented top-level fields via **extra.
    """
    if not (0 <= creativity < 0.95):
        raise ValueError("creativityLevel must be in [0, 0.95)")
    if not (prompt and prompt.strip()):
        raise ValueError("the identity prompt is the highest-leverage field — it must be non-empty")
    cfg = {"formatVersion": "1.0", "exportType": "BOT",
           "exportTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "name": name, "botType": bot_type,
           "chatModelVersionId": "", "creativityLevel": creativity, "prompt": prompt}
    if welcome is not None:
        cfg["welcomeMessage"] = welcome
    if guiding_questions:
        cfg["guidingQuestions"] = list(guiding_questions)
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
        welcome="Hello!", guiding_questions=["What is this?"], creativity=0.3)
    return save(cfg, out / "demo-agent.bot")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--demo":
        sys.exit(_demo(sys.argv[2]))
    print(__doc__)
