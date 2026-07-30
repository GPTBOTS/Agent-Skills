#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LoopAgent `.bot` builder (botType=LoopAgent, formerly "Claw"). One of the
generators in this skill:
  build_gptbots_agent.py      -> QuestionAnswer .bot
  build_gptbots_flowagent.py  -> FlowAgent .bot
  build_gptbots_loopagent.py  -> LoopAgent .bot   (this file)
  build_gptbots_audioagent.py -> Audio Agent .bot
  build_gptbots_workflow.py   -> Workflow .flow

A LoopAgent has NO graph to design: the topology is fixed at 1 `ClawCenter`
plus 7 satellites with contractual ids (center / keyEvent-1 / handoff-1 /
knowledge-1 / skills-1 / tools-1 / database-1 / subagent-1), wired by 7 edges
`center->{id}` with sort 0..6. This builder emits that topology exactly as the
platform seeds it (ClawDefaultsHelper on the Java side, claw-rule-codec.ts on
the front end), so the only things you decide are the identity prompt, the loop
guardrails, and which satellites are on.

Where the leverage is: `center.content.prompts.persona`, the identity prompt. It
is the ONLY operator-editable prompt on a LoopAgent - the console has no entry
point for the other prompt fields, so everything you want the agent to do (tone,
reply length, when to search knowledge, when to hand off) belongs in the persona.
The top-level `prompt` stays empty for a LoopAgent.

`style` and `routing` are still emitted as empty strings for wire parity with a
platform-seeded bot, but this builder deliberately gives you no way to fill them:
their console entry points were removed, so text written there could never be
reviewed, edited or reset by the operator afterwards.

Import-fatal rules enforced here (see references/create-gptbots-loopagent.md):
  * a ClawCenter component is mandatory
  * loop: maxTurns [1,100], maxErrors [0,50], maxBudgetInputTokens >= 0, integers
  * <= 64 components; component ids are STRINGS (unlike FlowAgent's ints)
  * llm.baseUrl must be null or a public http(s) URL (SSRF scan on import)
  * llm.model is an AMH gateway model_version_id - leave blank, never a name
  * environment-bound ids (docGroupIds / tableIds / pluginIds / skillRefs) are
    cleared or filtered on import: ship them empty unless transferring
  * clawToolTraceRecentRounds in [0,5]; multiModal.multiModalInput must exist

Example
-------
    from build_gptbots_loopagent import loopagent_config, save
    from gptbots_prompts import load_prompt_store

    P = load_prompt_store("prompts/")        # persona.md
    cfg = loopagent_config(
        "Support LoopAgent",
        persona=P.require("persona"),
        knowledge=True, tools=True, database=False, subagent=False,
        handoff=True, key_event=True,
        max_turns=25, max_errors=5, max_budget_input_tokens=0,
        message_mode="QUEUE", tool_trace_recent_rounds=1,
    )
    save(cfg, "support-loopagent.bot")
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from gptbots_prompts import load_prompts, load_prompt_store  # noqa: F401
except ImportError:
    load_prompts = load_prompt_store = None

# --- contractual ids / order (claw-topology.ts SATELLITES == ClawDefaultsHelper) ---
CENTER_ID = "center"
SATELLITES = [
    ("keyEvent-1", "ClawKeyEvent"),
    ("handoff-1", "Human"),
    ("knowledge-1", "Dataset"),
    ("skills-1", "ClawSkill"),
    ("tools-1", "ToolApi"),
    ("database-1", "ClawDB"),
    ("subagent-1", "ClawSubAgent"),
]
MAX_COMPONENTS = 64          # ImportSecurityScanner.MAX_CLAW_COMPONENTS
MAX_SKILL_REFS = 10          # claw-rule-codec.ts MAX_CLAW_SKILL_REFS
SKILL_REF_SOURCES = {"SYSTEM", "ORGANIZATION"}
MESSAGE_MODES = {"QUEUE", "APPEND"}
SEARCH_MODES = {"mix", "semantics", "keyword"}
SEVERITIES = {"low", "normal", "high", "urgent"}
SLA_HIGH_MS = 60 * 60 * 1000
SLA_NORMAL_MS = 24 * 60 * 60 * 1000
DEFAULT_MAX_TOKENS = 4096
DEFAULT_AGENT_LOGO = "/developer/static/images/avatar/default_avatar_202506131619.png"

# Known-good multiModal block, matching what BotConverter seeds for a LoopAgent.
# It must be COMPLETE, not just non-null: the import copies `multiModal` verbatim
# with no backfill, and two backend paths dereference it without a null check —
#   * console auto-save reads multiModalInput.chatMode  -> HTTP 500 on every save
#   * Open API v2 chat unboxes multiModalInput.getFileLimit() (int, not Integer)
#     -> every POST /v2/conversation/message answers 50000 NullPointerException
# so an imported bot with `{"multiModalInput": {}}` imports fine and is then dead
# on the API. Do not hand-edit the enum strings; override via multi_modal=.
_DEFAULT_MULTIMODAL = {
    "multiModalInput": {"fileLimit": 1, "fileMode": "DISABLED", "imageMode": "auto",
                        "audioMode": "ASR", "chatMode": "Q_A", "textSwitch": True,
                        "fileSupportTypes": None, "audioModelVersionId": None,
                        "fileSwitch": None, "asrPrompt": None},
    "multiModalOutput": {"textLanguage": "auto", "audioMode": "DEFAULT", "audioVoice": None,
                         "audioModelVersionId": None, "audioModeOutput": "TTS",
                         "textSwitch": True, "showAiGeneratedContent": False},
}
# A gateway model_version_id is an opaque 24-hex id; a readable name is the
# classic mistake (the bot then cannot route to the AMH gateway).
_MODEL_ID_RE = re.compile(r"^[0-9a-fA-F]{24}$")


def _int_in(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer, got %r" % (label, value))
    if value < low or (high is not None and value > high):
        bound = "[%s, %s]" % (low, "inf" if high is None else high)
        raise ValueError("%s must be in %s, got %s" % (label, bound, value))
    return value


def _check_base_url(base_url):
    if base_url is None or base_url == "":
        return None
    low = str(base_url).strip().lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        raise ValueError("llm.baseUrl must be null or an http(s) URL, got %r" % base_url)
    host = low.split("://", 1)[1].split("/", 1)[0].split("@")[-1].split(":")[0]
    if (host in ("localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254")
            or host.startswith("10.") or host.startswith("192.168.")
            or host.startswith("169.254.") or host.endswith(".local")
            or re.match(r"^172\.(1[6-9]|2[0-9]|3[01])\.", host)):
        raise ValueError("llm.baseUrl points at an internal/loopback address (%s) - "
                         "the import security scan rejects it" % host)
    return str(base_url).strip()


def claw_center(persona="", model="", base_url=None,
                max_tokens=DEFAULT_MAX_TOKENS, max_turns=25, max_errors=5,
                max_budget_input_tokens=0, model_dynamic_params=None, **llm_extra):
    """Build the mandatory ClawCenter component (model + loop guardrails + prompts)."""
    _int_in(max_turns, 1, 100, "loop.maxTurns")
    _int_in(max_errors, 0, 50, "loop.maxErrors")
    _int_in(max_budget_input_tokens, 0, None, "loop.maxBudgetInputTokens")
    _int_in(int(max_tokens), 1, None, "llm.maxTokens")
    model = (model or "").strip()
    if model and not _MODEL_ID_RE.match(model):
        print("warning: llm.model=%r does not look like an AMH gateway model_version_id "
              "(24-hex). Leave it blank so the import backfills the platform default."
              % model, file=sys.stderr)
    llm = {"model": model, "baseUrl": _check_base_url(base_url),
           "maxTokens": int(max_tokens),
           "modelDynamicParams": list(model_dynamic_params or [])}
    llm.update(llm_extra)
    return {
        "id": CENTER_ID,
        "type": "ClawCenter",
        "content": {
            # Always true - the engine treats false as a kill switch (40300).
            "enabled": True,
            "llm": llm,
            "loop": {"maxTurns": max_turns, "maxErrors": max_errors,
                     "maxBudgetInputTokens": max_budget_input_tokens},
            # persona is the only editable prompt; `style` / `routing` keep their
            # keys for wire parity with the platform seed but are always emitted
            # empty ("" == use the engine default) since the console dropped their
            # entry points. Never echo an engine default back into any of them.
            "prompts": {"persona": persona or "", "style": "", "routing": ""},
        },
        "nextComponents": [
            {"id": "%s->%s" % (CENTER_ID, sid), "nextComponentId": sid, "sort": i}
            for i, (sid, _type) in enumerate(SATELLITES)
        ],
    }


def _merge_multimodal(override, message_mode):
    """Full multiModal block + the LoopAgent messageMode, keeping any override."""
    import copy
    block = copy.deepcopy(_DEFAULT_MULTIMODAL)
    if override:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(block.get(key), dict):
                block[key].update(value)
            else:
                block[key] = value
    block.setdefault("multiModalInput", {})["messageMode"] = message_mode
    if block["multiModalInput"].get("fileLimit") is None:
        raise ValueError("multiModalInput.fileLimit must be an integer — the Open API v2 "
                         "chat endpoint unboxes it and answers 50000 NullPointerException "
                         "when it is null")
    return block


def _satellite(sid, stype, content):
    # Satellites carry no outgoing edges (the center owns the radial layout);
    # the platform serializer omits `nextComponents` entirely on them.
    return {"id": sid, "type": stype, "content": content}


def claw_rule(center, key_event=True, default_severity="normal",
              handoff=True,
              knowledge=True, doc_group_ids=None, match_data_limit=5, doc_correlation=0.8,
              search_mode="mix", embedding_rate=0.7, rerank=False, rerank_model_version_id=None,
              graph_enable=False, graph_hop_limit=None,
              metadata_filter=None, metadata_filter_logic="AND",
              skills=True, skill_refs=None,
              tools=True, plugin_ids=None,
              database=False, table_ids=None,
              subagent=False, parallel_count=1, subagent_trigger_prompt=""):
    """Build the full clawRule: the center plus all 7 satellites, in contract order."""
    if default_severity not in SEVERITIES:
        raise ValueError("defaultSeverity must be one of %s" % sorted(SEVERITIES))
    if search_mode not in SEARCH_MODES:
        raise ValueError("searchMode must be one of %s" % sorted(SEARCH_MODES))
    if metadata_filter_logic not in ("AND", "OR"):
        raise ValueError("metadataFilterLogic must be AND or OR")
    _int_in(int(match_data_limit), 1, 50, "Dataset.matchDataLimit")
    if not (0 <= float(doc_correlation) <= 1):
        raise ValueError("Dataset.docCorrelation must be in [0, 1]")
    if not (0 <= float(embedding_rate) <= 1):
        raise ValueError("Dataset.embeddingRate must be in [0, 1]")
    if graph_hop_limit is not None:
        _int_in(int(graph_hop_limit), 1, 5, "Dataset.graphHopLimit")
    _int_in(int(parallel_count), 1, 5, "ClawSubAgent.parallelCount")

    refs = []
    for i, ref in enumerate(skill_refs or []):
        if not isinstance(ref, dict) or not ref.get("skillId"):
            raise ValueError("skillRefs[%d] must be {skillId, enabled, source}" % i)
        source = ref.get("source", "ORGANIZATION")
        if source not in SKILL_REF_SOURCES:
            raise ValueError("skillRefs[%d].source must be one of %s (an unknown value makes "
                             "the row malformed and it is dropped)" % (i, sorted(SKILL_REF_SOURCES)))
        refs.append({"skillId": str(ref["skillId"]),
                     "enabled": bool(ref.get("enabled", True)), "source": source})
    if len(refs) > MAX_SKILL_REFS:
        raise ValueError("at most %d skillRefs may be attached to one agent" % MAX_SKILL_REFS)

    components = [center]
    contents = {
        # keyEvent: only `enabled` + the bot-level type catalogue + defaultSeverity
        # actually drive behaviour; the SLA / title / auto-* fields are inert but
        # are part of the shape the platform seeds, so we keep them.
        "keyEvent-1": {"enabled": bool(key_event), "defaultSeverity": default_severity,
                       "titleStrategy": "router_decided", "autoCreateOnSpawn": True,
                       "autoResolveIdleDays": 7, "slaHighMs": SLA_HIGH_MS,
                       "slaNormalMs": SLA_NORMAL_MS, "keyEventTypes": []},
        # handoff: kill switch only - the real config is bot-level humanConfig,
        # whose `enable` overwrites this every turn.
        "handoff-1": {"enabled": bool(handoff)},
        "knowledge-1": {"enabled": bool(knowledge),
                        "docGroupIds": list(doc_group_ids or []),
                        "matchDataLimit": int(match_data_limit),
                        "docCorrelation": float(doc_correlation),
                        "rerankSwitch": bool(rerank),
                        "rerankModelVersionId": rerank_model_version_id,
                        "searchMode": search_mode,
                        "embeddingRate": float(embedding_rate),
                        "graphEnable": bool(graph_enable),
                        "graphHopLimit": (int(graph_hop_limit)
                                          if graph_hop_limit is not None else None),
                        "metadataFilter": list(metadata_filter or []),
                        "metadataFilterLogic": metadata_filter_logic},
        "skills-1": {"enabled": bool(skills), "skills": [], "skillRefs": refs},
        "tools-1": {"enabled": bool(tools), "pluginIds": list(plugin_ids or [])},
        "database-1": {"enabled": bool(database), "tableIds": list(table_ids or [])},
        "subagent-1": {"enabled": bool(subagent), "parallelCount": int(parallel_count),
                       "triggerPrompt": subagent_trigger_prompt or ""},
    }
    for sid, stype in SATELLITES:
        components.append(_satellite(sid, stype, contents[sid]))
    if len(components) > MAX_COMPONENTS:
        raise ValueError("clawRule may not exceed %d components" % MAX_COMPONENTS)
    return {"thumbnail": None, "components": components, "comments": []}


def loopagent_config(name, persona="",
                     first_message=None, preset_questions=None,
                     message_mode="QUEUE", tool_trace_recent_rounds=1,
                     short_term_memory=True, short_term_memory_round=30,
                     description="", logo=DEFAULT_AGENT_LOGO, multi_modal=None,
                     human_config=None, private_skills=None, rule=None, **kwargs):
    """Build a LoopAgent .bot dict.

    Prompt/loop/satellite keyword arguments are forwarded to claw_center() and
    claw_rule(); pass a prebuilt `rule=` to bypass both. Any other documented
    top-level field (dataEnable, toolsEnable, workflowEnable+associatedWorkflows,
    reasoningEffort, plugins, userProperties, chatSecurityConfig, ...) can be
    passed through **kwargs and lands verbatim on the config.
    """
    # Removed parameters: `style` / `routing` used to be editable center prompts.
    # Their console entry points are gone, so they must not be filled — fail loudly
    # instead of letting **kwargs drop the text onto the config as a top-level key.
    for gone in ("style", "routing", "router"):
        if gone in kwargs:
            raise ValueError(
                "`%s` is no longer a LoopAgent prompt — the console removed its entry point, "
                "so text there would drive behaviour nobody can review or reset. Fold it into "
                "`persona`, the only editable prompt." % gone)
    if message_mode not in MESSAGE_MODES:
        raise ValueError("messageMode must be QUEUE or APPEND")
    _int_in(int(tool_trace_recent_rounds), 0, 5, "clawToolTraceRecentRounds")
    _int_in(int(short_term_memory_round), 1, 200, "shortTermMemoryRound")

    center_keys = ("model", "base_url", "max_tokens", "max_turns", "max_errors",
                   "max_budget_input_tokens", "model_dynamic_params")
    rule_keys = ("key_event", "default_severity", "handoff", "knowledge", "doc_group_ids",
                 "match_data_limit", "doc_correlation", "search_mode", "embedding_rate",
                 "rerank", "rerank_model_version_id", "graph_enable", "graph_hop_limit",
                 "metadata_filter", "metadata_filter_logic", "skills", "skill_refs",
                 "tools", "plugin_ids", "database", "table_ids", "subagent",
                 "parallel_count", "subagent_trigger_prompt")
    center_kw = {k: kwargs.pop(k) for k in list(kwargs) if k in center_keys}
    rule_kw = {k: kwargs.pop(k) for k in list(kwargs) if k in rule_keys}
    if rule is None:
        rule = claw_rule(claw_center(persona=persona, **center_kw), **rule_kw)
    elif center_kw or rule_kw:
        raise ValueError("pass either rule= or the center/satellite keyword arguments, not both")

    cfg = {
        "formatVersion": "1.0", "exportType": "BOT",
        # epoch milliseconds as a bare integer - an ISO string fails import
        "exportTime": int(datetime.now(timezone.utc).timestamp() * 1000),
        "name": name, "botType": "LoopAgent", "logo": logo,
        # The identity that runs is clawRule.center.content.prompts.persona;
        # the top-level prompt is dead text on a LoopAgent.
        "prompt": "",
        "chatModelVersionId": "",       # backend backfills; never invent one
        # Full known-good block (see _DEFAULT_MULTIMODAL: a partial one passes
        # import and then 500s on chat) plus the LoopAgent-only message mode.
        "multiModal": _merge_multimodal(multi_modal, message_mode),
        "shortTermMemory": bool(short_term_memory),
        "shortTermMemoryRound": int(short_term_memory_round),
        # Meaningless for LoopAgent (the engine self-manages memory) - kept at
        # the values the platform seeds so the file reads like a real export.
        "longTermMemory": False, "memoryEnable": True,
        "clawToolTraceRecentRounds": int(tool_trace_recent_rounds),
        "clawRule": rule,
        "privateSkills": list(private_skills or []),
    }
    if first_message is not None:
        cfg["firstMessage"] = first_message
    if preset_questions:
        cfg["presetQuestions"] = list(preset_questions)
    if description:
        cfg["description"] = description
    if human_config:
        cfg["humanConfig"] = human_config
    cfg.update(kwargs)
    return cfg


def save(cfg, path, validate=True):
    """Write JSON; then run validate_gptbots_config.py (same dir) if present."""
    p = Path(path)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote %s" % p)
    validator = Path(__file__).resolve().parent / "validate_gptbots_config.py"
    if validate and validator.exists():
        return subprocess.run([sys.executable, str(validator), str(p)]).returncode
    return 0


def _demo(outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = loopagent_config(
        "Demo LoopAgent",
        persona="# Role\nYou are the front-line support agent for a demo SaaS product.\n"
                "Answer in the customer's language.\n\n"
                "# Boundaries\nNever invent policy: if the knowledge base does not cover it, "
                "say so and offer a human handoff.\n\n"
                "# How to handle a message\nSearch the knowledge base before answering any "
                "product or billing question. Open a key event for anything the customer "
                "expects follow-up on. Hand off to a human on refunds, account security, or "
                "an explicit request.\n\n"
                "# Reply style\nUnder 120 words. Plain sentences, no marketing tone. "
                "One concrete next step per reply.",
        first_message="Hi! How can I help you today?",
        knowledge=True, tools=True, database=False, subagent=False,
        handoff=True, key_event=True,
        max_turns=25, max_errors=5, max_budget_input_tokens=0,
        message_mode="QUEUE", tool_trace_recent_rounds=1,
    )
    return save(cfg, out / "demo-loopagent.bot")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--demo":
        sys.exit(_demo(sys.argv[2]))
    print(__doc__)
