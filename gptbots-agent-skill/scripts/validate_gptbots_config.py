#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPTBots .bot / .flow config quality-check script (offline, zero network, pure standard library).

After generating a .bot/.flow you *must* run this script; on a non-zero exit code, read errors,
fix, and rerun, delivering/prompting import only after the quality check passes. The rules are
ported from the real backend and frontend validation:
  - Backend oversea-ailab-bot .../service/workflow/component/utils/WorkflowRuntimeChecker.java (graph integrity)
  - Backend .../service/workflow/component/utils/WorkflowNodeChecker.java (node parameters)
  - Backend .../service/exportimport/BotTransferService.java (import stripping/defaults + strict enum parsing)
  - Backend .../bean/enums/HumanManufacturerEnum.java, HumanConfigStatus.java (humanConfig enums)
  - Backend .../bean/entity/BotFlowComponent.java + its nested DTOs/enums (per-component fields & enums)
  - Backend .../common/enums + .../common/model/bot (ReasoningEffortEnum, ReasoningShowStatusEnum,
    DataSourceShowType, CustomKnowledgeTypeEnum, BotResponseFormatType, BotModeType, FlowContentType,
    PromptMessageType, BotMultiModalDataType, CombineEnum, PropertyTypeEnum, BotFileModeEnum, …)
  - Frontend ailab-d-developer-frontend/src/features/workflow/canvas/data/handle-node-error.ts (checkNodeErrors)
  - Frontend .../features/flow-bot/canvas/data/handle-connection-point.ts + convert.ts
    (FlowAgent edge handle ids: {side}{id}-{key}[_suffix]; a handle that doesn't resolve to a
    rendered port makes the canvas draw a distorted/misrouted edge)
  - Backend .../bean/entity/ClawFlow*.java, .../consts/ClawComponentTypes.java,
    .../helper/ClawDefaultsHelper.java, .../helper/ClawLoopControlValidator.java,
    .../service/exportimport/ClawRuleTransferHelper.java + ImportSecurityScanner.java
    (LoopAgent clawRule topology, loop-control ranges, import stripping, SSRF/DoS limits)
  - Engine ailab-claw-engine/.../csagent/botFlowAdapter.ts + types/botFlow.ts and frontend
    .../features/claw-bot/data/claw-rule-codec.ts (LoopAgent wire shape & defaults)
  - Backend .../helper/audio/AudioConfigValidator.java, .../bean/entity/BotMultiModal.java
    (+ entity/audio/*.java), .../common/enums/AudioEngineMode.java (Audio Agent voice config)
When the schema changes, re-sync against these and bump the skill version.

Usage:
  python3 validate_gptbots_config.py <file.bot|file.flow> [--json]
Exit codes: 0 = pass (no error); 1 = has error; 2 = usage/read error.
"""
import argparse
import json
import re
import sys

# Bot types this skill authors. Mirrors ai.altatech.oversea.common.enums.BotType, minus the
# types this skill does not generate (MultiAgent, Clawsearch). "Claw" is the historical alias
# of LoopAgent - the backend still accepts it on read, but always emit "LoopAgent".
BOT_TYPES = {"QuestionAnswer", "Flow", "Workflow", "LoopAgent", "Audio"}
EXPORT_TYPES = {"BOT", "WORKFLOW"}

# Valid HumanManufacturerEnum values (.bot top-level `humanConfig.manufacturer`).
# Mirrors ai.altatech.oversea.bot.bean.enums.HumanManufacturerEnum. The values are enum
# names, NOT display names — a UI/display name (e.g. "livechat" instead of "LiveChat",
# "Crescendo Lab" instead of "Omnichat") makes the backend import reject the file with:
#   Invalid import file: value "..." is not allowed for field "manufacturer".
HUMAN_MANUFACTURERS = {"Intercom", "Webhook", "LiveChat", "SoBot", "ZohoSalesIQ", "LiveDesk", "Omnichat"}
# Valid HumanConfigStatus values (.bot `humanConfig.status`).
# Mirrors ai.altatech.oversea.bot.bean.enums.HumanConfigStatus.
HUMAN_CONFIG_STATUS = {"enable", "disable"}

# Valid FlowComponentType enum values (FlowAgent .bot `flowRule.components[].type`).
# Mirrors ai.altatech.oversea.common.enums.FlowComponentType — an unknown value (e.g. the
# UI name "Classifier" instead of the enum "Branch") makes the backend import reject the file.
FLOW_COMPONENT_TYPES = {
    "Input", "Output", "LLM", "Bool", "Branch", "Predefine", "Dataset", "Human",
    "Condition", "Regular", "ChatGather", "FormGather", "Message", "ToolApi", "Workflow", "Variable",
}
# Valid WorkflowNodeType enum values (Workflow .flow `workflow.workflowNodes[].type`).
# Mirrors ai.altatech.oversea.common.enums.WorkflowNodeType.
WORKFLOW_NODE_TYPES = {
    "START", "END", "LLM", "DATABASE", "DATASET", "AUDIO_LLM", "INTENT", "CODE", "HTTP",
    "CONDITION", "COMMENT", "TOOL_API", "FILE_PARSE", "TEXT_PROCESS", "VARIABLE_AGGREGATE",
    "LOOP", "BATCH", "NEXT_LOOP", "CONTINUE", "BREAK", "SET_INTERMEDIATE_VARIABLE",
}
MAX_FILE_SIZE = 50 * 1024 * 1024
VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# WorkflowNodeChecker: node type -> required param field name
NODE_REQUIRED_PARAM = {
    "LLM": "llmParam",
    "AUDIO_LLM": "audioLlmParam",
    "CODE": "codeParam",
    "CONDITION": "conditionParam",
    "DATABASE": "databaseParam",
    "DATASET": "datasetParam",
    "HTTP": "httpParam",
    "INTENT": "intentParam",
    "COMMENT": "commentParam",
    "TOOL_API": "toolApiParam",
    "FILE_PARSE": "fileParseParam",
    "TEXT_PROCESS": "textProcessParam",
    "VARIABLE_AGGREGATE": "variableAggregateParam",
    "LOOP": "loopParam",
    "BATCH": "batchParam",
    "SET_INTERMEDIATE_VARIABLE": "setIntermediateVariableParam",
    "END": "endParam",
}

# --- Enum value sets (mirror the backend enums). Out-of-enum strings — top-level OR nested in a
# --- flow component — are rejected by the backend's strict import parse (InvalidFormatException),
# --- so they are validated as ERRORS, but only when the field is present (the backend does not
# --- require these fields). Values are exact enum *names* (case-sensitive). NOTE: multiModal
# --- input/output `audioMode`/`chatMode`/`imageMode` are intentionally NOT validated — the same
# --- JSON key maps to different enums on input vs output, which would cause false positives.
REASONING_EFFORTS = {"MINIMAL", "LOW", "MEDIUM", "HIGH"}                       # ReasoningEffortEnum
REASONING_SHOW = {"SHOW", "COLLAPSE", "HIDDEN"}                               # ReasoningShowStatusEnum
DATA_SOURCE_SHOW = {"MIN_SHOW", "LIST_SHOW", "CORNER_SHOW"}                   # DataSourceShowType
CUSTOM_KNOWLEDGE_TYPES = {"DEFAULT", "LLM"}                                   # CustomKnowledgeTypeEnum
RESPONSE_FORMATS = {"Text", "JsonObject", "JsonSchema"}                       # BotResponseFormatType (by name)
MODE_TYPES = {"general", "excellent", "specialist"}                          # BotModeType
MULTI_MODAL_DATA_TYPES = {"Text", "Image", "File", "Audio", "Video", "Document"}  # BotMultiModalDataType
FLOW_CONTENT_TYPES = {"Form", "Text", "Json", "Card"}                         # FlowContentType (Predefine/Message)
PROMPT_MESSAGE_TYPES = {"Role", "LongMemory", "ShortMemory", "Dataset", "Input",
                        "Output", "Plugin", "Content", "Choices", "Condition", "Attr", "Gather"}  # PromptMessageType
GATHER_FIELD_TYPES = {"userProperty", "selfDefining"}                         # GatherFieldType
GATHER_VALUE_TYPES = {"string", "bool", "integer", "number", "datetime", "list"}  # GatherFieldValueTypeEnum
OPTION_FIELD_TYPES = {"string", "multiString", "bool", "integer", "number",
                      "datetime", "phoneNumber", "email", "radio", "checkbox"}  # OptionFieldTypeEnum
FORM_GATHER_TYPES = {"single", "all"}                                         # FormGatherType
VARIABLE_TYPES = {"USER_PROPERTY", "CUSTOM_VARIABLE"}                         # VariableType (legacy field, optional)
VARIABLE_OPERATE_TYPES = {"CLEAR", "COVER", "APPEND"}                         # VariableOperateType (legacy field)
# Real export shape of variableSetValueConfigs[] is {variableName, operation, value};
# `operation` is capitalized (Cover/Clear/Append), NOT the legacy COVER/CLEAR/APPEND.
VARIABLE_OPERATIONS = {"Cover", "Clear", "Append"}                            # operation (real export)
COMBINE_TYPES = {"and", "or"}                                                 # CombineEnum
REGULAR_CATEGORIES = {"GlobalVariable", "UserProperty", "BrowserProperty", "Upstream",
                      "WhatsApp", "Telegram", "LiveChat", "LiveDesk", "Line", "Start",
                      "CustomVariable", "KeyEvent"}                            # RegularItemCategoryEnum
PROPERTY_TYPES = {"string", "number", "datetime", "bool", "list"}            # PropertyTypeEnum
FILE_MODES = {"SYSTEM", "LLM", "DISABLED"}                                    # BotFileModeEnum

# --- FlowAgent canvas handle keys (frontend handle-connection-point.ts `buildHandleId`). An edge's
# --- `sourceHandle`/`targetHandle` is `{side}{componentId}-{key}[_{suffix}]`. If the embedded id or
# --- key is wrong, the canvas cannot resolve the port and falls back to the node origin → the edge
# --- renders distorted/misrouted. The base key (before any `_suffix`) must match the component type.
HANDLE_TARGET_KEY = {  # left/input handle key per FlowComponentType
    "Input": "input", "Output": "output", "LLM": "LLM", "Bool": "boolean",
    "Branch": "branch", "Predefine": "preset", "Message": "message", "Dataset": "knowledge",
    "Human": "artificial", "Condition": "conditions", "Regular": "regular",
    "ChatGather": "qa-collect", "FormGather": "form-collect", "Workflow": "workflow",
    "ToolApi": "toolapi", "Variable": "variable",
}
# right/output handle key per type: same as target, EXCEPT FormGather emits "formgather" on its
# suffixed outputs (built via the default lowercase path), and Output/Human have no source handle.
HANDLE_SOURCE_KEY = {k: v for k, v in HANDLE_TARGET_KEY.items() if k not in ("Output", "Human")}
HANDLE_SOURCE_KEY["FormGather"] = "formgather"


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, code, path, message, fix=""):
        self.errors.append({"code": code, "path": path, "message": message, "fix": fix})

    def warn(self, code, path, message, fix=""):
        self.warnings.append({"code": code, "path": path, "message": message, "fix": fix})

    @property
    def ok(self):
        return len(self.errors) == 0


def _is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def _check_enum(value, allowed, code, path, rep, label):
    """Error if `value` is present (non-blank) and not in the allowed enum set."""
    if value is None or value == "":
        return
    if value not in allowed:
        rep.err(code, path, f"Invalid {label}: {value}",
                "Use one of: " + ", ".join(sorted(allowed)))


def _check_list_enum(values, allowed, code, path, rep, label):
    """Like _check_enum but for a list field; validates each present item."""
    if not isinstance(values, list):
        return
    for i, v in enumerate(values):
        _check_enum(v, allowed, code, f"{path}[{i}]", rep, label)


def _parse_handle(h):
    """Parse a canvas handle id `{side}{id}-{key}[_{suffix}]`.

    Returns (side, node_id_str, base_key) or None if malformed. side is 'left' or 'right';
    base_key is the part after `{id}-` and before the first `_` (so hyphenated keys like
    `qa-collect` / `form-collect` are preserved, while `_true`/`_<id>` suffixes are dropped).
    """
    if not isinstance(h, str):
        return None
    if h.startswith("right"):
        side, body = "right", h[5:]
    elif h.startswith("left"):
        side, body = "left", h[4:]
    else:
        return None
    dash = body.find("-")
    if dash <= 0:
        return None
    return side, body[:dash], body[dash + 1:].split("_", 1)[0]


def check_top_level_enums(cfg, rep):
    """Validate top-level enum fields (apply to every bot type). Backend strict-parses these."""
    if not isinstance(cfg, dict):
        return
    _check_enum(cfg.get("reasoningEffort"), REASONING_EFFORTS, "ENUM_REASONING_EFFORT", "$.reasoningEffort", rep, "reasoningEffort")
    _check_enum(cfg.get("showReasoning"), REASONING_SHOW, "ENUM_SHOW_REASONING", "$.showReasoning", rep, "showReasoning")
    _check_enum(cfg.get("dataSourceShowType"), DATA_SOURCE_SHOW, "ENUM_DATA_SOURCE_SHOW", "$.dataSourceShowType", rep, "dataSourceShowType")
    _check_enum(cfg.get("customKnowledgeType"), CUSTOM_KNOWLEDGE_TYPES, "ENUM_CUSTOM_KNOWLEDGE", "$.customKnowledgeType", rep, "customKnowledgeType")
    _check_enum(cfg.get("responseFormat"), RESPONSE_FORMATS, "ENUM_RESPONSE_FORMAT", "$.responseFormat", rep, "responseFormat")
    _check_enum(cfg.get("modeType"), MODE_TYPES, "ENUM_MODE_TYPE", "$.modeType", rep, "modeType")
    _check_list_enum(cfg.get("multiResponseTypes"), MULTI_MODAL_DATA_TYPES, "ENUM_MULTI_RESPONSE", "$.multiResponseTypes", rep, "multiResponseTypes")


# ----------------------------- L0 top level -----------------------------

def check_top_level(cfg, rep):
    if not isinstance(cfg, dict):
        rep.err("L0_NOT_OBJECT", "$", "The config root must be a JSON object")
        return None
    if _is_blank(cfg.get("name")):
        rep.err("L0_NAME", "$.name", "Missing name", "Set a meaningful name")
    export_type = cfg.get("exportType")
    if export_type not in EXPORT_TYPES:
        rep.err("L0_EXPORT_TYPE", "$.exportType", f"Invalid exportType: {export_type}",
                "Set it to BOT or WORKFLOW")
    bot_type = cfg.get("botType")
    if bot_type not in BOT_TYPES:
        rep.err("L0_BOT_TYPE", "$.botType", f"Invalid botType: {bot_type}",
                "Set it to QuestionAnswer / Flow / LoopAgent / Audio / Workflow")
    # exportType / botType consistency
    if bot_type == "Workflow" and export_type != "WORKFLOW":
        rep.err("L0_TYPE_MISMATCH", "$.exportType", "Workflow requires exportType=WORKFLOW")
    if bot_type in {"QuestionAnswer", "Flow", "LoopAgent", "Audio"} and export_type == "WORKFLOW":
        rep.err("L0_TYPE_MISMATCH", "$.exportType", f"{bot_type} requires exportType=BOT")
    if _is_blank(cfg.get("formatVersion")):
        rep.warn("L0_FORMAT_VERSION", "$.formatVersion", "It is recommended to set formatVersion (e.g. \"1.0\")")
    export_time = cfg.get("exportTime")
    if export_time is not None and (isinstance(export_time, bool) or not isinstance(export_time, int)):
        rep.err("L0_EXPORT_TIME", "$.exportTime",
                f"exportTime must be an epoch-milliseconds integer (Long), got {type(export_time).__name__}: {export_time!r}",
                "Use int(datetime.now(timezone.utc).timestamp() * 1000); ISO strings fail import")
    # Auto-save NPE guard (backend regression 2025-12-02): the import copies `multiModal`
    # verbatim with no default backfill, while the console auto-save dereferences
    # multiModalForm.multiModalInput.chatMode WITHOUT a null check — so a BOT imported
    # without a non-null multiModal.multiModalInput 500s on EVERY auto-save (the import
    # itself succeeds, the bot is then uneditable). Normally-created bots get defaults at
    # creation and never hit this; only imported bots do.
    if export_type == "BOT":
        mm = cfg.get("multiModal")
        mmi = mm.get("multiModalInput") if isinstance(mm, dict) else None
        if not isinstance(mmi, dict):
            rep.err("L0_MULTIMODAL_AUTOSAVE_NPE", "$.multiModal",
                    "multiModal.multiModalInput is missing/null — the imported bot will hit a "
                    "backend NPE (HTTP 500) on every console auto-save",
                    'Emit the full known-good block (builder DEFAULT_MULTIMODAL()); a bare '
                    '{"multiModalInput": {}} survives auto-save but still dies on the chat API '
                    "(see L0_MULTIMODAL_FILE_LIMIT). Do NOT guess audioMode/chatMode/imageMode "
                    "enum values — copy them from a real export")
        else:
            # BotChatOpenAPIVersion2DataPrePreparationService unboxes
            #   int inputFileLimit = ...getMultiModalInput().getFileLimit();
            # with no null check, so a .bot whose multiModalInput omits fileLimit imports
            # cleanly, saves cleanly, and then answers EVERY POST /v2/conversation/message
            # with 50000 "NullPointerException - Cannot invoke java.lang.Integer.intValue()".
            # Console-created bots are seeded with fileLimit; only imported ones hit this.
            limit = mmi.get("fileLimit")
            if limit is None or isinstance(limit, bool) or not isinstance(limit, int):
                rep.err("L0_MULTIMODAL_FILE_LIMIT", "$.multiModal.multiModalInput.fileLimit",
                        "multiModalInput.fileLimit is missing/not an integer — the Open API v2 "
                        "chat endpoint unboxes it, so every message returns "
                        "50000 NullPointerException (import and console auto-save still succeed, "
                        "which is why this passes unnoticed)",
                        "Set an integer (1 is the platform default for a new bot), or emit the "
                        "whole known-good multiModal block from the builder")
    # QuestionAnswer field-name gotchas (confirmed against a real export): the opening
    # line is `firstMessage` and the suggested questions are `presetQuestions`. The
    # plausible-looking `welcomeMessage` / `guidingQuestions` are dropped on import.
    if bot_type in ("QuestionAnswer", "Audio", "LoopAgent"):
        if "welcomeMessage" in cfg and "firstMessage" not in cfg:
            rep.warn("AGENT_WELCOME_FIELD", "$.welcomeMessage",
                     "use `firstMessage` for the opening line; `welcomeMessage` is dropped on import")
        if "guidingQuestions" in cfg and "presetQuestions" not in cfg:
            rep.warn("AGENT_PRESET_FIELD", "$.guidingQuestions",
                     "use `presetQuestions` for the suggested questions; `guidingQuestions` is dropped on import")
    return bot_type


# --------------------------- L1/L2 Workflow ---------------------------

def check_workflow_graph(workflow, rep, base_path, inner=False):
    if not isinstance(workflow, dict):
        rep.err("WF_MISSING", base_path, "Missing workflow object")
        return
    nodes = workflow.get("workflowNodes") or []
    edges = workflow.get("workflowEdges") or []
    if not nodes:
        rep.err("WF_NO_NODES", base_path + ".workflowNodes", "The workflow must have at least one node")
        return

    ids = []
    names = []
    id_set = set()
    type_by_id = {}
    for i, node in enumerate(nodes):
        np = f"{base_path}.workflowNodes[{i}]"
        if not isinstance(node, dict):
            rep.err("WF_NODE_OBJ", np, "A node must be an object")
            continue
        nid = node.get("id")
        ntype = node.get("type")
        if _is_blank(nid):
            rep.err("WF_NODE_ID", np + ".id", "Node id cannot be empty")
        else:
            if nid in id_set:
                rep.err("WF_NODE_ID_DUP", np + ".id", f"Duplicate node id: {nid}")
            id_set.add(nid)
            ids.append(nid)
            type_by_id[nid] = ntype
        if _is_blank(ntype):
            rep.err("WF_NODE_TYPE", np + ".type", "Node type cannot be empty")
        elif ntype not in WORKFLOW_NODE_TYPES:
            rep.err("WF_NODE_TYPE_INVALID", np + ".type",
                    f"Invalid node type: {ntype}",
                    "Use a WorkflowNodeType value: " + ", ".join(sorted(WORKFLOW_NODE_TYPES)))
        name = node.get("name")
        if _is_blank(name):
            rep.err("WF_NODE_NAME", np + ".name", "Node name cannot be empty")
        elif name in names:
            rep.err("WF_NODE_NAME_DUP", np + ".name", f"Duplicate node name: {name}")
        else:
            names.append(name)
        if node.get("x") is None or node.get("y") is None:
            rep.err("WF_NODE_XY", np, "Node is missing x/y coordinates (the backend import will reject it)", "Set x/y for every node")
        # node parameters
        _check_node_param(node, np, rep)

    # START/END count
    starts = [n for n in nodes if isinstance(n, dict) and n.get("type") == "START"]
    ends = [n for n in nodes if isinstance(n, dict) and n.get("type") == "END"]
    if len(starts) != 1:
        rep.err("WF_START_COUNT", base_path, f"There must be exactly one START node (currently {len(starts)})")
    if not inner and len(ends) != 1:
        rep.err("WF_END_COUNT", base_path, f"There must be exactly one END node (currently {len(ends)})")

    # edge validation
    out_deg, in_deg = {}, {}
    edge_ids = set()
    adj = {}
    out_handles = {}   # nodeId -> set of sourceHandle values on its outgoing edges
    for j, edge in enumerate(edges):
        ep = f"{base_path}.workflowEdges[{j}]"
        if not isinstance(edge, dict):
            rep.err("WF_EDGE_OBJ", ep, "An edge must be an object")
            continue
        eid = edge.get("id")
        if _is_blank(eid):
            rep.err("WF_EDGE_ID", ep + ".id", "Edge id cannot be empty")
        elif eid in edge_ids:
            rep.err("WF_EDGE_ID_DUP", ep + ".id", f"Duplicate edge id: {eid}")
        else:
            edge_ids.add(eid)
        src = edge.get("sourceNodeID")
        tgt = edge.get("targetNodeID")
        for fld in ("sourceNodeID", "targetNodeID", "sourceHandle", "targetHandle"):
            if _is_blank(edge.get(fld)):
                rep.err("WF_EDGE_FIELD", f"{ep}.{fld}", f"Edge {fld} cannot be empty")
        if not _is_blank(src) and src not in id_set:
            rep.err("WF_EDGE_SRC", ep + ".sourceNodeID", f"The edge's source node does not exist: {src}")
        if not _is_blank(tgt) and tgt not in id_set:
            rep.err("WF_EDGE_TGT", ep + ".targetNodeID", f"The edge's target node does not exist: {tgt}")
        if not _is_blank(src) and src == tgt:
            rep.err("WF_EDGE_SELF", ep, f"Self-loops are not allowed: {eid}")
        if not _is_blank(src) and not _is_blank(tgt) and src in id_set and tgt in id_set:
            out_deg[src] = out_deg.get(src, 0) + 1
            in_deg[tgt] = in_deg.get(tgt, 0) + 1
            adj.setdefault(src, []).append(tgt)
            if not _is_blank(edge.get("sourceHandle")):
                out_handles.setdefault(src, set()).add(edge.get("sourceHandle"))

    # connectivity / terminal rules
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid, ntype = n.get("id"), n.get("type")
        if _is_blank(nid):
            continue
        name = n.get("name", nid)
        if ntype == "START":
            if in_deg.get(nid, 0) > 0:
                rep.err("WF_START_IN", base_path, f"START should have no inbound edge: {name}")
            if out_deg.get(nid, 0) == 0:
                rep.err("WF_START_OUT", base_path, f"START must have an outbound edge: {name}")
        elif ntype == "END":
            if out_deg.get(nid, 0) > 0:
                rep.err("WF_END_OUT", base_path, f"END should have no outbound edge: {name}")
            if in_deg.get(nid, 0) == 0:
                rep.err("WF_END_IN", base_path, f"END must have an inbound edge: {name}")
        elif ntype == "COMMENT":
            if in_deg.get(nid, 0) or out_deg.get(nid, 0):
                rep.err("WF_COMMENT_EDGE", base_path, f"A COMMENT node should have no edges at all: {name}")
        else:
            if in_deg.get(nid, 0) == 0:
                rep.err("WF_NODE_NO_IN", base_path, f"Node is missing an inbound edge: {name}")
            if out_deg.get(nid, 0) == 0 and ntype not in {"BREAK", "CONTINUE", "NEXT_LOOP"}:
                rep.err("WF_NODE_NO_OUT", base_path, f"Node is missing an outbound edge: {name}")
        # CONDITION/INTENT: EVERY branch/intent sourceHandle must have a connected edge
        # (backend WorkflowRuntimeChecker: "must have all branches/intents connected").
        if ntype == "CONDITION":
            handles = {b.get("sourceHandle") for b in
                       ((n.get("conditionParam") or {}).get("conditionBranches") or [])
                       if isinstance(b, dict) and b.get("sourceHandle")}
            missing = handles - out_handles.get(nid, set())
            if missing:
                rep.err("WF_COND_NOT_CONNECTED", base_path,
                        f"CONDITION '{name}' has branch(es) with no outgoing edge: {sorted(missing)} "
                        "— every conditionBranches[].sourceHandle needs a matching edge "
                        "(edge sourceHandle == branch sourceHandle)")
        elif ntype == "INTENT":
            handles = {it.get("sourceHandle") for it in
                       ((n.get("intentParam") or {}).get("intents") or [])
                       if isinstance(it, dict) and it.get("sourceHandle")}
            missing = handles - out_handles.get(nid, set())
            if missing:
                rep.err("WF_INTENT_NOT_CONNECTED", base_path,
                        f"INTENT '{name}' has intent(s) with no outgoing edge: {sorted(missing)} "
                        "— every intents[].sourceHandle needs a matching edge")

    # DAG detection
    if _has_cycle(id_set, adj):
        rep.err("WF_CYCLE", base_path, "The workflow has a cycle (it must be a directed acyclic graph, DAG)")

    # recurse into subworkflows
    for i, node in enumerate(nodes):
        if isinstance(node, dict) and node.get("type") in {"LOOP", "BATCH"}:
            sub = node.get("subWorkflow")
            if not isinstance(sub, dict):
                rep.err("WF_SUBWORKFLOW", f"{base_path}.workflowNodes[{i}].subWorkflow",
                        f"A {node.get('type')} node must contain a subWorkflow")
            else:
                check_workflow_graph(sub, rep, f"{base_path}.workflowNodes[{i}].subWorkflow", inner=True)


_VAR_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_INTERNAL_HOST_RE = re.compile(
    r"^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|169\.254\.\d+\.\d+|\[?::1\]?)$", re.IGNORECASE)


def _url_host(url):
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://([^/:?#]+)", str(url or ""))
    return m.group(1) if m else ""


def _check_node_param(node, np, rep):
    """Per-node parameter checks, mirroring backend WorkflowNodeChecker."""
    ntype = node.get("type")
    required = NODE_REQUIRED_PARAM.get(ntype)
    # END is exempt: inner LOOP/BATCH sub-workflow END nodes legitimately carry a null
    # endParam in real exports (only the top-level END needs an output config).
    if required and node.get(required) is None and ntype != "END":
        rep.err("WF_PARAM_MISSING", f"{np}.{required}", f"{ntype} node is missing {required}")
        return
    if ntype == "HTTP":
        http = node.get("httpParam") or {}
        req = http.get("request") or {}
        url = req.get("url")
        if _is_blank(url):
            rep.err("WF_HTTP_URL", f"{np}.httpParam.request.url", "HTTP node is missing url")
        elif _INTERNAL_HOST_RE.match(_url_host(url)):
            rep.err("WF_HTTP_INTERNAL_IP", f"{np}.httpParam.request.url",
                    f"HTTP node URL cannot use an internal/loopback host: {url}",
                    "Use a public URL; intranet/loopback addresses are rejected on non-OP deployments")
    elif ntype == "CODE":
        code = node.get("codeParam") or {}
        if _is_blank(code.get("code")):
            rep.err("WF_CODE_EMPTY", f"{np}.codeParam.code", "CODE node code cannot be empty")
    elif ntype == "CONDITION":
        cond = node.get("conditionParam") or {}
        branches = cond.get("conditionBranches") or []
        if not branches:
            rep.err("WF_COND_BRANCHES", f"{np}.conditionParam.conditionBranches",
                    "CONDITION must have conditionBranches")
        else:
            elses = [b for b in branches if isinstance(b, dict) and b.get("type") == "ELSE"]
            if len(elses) != 1:
                rep.err("WF_COND_ELSE", f"{np}.conditionParam", f"CONDITION must have exactly one ELSE branch (currently {len(elses)})")
    elif ntype == "INTENT":
        intent = node.get("intentParam") or {}
        if not (intent.get("intents") or []):
            rep.err("WF_INTENT_EMPTY", f"{np}.intentParam.intents", "INTENT must have intents")
    elif ntype == "DATABASE":
        db = node.get("databaseParam") or {}
        if _is_blank(db.get("sqlQuery")):
            rep.err("WF_DB_SQL", f"{np}.databaseParam.sqlQuery", "DATABASE node is missing sqlQuery")
    elif ntype == "VARIABLE_AGGREGATE":
        agg = node.get("variableAggregateParam") or {}
        if agg.get("strategy") != "FIRST_NON_NULL":
            rep.err("WF_AGG_STRATEGY", f"{np}.variableAggregateParam.strategy",
                    f"VARIABLE_AGGREGATE only supports FIRST_NON_NULL (got {agg.get('strategy')!r})")
        groups = agg.get("groups") or []
        if not groups:
            rep.err("WF_AGG_NO_GROUP", f"{np}.variableAggregateParam.groups",
                    "VARIABLE_AGGREGATE must have at least 1 group")
        elif len(groups) > 20:
            rep.err("WF_AGG_GROUPS", f"{np}.variableAggregateParam.groups",
                    f"too many groups ({len(groups)}; max 20)")
        for gi, g in enumerate(groups):
            if not isinstance(g, dict):
                continue
            gp = f"{np}.variableAggregateParam.groups[{gi}]"
            gname, gtype = g.get("groupName"), g.get("groupType")
            if not (gname and _VAR_NAME_RE.match(str(gname))):
                rep.err("WF_AGG_GROUP_NAME", gp + ".groupName",
                        f"group name {gname!r} must match ^[a-zA-Z_][a-zA-Z0-9_]*$")
            if gtype is None:
                rep.err("WF_AGG_GROUP_TYPE", gp + ".groupType", "group type is required")
            gvars = g.get("variables") or []
            if not gvars:
                rep.err("WF_AGG_GROUP_VARS", gp + ".variables", "each group needs at least 1 variable")
            elif len(gvars) > 10:
                rep.err("WF_AGG_GROUP_VARS", gp + ".variables", f"too many variables ({len(gvars)}; max 10)")
            for v in gvars:
                if isinstance(v, dict) and gtype is not None and v.get("type") != gtype:
                    rep.err("WF_AGG_VAR_TYPE", gp + ".variables",
                            f"variable {v.get('name')!r} type {v.get('type')!r} must equal group type {gtype!r}")
    elif ntype in {"LOOP", "BATCH"}:
        param = node.get("loopParam" if ntype == "LOOP" else "batchParam") or {}
        seen = set()
        srcs = (param.get("intermediateVariables") or []) if ntype == "LOOP" else []
        for v in list(srcs) + list(param.get("inputArrays") or []):
            if isinstance(v, dict):
                nm = v.get("name")
                if nm == "index":
                    rep.err("WF_LOOP_INDEX_NAME", f"{np}.{ntype.lower()}Param",
                            f"{ntype} variable name cannot be 'index' (reserved)")
                elif nm in seen:
                    rep.err("WF_LOOP_DUP_NAME", f"{np}.{ntype.lower()}Param",
                            f"duplicate {ntype} variable name {nm!r}")
                else:
                    seen.add(nm)
        # (subWorkflow presence + recursion handled at graph level in check_workflow_graph)
    elif ntype == "SET_INTERMEDIATE_VARIABLE":
        sp = node.get("setIntermediateVariableParam") or {}
        assigns = sp.get("assignments") or []
        if not assigns:
            rep.err("WF_SIV_NO_ASSIGN", f"{np}.setIntermediateVariableParam.assignments",
                    "SET_INTERMEDIATE_VARIABLE must have at least one assignment")
        for ai, a in enumerate(assigns):
            if isinstance(a, dict) and a.get("leftValue") is None:
                rep.err("WF_SIV_LEFT", f"{np}.setIntermediateVariableParam.assignments[{ai}].leftValue",
                        "assignment leftValue cannot be null")


def _has_cycle(id_set, adj):
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in id_set}

    def dfs(u):
        color[u] = GRAY
        for v in adj.get(u, []):
            if color.get(v) == GRAY:
                return True
            if color.get(v) == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    for nid in id_set:
        if color[nid] == WHITE and dfs(nid):
            return True
    return False


# --------------------------- L4 FlowAgent ---------------------------

# A platform variable reference is `{{name}}` (double braces). A single-braced
# `{name}` is almost always the result of running str.format()/f-string over a prompt
# that contained `{{...}}` — .format() COLLAPSES `{{x}}` to `{x}`, after which GPTBots
# no longer recognizes the variable. The lookbehind/lookahead skip correctly-doubled
# braces and match only the broken single-brace form.
_SINGLE_BRACE_VAR = re.compile(r'(?<!\{)\{([A-Za-z_]\w*)\}(?!\})')


def _check_single_brace_vars(text, path, rep):
    if not isinstance(text, str):
        return
    hits = _SINGLE_BRACE_VAR.findall(text)
    if hits:
        uniq = sorted(set(hits))
        rep.warn("MSG_SINGLE_BRACE_VAR", path,
                 f"single-brace variable(s) {', '.join('{'+h+'}' for h in uniq)} — platform "
                 f"variables need DOUBLE braces ({{{{{uniq[0]}}}}}); a single brace usually means "
                 f"str.format()/f-string collapsed the {{{{...}}}} (use .replace() for substitution)")


def _check_component_enums(c, cp, rep):
    """Validate enum-valued fields inside one flow component (mirrors backend strict parse)."""
    _check_enum(c.get("reasoningEffort"), REASONING_EFFORTS, "COMP_ENUM_REASONING_EFFORT", cp + ".reasoningEffort", rep, "reasoningEffort")
    _check_enum(c.get("showReasoning"), REASONING_SHOW, "COMP_ENUM_SHOW_REASONING", cp + ".showReasoning", rep, "showReasoning")
    _check_enum(c.get("dataSourceShowType"), DATA_SOURCE_SHOW, "COMP_ENUM_DATA_SOURCE_SHOW", cp + ".dataSourceShowType", rep, "dataSourceShowType")
    _check_enum(c.get("customKnowledgeType"), CUSTOM_KNOWLEDGE_TYPES, "COMP_ENUM_CUSTOM_KNOWLEDGE", cp + ".customKnowledgeType", rep, "customKnowledgeType")
    _check_enum(c.get("responseFormat"), RESPONSE_FORMATS, "COMP_ENUM_RESPONSE_FORMAT", cp + ".responseFormat", rep, "responseFormat")
    _check_enum(c.get("contentType"), FLOW_CONTENT_TYPES, "COMP_ENUM_CONTENT_TYPE", cp + ".contentType", rep, "contentType")
    _check_list_enum(c.get("multiResponseTypes"), MULTI_MODAL_DATA_TYPES, "COMP_ENUM_MULTI_RESPONSE", cp + ".multiResponseTypes", rep, "multiResponseTypes")
    # Message/Predefine reply text (their content field) — also variable-scanned.
    _check_single_brace_vars(c.get("content"), cp + ".content", rep)
    # prompt message lists (LLM / Branch / Condition / ChatGather / FormGather)
    for fld in ("messages", "datasetMessages"):
        msgs = c.get(fld)
        if isinstance(msgs, list):
            for i, m in enumerate(msgs):
                if isinstance(m, dict):
                    mpath = f"{cp}.{fld}[{i}]"
                    _check_enum(m.get("type"), PROMPT_MESSAGE_TYPES, "COMP_ENUM_MESSAGE_TYPE", mpath + ".type", rep, "message type")
                    _check_single_brace_vars(m.get("text"), mpath + ".text", rep)
                    # The importer rebuilds the prompt editor ONLY from the canonical
                    # PromptMessage object {lineId,type,text,ids,upstream,children,datasetType}
                    # with the body in `text`. A message that carries the body in stray keys
                    # (content/value/prompt) — what a hand-rolled generator often emits — is
                    # NOT read, so the node imports with a BLANK Identity/System prompt even
                    # though those keys look populated. Flag any stray body key.
                    stray = [k for k in ("content", "value", "prompt") if k in m]
                    if stray:
                        body_in_stray = any(m.get(k) and str(m[k]).strip() for k in stray)
                        if body_in_stray and not (m.get("text") and str(m["text"]).strip()):
                            rep.err("MSG_NONCANONICAL", mpath,
                                    f"prompt message body is in {stray} but not in `text` — the importer "
                                    "reads only `text`, so this imports as a BLANK prompt",
                                    "Put the body in `text` and use the canonical PromptMessage "
                                    "shape {lineId,type,text,ids,upstream,children,datasetType} (builder _msg)")
                        else:
                            rep.warn("MSG_NONCANONICAL", mpath,
                                     f"prompt message has non-schema key(s) {stray}; real exports use only "
                                     "`text`. Stray keys signal a non-canonical message that may import blank",
                                     "Emit the canonical PromptMessage object (builder _msg/role)")
                    if m.get("type") == "Role" and not (m.get("text") and str(m["text"]).strip()):
                        rep.err("MSG_ROLE_EMPTY", mpath,
                                f"the Role (identity prompt) of {c.get('type')} #{c.get('id')} has no `text` "
                                "— the node imports with no instructions (the prompt body must be in `text`)",
                                "Provide a non-empty identity prompt in the Role message's `text`")
    # gather fields (ChatGather / FormGather)
    gfs = c.get("gatherFields")
    if isinstance(gfs, list):
        for i, g in enumerate(gfs):
            if isinstance(g, dict):
                gp = f"{cp}.gatherFields[{i}]"
                # The backend reads the field name from `fieldName` (label from `showName`).
                # name/variableName/key are silently dropped on import → the platform then
                # assigns random default names (age/user_birthday/…). Catch that here.
                fname = g.get("fieldName")
                if _is_blank(fname):
                    hint = next((k for k in ("name", "variableName", "key") if g.get(k)), None)
                    rep.err("GATHER_FIELD_NAME", gp + ".fieldName",
                            "gather field is missing `fieldName`" +
                            (f" (found '{hint}', which the import drops → random default name)" if hint else ""),
                            "Set fieldName (+ showName for the label); use gather_fields() in the builder")
                elif not re.match(r"^[a-z0-9_]+$", str(fname)):
                    rep.err("GATHER_FIELD_NAME_FORMAT", gp + ".fieldName",
                            f"fieldName {fname!r} must contain only lowercase letters, digits, "
                            "and underscores ([a-z0-9_]) — it becomes a variable key",
                            "Rename it to e.g. user_name")
                _check_enum(g.get("gatherType"), GATHER_FIELD_TYPES, "COMP_ENUM_GATHER_TYPE", gp + ".gatherType", rep, "gatherType")
                _check_enum(g.get("valueType"), GATHER_VALUE_TYPES, "COMP_ENUM_GATHER_VALUE_TYPE", gp + ".valueType", rep, "valueType")
                _check_enum(g.get("optionFieldType"), OPTION_FIELD_TYPES, "COMP_ENUM_OPTION_FIELD_TYPE", gp + ".optionFieldType", rep, "optionFieldType")
    gc = c.get("gatherControl")
    if isinstance(gc, dict):
        _check_enum(gc.get("formGatherType"), FORM_GATHER_TYPES, "COMP_ENUM_FORM_GATHER_TYPE", cp + ".gatherControl.formGatherType", rep, "formGatherType")
    # variable assignment (Variable)
    vscs = c.get("variableSetValueConfigs")
    if isinstance(vscs, list):
        for i, v in enumerate(vscs):
            if isinstance(v, dict):
                vp = f"{cp}.variableSetValueConfigs[{i}]"
                # Real export shape: {variableName, operation, value}. `operation` is
                # capitalized (Cover/Clear/Append). Validate it when present.
                _check_enum(v.get("operation"), VARIABLE_OPERATIONS, "COMP_ENUM_VARIABLE_OPERATION", vp + ".operation", rep, "operation")
                if _is_blank(v.get("variableName")):
                    rep.err("COMP_VARIABLE_NAME", vp + ".variableName",
                            "variableSetValueConfigs entry is missing variableName",
                            "Each assignment needs {variableName, operation, value}")
                # legacy fields, still validated if a caller emits them
                _check_enum(v.get("variableType"), VARIABLE_TYPES, "COMP_ENUM_VARIABLE_TYPE", vp + ".variableType", rep, "variableType")
                _check_enum(v.get("variableOperateType"), VARIABLE_OPERATE_TYPES, "COMP_ENUM_VARIABLE_OPERATE_TYPE", vp + ".variableOperateType", rep, "variableOperateType")
    # rule groups (Regular / Bool)
    rgs = c.get("regularGroups")
    if isinstance(rgs, list):
        for i, g in enumerate(rgs):
            if isinstance(g, dict):
                rp = f"{cp}.regularGroups[{i}]"
                _check_enum(g.get("combine"), COMBINE_TYPES, "COMP_ENUM_COMBINE", rp + ".combine", rep, "combine")
                items = g.get("items")
                if isinstance(items, list):
                    for j, it in enumerate(items):
                        if isinstance(it, dict):
                            ip = f"{rp}.items[{j}]"
                            _check_enum(it.get("category"), REGULAR_CATEGORIES, "COMP_ENUM_REGULAR_CATEGORY", ip + ".category", rep, "category")
                            _check_enum(it.get("type"), PROPERTY_TYPES, "COMP_ENUM_PROPERTY_TYPE", ip + ".type", rep, "property type")
    # multimodal LLM file input
    mm = c.get("multiModalLlmInput")
    if isinstance(mm, dict):
        _check_enum(mm.get("fileMode"), FILE_MODES, "COMP_ENUM_FILE_MODE", cp + ".multiModalLlmInput.fileMode", rep, "fileMode")


def _check_component_edges(c, cp, comp_type_by_id, rep):
    """Validate connection-handle integrity for one component's nextComponents.

    The canvas resolves an edge by its `sourceHandle`/`targetHandle` id; if the embedded
    component id or the handle key is wrong, the port is not found and the edge endpoint
    falls back to the node origin → a distorted/misrouted line. These checks catch that
    offline. Handle id format: `{side}{componentId}-{key}[_{suffix}]`.
    """
    owner_id = c.get("id")
    owner_type = c.get("type")
    src_key = HANDLE_SOURCE_KEY.get(owner_type)
    # A classifier must wire its built-in Other fallback (branch_other), or unmatched
    # messages dead-end. Detect it across this component's edges.
    if owner_type == "Branch":
        has_other = any(isinstance(nx, dict) and str(nx.get("sourceHandle", "")).endswith("-branch_other")
                        for nx in (c.get("nextComponents") or []))
        if not has_other:
            rep.err("BRANCH_NO_OTHER", cp + ".nextComponents",
                    f"Classifier #{owner_id} has no branch_other (built-in Other) edge — "
                    "unmatched messages would dead-end",
                    'Add the Other fallback edge with name="_other", condition="" '
                    "(use branch_other() in the builder)")
    # A Condition node carries its IF text on the conditions_true edge's `condition`
    # (name="_true"); the conditions_false edge is name="_false", condition="". An
    # empty true-edge condition = an empty IF box on the canvas.
    if owner_type == "Condition":
        edges = [nx for nx in (c.get("nextComponents") or []) if isinstance(nx, dict)]
        true_e = next((e for e in edges if str(e.get("sourceHandle", "")).endswith("-conditions_true")), None)
        false_e = next((e for e in edges if str(e.get("sourceHandle", "")).endswith("-conditions_false")), None)
        if true_e is None:
            rep.err("CONDITION_NO_TRUE", cp + ".nextComponents",
                    f"Condition #{owner_id} has no conditions_true edge",
                    "Wire both outlets with condition_edges() in the builder")
        else:
            if not str(true_e.get("condition") or "").strip():
                rep.err("CONDITION_IF_EMPTY", cp + ".nextComponents",
                        f"Condition #{owner_id} conditions_true edge has an empty `condition` — "
                        "the IF condition text must live here (the canvas IF box reads it)",
                        'Put the IF text on the conditions_true edge (condition_edges(if_text=...))')
            if true_e.get("name") != "_true":
                rep.err("CONDITION_EDGE_NAME", cp + ".nextComponents",
                        f"Condition #{owner_id} conditions_true edge name must be \"_true\" "
                        f"(got {true_e.get('name')!r})", 'Set name="_true"')
        if false_e is not None and false_e.get("name") != "_false":
            rep.err("CONDITION_EDGE_NAME", cp + ".nextComponents",
                    f"Condition #{owner_id} conditions_false edge name must be \"_false\" "
                    f"(got {false_e.get('name')!r})", 'Set name="_false"')
    # A Variable (assignment) node's success outlet is `variable_true` (edge
    # name="_true") — NOT the bare `variable` handle. The platform's "assignment
    # successful" port is keyed `variable_true`, so a plain `right{id}-variable`
    # edge does not anchor to that port: the canvas draws a detached/floating line
    # and the port greys out (identical failure to a Condition true-edge missing
    # its `_true`). The `_parse_handle` key drops the `_true`/`_exception` suffix,
    # so EDGE_SOURCE_KEY cannot catch this — check the raw suffix here.
    if owner_type == "Variable":
        edges = [nx for nx in (c.get("nextComponents") or []) if isinstance(nx, dict)]
        for nx in edges:
            sh = str(nx.get("sourceHandle") or "")
            # the bare success handle: ends with "-variable" and carries no suffix
            if sh == f"right{owner_id}-variable" or (sh.endswith("-variable") and "_" not in sh.rsplit("-", 1)[-1]):
                rep.err("VAR_SUCCESS_HANDLE", cp + ".nextComponents",
                        f"Variable #{owner_id} success edge uses the bare handle "
                        f"'{sh}' — the 'assignment successful' port is keyed "
                        "'variable_true', so this edge does not anchor to it and the "
                        "canvas draws a floating/greyed line",
                        f"Use sourceHandle 'right{owner_id}-variable_true' with name "
                        '"_true" (connect(var, dst) / connect(var, dst, suffix="true") '
                        "in the builder now emits this automatically)")
            elif sh.endswith("-variable_true") and nx.get("name") != "_true":
                rep.err("VAR_SUCCESS_HANDLE", cp + ".nextComponents",
                        f"Variable #{owner_id} variable_true edge name must be "
                        f"\"_true\" (got {nx.get('name')!r})", 'Set name="_true"')
    for k, nx in enumerate(c.get("nextComponents") or []):
        if not isinstance(nx, dict):
            continue
        ep = f"{cp}.nextComponents[{k}]"
        sh, th, nid = nx.get("sourceHandle"), nx.get("targetHandle"), nx.get("nextComponentId")
        # Backend BotFlowNext parses `id`, `nextComponentId`, `sort` as Integer with strict
        # Jackson typing (same as `exportTime`): ANY string — "e1", "vueflow__edge-...", even a
        # quoted number "1" — fails import with 'value X is not allowed for field id'.
        # (FAIL_ON_UNKNOWN_PROPERTIES=false: extra fields are tolerated; only wrong TYPES kill
        # the import.) Use unique integers for edge ids; 100000+seq avoids colliding with
        # component ids; `sort` may equal `id`.
        eid = nx.get("id")
        if eid is not None and (isinstance(eid, bool) or not isinstance(eid, int)):
            rep.err("EDGE_ID_NOT_LONG", ep + ".id",
                    f"Edge id must be a bare integer (backend Integer), got {type(eid).__name__}: {eid!r}",
                    "Use a unique integer, e.g. 100000+seq (won't collide with component ids)")
        for fld in ("nextComponentId", "sort"):
            v = nx.get(fld)
            if v is not None and (isinstance(v, bool) or not isinstance(v, int)):
                rep.err("EDGE_INT_FIELD", f"{ep}.{fld}",
                        f"{fld} must be a bare integer (backend Integer), got {type(v).__name__}: {v!r}",
                        f'Write "{fld}": 2, not "{fld}": "2"')
        if sh:
            ps = _parse_handle(sh)
            if ps is None or ps[0] != "right":
                rep.err("EDGE_SOURCE_FORMAT", ep + ".sourceHandle",
                        f"Malformed source handle: {sh}", "Expected right{componentId}-{key}[_suffix]")
            else:
                _, sid, skey = ps
                if owner_id is not None and sid != str(owner_id):
                    rep.err("EDGE_SOURCE_ID_MISMATCH", ep + ".sourceHandle",
                            f"sourceHandle id {sid} != owning component id {owner_id} (the canvas will draw a distorted edge)",
                            f"Use right{owner_id}-...")
                if src_key is not None and skey != src_key:
                    rep.err("EDGE_SOURCE_KEY", ep + ".sourceHandle",
                            f"sourceHandle key '{skey}' does not match a {owner_type} component (expected '{src_key}')",
                            f"Use right{owner_id}-{src_key}...")
                # Classifier (Branch) rule branches: the handle suffix is a sequential
                # number (branch_1, branch_2, …) and the RULE lives in the edge's
                # `condition` as natural-language text. A numeric/empty condition means the
                # rule was wrongly stored as an id (the UI then shows the id, not the rule).
                if owner_type == "Branch":
                    suffix = sh.split("-", 1)[1] if "-" in sh else ""
                    suffix = suffix[len(skey) + 1:] if suffix.startswith(skey + "_") else ""
                    if suffix == "exception":
                        # A wired classifier exception branch IS supported: real
                        # platform exports contain right{id}-branch_exception (name
                        # "_exception") routing to a fallback node, structurally
                        # identical to the LLM/Condition wired exception, with the
                        # classifier's exceptionSwitch=True. It is only inconsistent
                        # when the edge exists but the exception mechanism is off.
                        if not c.get("exceptionSwitch"):
                            rep.warn("BRANCH_EXCEPTION_EDGE", ep + ".sourceHandle",
                                     "Classifier has a wired branch_exception edge but "
                                     "exceptionSwitch is not enabled — the exception "
                                     "branch only fires when the exception mechanism is "
                                     "on. Set exceptionSwitch=true, or remove the edge "
                                     "if you don't want a wired exception fallback")
                    elif suffix == "other":
                        # The built-in Other edge must be name="_other" + condition=""
                        # (empty string, not null). name=null makes the platform render
                        # branch_other as an editable BLANK category instead of mapping
                        # it to the built-in Other.
                        if nx.get("name") != "_other":
                            rep.err("BRANCH_OTHER_NAME", ep + ".name",
                                    f"branch_other edge name must be \"_other\" (got {nx.get('name')!r}) "
                                    "— otherwise the platform renders it as an editable blank "
                                    "category instead of the built-in Other",
                                    'Set name="_other" and condition="" (use branch_other() in the builder)')
                    elif suffix:
                        cond = nx.get("condition")
                        cond_s = "" if cond is None else str(cond).strip()
                        if not cond_s or cond_s.isdigit():
                            rep.err("BRANCH_RULE_IS_ID", ep + ".condition",
                                    f"Classifier branch '{nx.get('name') or suffix}' has "
                                    f"{'an empty' if not cond_s else 'a numeric-id'} condition "
                                    f"({cond!r}) — the routing rule must be natural-language "
                                    "text here, not an id",
                                    "Put the branch's routing rule text in `condition` "
                                    "(use branch_edge(rule=...) in the builder)")
        if nid is not None:
            if not th:
                rep.err("EDGE_TARGET_MISSING", ep + ".targetHandle",
                        f"nextComponentId={nid} but targetHandle is empty (the canvas will draw a distorted edge)",
                        "Set targetHandle to left{nextComponentId}-{key}")
            else:
                pt = _parse_handle(th)
                if pt is None or pt[0] != "left":
                    rep.err("EDGE_TARGET_FORMAT", ep + ".targetHandle",
                            f"Malformed target handle: {th}", "Expected left{componentId}-{key}")
                else:
                    _, tid, tkey = pt
                    if tid != str(nid):
                        rep.err("EDGE_TARGET_ID_MISMATCH", ep + ".targetHandle",
                                f"targetHandle id {tid} != nextComponentId {nid} (the canvas will draw a distorted edge)",
                                f"Use left{nid}-...")
                    exp_tkey = HANDLE_TARGET_KEY.get(comp_type_by_id.get(nid))
                    if exp_tkey is not None and tkey != exp_tkey:
                        rep.err("EDGE_TARGET_KEY", ep + ".targetHandle",
                                f"targetHandle key '{tkey}' does not match the target {comp_type_by_id.get(nid)} component (expected '{exp_tkey}')",
                                f"Use left{nid}-{exp_tkey}")
        elif th:
            rep.err("EDGE_TARGET_ORPHAN", ep + ".targetHandle",
                    f"targetHandle '{th}' is set but nextComponentId is empty",
                    "Set nextComponentId, or remove the targetHandle")


def check_flow(flow_rule, rep):
    if not isinstance(flow_rule, dict):
        rep.err("FLOW_MISSING", "$.flowRule", "Missing flowRule")
        return
    comps = flow_rule.get("components") or []
    if not comps:
        rep.err("FLOW_NO_COMPONENTS", "$.flowRule.components", "A FlowAgent must have at least one component")
        return
    inputs = [c for c in comps if isinstance(c, dict) and c.get("type") == "Input"]
    outputs = [c for c in comps if isinstance(c, dict) and c.get("type") == "Output"]
    if len(inputs) != 1:
        rep.err("FLOW_INPUT", "$.flowRule", f"There must be exactly one Input component (currently {len(inputs)})")
    if len(outputs) != 1:
        rep.err("FLOW_OUTPUT", "$.flowRule", f"There must be exactly one Output component (currently {len(outputs)})")
    id_set = set()
    for i, c in enumerate(comps):
        cp = f"$.flowRule.components[{i}]"
        if not isinstance(c, dict):
            rep.err("FLOW_COMP_OBJ", cp, "A component must be an object")
            continue
        cid = c.get("id")
        if cid is None:
            rep.err("FLOW_COMP_ID", cp + ".id", "Component id cannot be empty")
        elif isinstance(cid, bool) or not isinstance(cid, int):
            # Backend BotFlowComponent.id is Integer (strict Jackson parsing): "1" (quoted) or
            # "vueflow__node-..." fails import with 'value X is not allowed for field id'.
            rep.err("FLOW_COMP_ID_NOT_INT", cp + ".id",
                    f"Component id must be a bare integer (backend Integer), got {type(cid).__name__}: {cid!r}",
                    'Write "id": 1, not "id": "1" or a vueflow__node-... string')
        elif cid in id_set:
            rep.err("FLOW_COMP_ID_DUP", cp + ".id", f"Duplicate component id: {cid}")
        else:
            id_set.add(cid)
        # x / y are backend Integer fields — same strict parsing
        for fld in ("x", "y"):
            v = c.get(fld)
            if v is not None and (isinstance(v, bool) or not isinstance(v, int)):
                rep.err("FLOW_COMP_XY_NOT_INT", f"{cp}.{fld}",
                        f"{fld} must be a bare integer (backend Integer), got {type(v).__name__}: {v!r}",
                        f'Write "{fld}": 420, not a quoted number or float')
        if _is_blank(c.get("type")):
            rep.err("FLOW_COMP_TYPE", cp + ".type", "Component type cannot be empty")
        elif c.get("type") not in FLOW_COMPONENT_TYPES:
            rep.err("FLOW_COMP_TYPE_INVALID", cp + ".type",
                    f"Invalid component type: {c.get('type')}",
                    "Use a FlowComponentType value: " + ", ".join(sorted(FLOW_COMPONENT_TYPES)))
    # component id -> type (for target-handle key validation)
    comp_type_by_id = {c.get("id"): c.get("type") for c in comps if isinstance(c, dict)}
    # next-target validation + terminal nodes + enum / connection-handle integrity
    edge_id_seen = set()
    edge_sort_seen = set()
    for i, c in enumerate(comps):
        if not isinstance(c, dict):
            continue
        cp = f"$.flowRule.components[{i}]"
        ctype = c.get("type")
        nexts = c.get("nextComponents") or []
        # Fan-out is legal: an output port MAY drive several edges to DIFFERENT targets
        # ("Multi-out / fan-out: each branch (output) can connect to multiple parallel
        # downstream nodes" — Connection rules). So a repeated sourceHandle alone is NOT
        # an error. The genuine import artifact is a *duplicate edge* — the SAME
        # (sourceHandle → target) appearing twice (e.g. an old `Exception`/`name=null`
        # entry plus a new `_exception` one on the same port to the same node). That is
        # dirty data (harmless to the engine — nextComponents is pass-through, no toMap —
        # but it renders a doubled line and can grey the port). Flag only that.
        line_seen = set()
        for k, nx in enumerate(nexts):
            if not isinstance(nx, dict):
                continue
            line = (nx.get("sourceHandle"), nx.get("nextComponentId"))
            if line[0] is not None and line[1] is not None:
                if line in line_seen:
                    rep.err("EDGE_DUP_HANDLE", f"{cp}.nextComponents[{k}]",
                            f"Duplicate edge on component #{c.get('id')}: sourceHandle "
                            f"{line[0]!r} → component {line[1]} appears more than once "
                            "(typical import artifact: an old 'Exception'/name=null edge "
                            "plus a new '_exception' one on the same port to the same "
                            "target). Fan-out to DIFFERENT targets is fine; only the exact "
                            "same handle→target pair repeating is the problem",
                            "Delete the duplicate edge (keep one edge per handle→target pair)")
                line_seen.add(line)
            if nx.get("nextComponentId") is not None \
                    and nx.get("nextComponentId") not in id_set:
                rep.err("FLOW_NEXT_MISSING", f"{cp}.nextComponents[{k}].nextComponentId",
                        f"Points to a non-existent component: {nx.get('nextComponentId')}")
            eid = nx.get("id")
            if isinstance(eid, int) and not isinstance(eid, bool):
                if eid in edge_id_seen:
                    rep.err("EDGE_ID_DUP", f"{cp}.nextComponents[{k}].id",
                            f"Duplicate edge id: {eid}", "Edge ids must be unique, e.g. 100000+seq")
                edge_id_seen.add(eid)
            # `sort` must be globally unique across all edges (real exports set sort == id).
            # A per-node counter (1, 2, …) collides across nodes and makes the canvas
            # mis-render — branch target nodes render greyed/unusable.
            esort = nx.get("sort")
            if isinstance(esort, int) and not isinstance(esort, bool):
                if esort in edge_sort_seen:
                    rep.err("EDGE_SORT_DUP", f"{cp}.nextComponents[{k}].sort",
                            f"Duplicate edge sort: {esort} — sort must be globally unique "
                            "(collisions grey out branch target nodes on the canvas)",
                            "Set sort equal to the edge id (a unique 100000+seq integer)")
                edge_sort_seen.add(esort)
        if ctype in {"Output", "Human"} and nexts:
            rep.warn("FLOW_TERMINAL", cp, f"{ctype} is a terminal node and usually should have no downstream")
        if ctype not in {"Output", "Human", "Message"} and not nexts:
            rep.warn("FLOW_NO_NEXT", cp, f"The {ctype} component has no downstream connection; please confirm whether a branch was missed")
        # A Message (pass-through) component's `content` must be a JSON string keyed by
        # contentType (e.g. '{"Text":"..."}'); a plain string renders an empty message.
        if ctype == "Message" and c.get("content") is not None:
            ct = c.get("contentType") or "Text"
            raw = c.get("content")
            ok = False
            if isinstance(raw, str):
                try:
                    d = json.loads(raw)
                    ok = isinstance(d, dict) and ct in d
                except (ValueError, TypeError):
                    ok = False
            if not ok:
                rep.err("MSG_CONTENT_NOT_JSON", cp + ".content",
                        f"Message #{c.get('id')} content must be a JSON string keyed by "
                        f'contentType, e.g. {{"{ct}":"...text..."}} — a plain string renders empty',
                        "Use message_content(text, content_type) in the builder")
        # LLM-driven nodes need maxRespTokens, or the canvas shows an empty "Maximum Response".
        if ctype in {"LLM", "Branch", "Condition", "ChatGather", "FormGather"}:
            mrt = c.get("maxRespTokens")
            if mrt is None or (isinstance(mrt, str) and not mrt.strip()):
                rep.warn("COMP_MAX_TOKENS_NULL", cp + ".maxRespTokens",
                         f"{ctype} #{c.get('id')} has no maxRespTokens — the canvas shows an "
                         "empty 'Maximum Response'; default it (e.g. 4096)")
        _check_component_enums(c, cp, rep)
        _check_component_edges(c, cp, comp_type_by_id, rep)


# --------------------------- L5 secrets / refs ---------------------------

def check_secrets_and_refs(cfg, rep):
    plugins = cfg.get("plugins") or []
    for i, p in enumerate(plugins):
        if not isinstance(p, dict):
            continue
        for fld in ("authKey", "authSecret", "oAuthId", "oAuthBean", "authProvider"):
            if p.get(fld):
                rep.warn("SEC_PLUGIN", f"$.plugins[{i}].{fld}",
                         f"Plugin credential {fld} should not be present (it is cleared on import)", "Leave it blank and reconfigure on the platform after import")
        if p.get("headers") or p.get("queries"):
            rep.warn("SEC_PLUGIN_HDR", f"$.plugins[{i}]", "Plugin headers/queries are cleared on import")
    if cfg.get("apiSecrets"):
        rep.warn("SEC_API", "$.apiSecrets", "apiSecrets should not be present (it is cleared on import)")
    # numeric ranges
    _range(cfg.get("creativityLevel"), 0.0, 0.95, "$.creativityLevel", rep, exclusive_high=True)
    _range(cfg.get("docCorrelation"), 0.0, 1.0, "$.docCorrelation", rep)
    _range(cfg.get("embeddingRate"), 0.0, 1.0, "$.embeddingRate", rep)


# --------------------------- L6 human handoff config ---------------------------

def check_human_config(cfg, rep):
    """Validate the top-level `humanConfig` enum fields against the backend enums.

    Both QuestionAnswer agents and FlowAgents may carry a `humanConfig`. The backend
    deserializes `manufacturer`/`status` into enums and rejects unknown string values
    during import (InvalidFormatException). Only validate values that are present
    (non-null); the backend does not require them.
    """
    hc = cfg.get("humanConfig")
    if not isinstance(hc, dict):
        return
    manufacturer = hc.get("manufacturer")
    if manufacturer is not None and manufacturer not in HUMAN_MANUFACTURERS:
        rep.err("HUMAN_MANUFACTURER_INVALID", "$.humanConfig.manufacturer",
                f"Invalid human-service manufacturer: {manufacturer}",
                "Use a HumanManufacturerEnum value (not a display name): "
                + ", ".join(sorted(HUMAN_MANUFACTURERS)))
    status = hc.get("status")
    if status is not None and status not in HUMAN_CONFIG_STATUS:
        rep.err("HUMAN_STATUS_INVALID", "$.humanConfig.status",
                f"Invalid humanConfig status: {status}",
                "Use one of: " + ", ".join(sorted(HUMAN_CONFIG_STATUS)))


def _range(v, low, high, path, rep, exclusive_high=False):
    if v is None:
        return
    try:
        f = float(v)
    except (TypeError, ValueError):
        rep.err("VAL_NUM", path, f"{path} must be a number")
        return
    bad = f < low or (f >= high if exclusive_high else f > high)
    if bad:
        bound = f"[{low}, {high})" if exclusive_high else f"[{low}, {high}]"
        rep.err("VAL_RANGE", path, f"{path}={f} is out of range {bound}")


# --------------------------- L7 LoopAgent (clawRule) ---------------------------
# Sources: backend .../bean/entity/ClawFlow.java + ClawFlowComponent.java + ClawFlowNext.java,
#   .../consts/ClawComponentTypes.java, .../helper/ClawDefaultsHelper.java (default topology),
#   .../helper/ClawLoopControlValidator.java (RANGE CHECK RUNS ON THE IMPORT PATH),
#   .../service/exportimport/ClawRuleTransferHelper.java + ImportSecurityScanner.java,
#   engine ailab-claw-engine/.../csagent/botFlowAdapter.ts + types/botFlow.ts,
#   frontend .../features/claw-bot/data/claw-rule-codec.ts

CLAW_CENTER_TYPE = "ClawCenter"
# Contractual ids + order (ClawDefaultsHelper == claw-topology.ts SATELLITES, sort 0..6).
CLAW_SATELLITES = [("keyEvent-1", "ClawKeyEvent"), ("handoff-1", "Human"),
                   ("knowledge-1", "Dataset"), ("skills-1", "ClawSkill"),
                   ("tools-1", "ToolApi"), ("database-1", "ClawDB"),
                   ("subagent-1", "ClawSubAgent")]
CLAW_COMPONENT_TYPES = {"ClawCenter", "ClawKeyEvent", "ClawSkill", "ClawDB", "ClawSubAgent",
                        "ClawModule", "Human", "Dataset", "ToolApi"}
MAX_CLAW_COMPONENTS = 64          # ImportSecurityScanner.MAX_CLAW_COMPONENTS
MAX_CLAW_SKILL_REFS = 10          # claw-rule-codec.ts MAX_CLAW_SKILL_REFS
MAX_PRIVATE_SKILLS = 50           # ImportSecurityScanner.MAX_PRIVATE_SKILLS
CLAW_SKILL_REF_SOURCES = {"SYSTEM", "ORGANIZATION"}
CLAW_SEARCH_MODES = {"mix", "semantics", "keyword"}
CLAW_SEVERITIES = {"low", "normal", "high", "urgent"}
CLAW_MESSAGE_MODES = {"QUEUE", "APPEND"}          # BotMessageModeEnum (LoopAgent only)
# Retired knowledge keys: read-tolerated by the engine, never written by the platform.
CLAW_RETIRED_KNOWLEDGE_KEYS = ("customKnowledgeType", "enhancementMessageSwitch",
                               "docCorrelationSwitch", "noCorrelationResponse")
# Fields the engine does not consume at all - configuring them changes nothing.
CLAW_INERT_KEYEVENT_KEYS = ("titleStrategy", "autoCreateOnSpawn", "autoResolveIdleDays",
                            "slaHighMs", "slaNormalMs", "keyEventTypes", "triggerPrompt")
_HEX24_RE = re.compile(r"^[0-9a-fA-F]{24}$")
_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0$|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2[0-9]|3[01])\.)")


def _public_http_url(url):
    """Return an error string if `url` is not a public http(s) URL, else None.

    Mirrors ImportSecurityScanner.checkUrl: templated ({{var}}) and relative URLs
    are skipped, non-http(s) schemes are rejected, internal/loopback/link-local
    hosts (incl. the 169.254.169.254 cloud-metadata address) are rejected.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    u = url.strip()
    if "{{" in u or "://" not in u:
        return None
    low = u.lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        return "only http/https URLs are allowed"
    host = low.split("://", 1)[1].split("/", 1)[0].split("@")[-1].split(":")[0]
    if _PRIVATE_HOST_RE.match(host) or host.endswith(".local"):
        return "points at an internal/loopback/link-local address (%s)" % host
    return None


def _claw_int_range(value, low, high, path, rep, code, label):
    """Integer range check with the backend's strictness (bools and floats are not ints)."""
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        rep.err(code, path, "%s must be an integer, got %r" % (label, value),
                "Write a bare integer (a float or a quoted number is rejected on import)")
        return
    if value < low or (high is not None and value > high):
        bound = "[%s, %s]" % (low, "inf" if high is None else high)
        rep.err(code, path, "%s=%s is out of range %s" % (label, value, bound),
                "Bring the value inside %s" % bound)


def _claw_find(components, ctype):
    return [c for c in components if isinstance(c, dict) and c.get("type") == ctype]


def _check_claw_center(center, rep):
    base = "$.clawRule.components[center]"
    content = center.get("content")
    if not isinstance(content, dict):
        rep.err("CLAW_CENTER_CONTENT", base + ".content",
                "ClawCenter.content must be an object",
                "Emit it with build_gptbots_loopagent.claw_center()")
        return
    if content.get("enabled") is False:
        rep.err("CLAW_CENTER_DISABLED", base + ".content.enabled",
                "center.content.enabled=false is a kill switch - the engine answers 40300 "
                "(ClawAgent disabled) on every turn",
                "Set it to true; there is no UI toggle for this field")

    llm = content.get("llm")
    if not isinstance(llm, dict):
        rep.err("CLAW_CENTER_LLM", base + ".content.llm",
                "center.content.llm must be an object {model, baseUrl, maxTokens}")
    else:
        model = llm.get("model")
        if _is_blank(model):
            # fixLoopAgentCenterModel returns early on a blank id — it is NOT backfilled,
            # on either import path. The imported agent therefore has no brain model and
            # the engine fails the first frame with 50101 "No LLM credentials". Worse, on
            # import-as-version this OVERWRITES the model the target already had.
            rep.warn("CLAW_MODEL_EMPTY", base + ".content.llm.model",
                     "the brain model is empty — the import does not backfill it (a blank id "
                     "is returned early, unlike a stale one), so the agent answers 50101 "
                     "'No LLM credentials' on the first message, and importing into an "
                     "EXISTING LoopAgent wipes the model that target had",
                     "Copy the gateway model_version_id out of an export of the target agent, "
                     "or tell the user to re-pick the model in the console (设置页 → 智能体大脑 "
                     "→ 模型) and publish again after importing")
        if isinstance(model, str) and model.strip() and not _HEX24_RE.match(model.strip()):
            rep.warn("CLAW_MODEL_NAME_AS_ID", base + ".content.llm.model",
                     "%r does not look like an AMH gateway model_version_id (24-hex opaque id)"
                     % model,
                     "Leave it blank so the import backfills the platform default - a readable "
                     "model name cannot be routed by the gateway (first frame fails with 50101)")
        bad = _public_http_url(llm.get("baseUrl"))
        if bad:
            rep.err("CLAW_BASEURL_SSRF", base + ".content.llm.baseUrl",
                    "llm.baseUrl %s" % bad,
                    "Use null (normal case) or a public http(s) URL - the import security scan "
                    "rejects internal addresses")
        _claw_int_range(llm.get("maxTokens"), 1, None, base + ".content.llm.maxTokens", rep,
                        "CLAW_MAX_TOKENS", "llm.maxTokens")

    loop = content.get("loop")
    if loop is not None and not isinstance(loop, dict):
        rep.err("CLAW_LOOP_SHAPE", base + ".content.loop", "center.content.loop must be an object")
    elif isinstance(loop, dict):
        # ClawLoopControlValidator runs on the import path too, so these are hard errors.
        _claw_int_range(loop.get("maxTurns"), 1, 100, base + ".content.loop.maxTurns", rep,
                        "CLAW_LOOP_RANGE", "loop.maxTurns")
        _claw_int_range(loop.get("maxErrors"), 0, 50, base + ".content.loop.maxErrors", rep,
                        "CLAW_LOOP_RANGE", "loop.maxErrors")
        _claw_int_range(loop.get("maxBudgetInputTokens"), 0, None,
                        base + ".content.loop.maxBudgetInputTokens", rep,
                        "CLAW_LOOP_RANGE", "loop.maxBudgetInputTokens")

    prompts = content.get("prompts")
    if prompts is not None and not isinstance(prompts, dict):
        rep.err("CLAW_PROMPTS_SHAPE", base + ".content.prompts",
                "center.content.prompts must be an object; `persona` is the only editable key")
    elif isinstance(prompts, dict):
        for key in ("persona", "style", "routing"):
            value = prompts.get(key)
            if value is not None and not isinstance(value, str):
                rep.err("CLAW_PROMPT_TYPE", base + ".content.prompts." + key,
                        "prompts.%s must be a string (\"\" means \"use the engine default\")" % key)
            elif isinstance(value, str):
                _check_single_brace_vars(value, base + ".content.prompts." + key, rep)
        if prompts.get("mainAgentBase") and not prompts.get("persona"):
            rep.warn("CLAW_PROMPT_LEGACY_ALIAS", base + ".content.prompts.mainAgentBase",
                     "`mainAgentBase` is a deprecated alias for `persona`",
                     "Rename the field to `persona`")
        # The console entry points for `style` / `routing` (and the legacy `router`
        # alias) were removed: persona is now the only editable prompt. The engine
        # still reads these keys, so text left here silently shapes behaviour that
        # nobody can see, edit or reset from the UI.
        for key in ("style", "routing", "router"):
            if not _is_blank(prompts.get(key)):
                rep.warn("CLAW_PROMPT_NO_UI", base + ".content.prompts." + key,
                         "`%s` carries text, but its console entry point has been removed — "
                         "the engine still applies it while no operator can review, edit or "
                         "reset it" % key,
                         "Fold the content into `persona` (the only editable prompt) and "
                         'leave this as ""')
        if _is_blank(prompts.get("persona")):
            rep.warn("CLAW_PERSONA_EMPTY", base + ".content.prompts.persona",
                     "the identity prompt is empty - the engine ships no built-in persona, so the "
                     "agent runs with no identity section (legal, but almost never intended)",
                     "Write the identity prompt here; it is the highest-leverage field of a LoopAgent")

    nexts = center.get("nextComponents")
    if not isinstance(nexts, list) or len(nexts) != len(CLAW_SATELLITES):
        rep.warn("CLAW_CENTER_EDGES", base + ".nextComponents",
                 "the center should carry one edge per satellite (%d expected)" % len(CLAW_SATELLITES),
                 "Emit them as {id:\"center-><sat>\", nextComponentId:\"<sat>\", sort:<0..6>}")
    else:
        for i, edge in enumerate(nexts):
            ep = "%s.nextComponents[%d]" % (base, i)
            if not isinstance(edge, dict):
                rep.err("CLAW_EDGE_SHAPE", ep, "each nextComponents entry must be an object")
                continue
            target = edge.get("nextComponentId")
            if not isinstance(target, str) or not target:
                rep.err("CLAW_EDGE_ID_NOT_STRING", ep + ".nextComponentId",
                        "nextComponentId must be a non-empty STRING on a LoopAgent "
                        "(FlowAgent uses integers; Claw matches string handles)")
            sort = edge.get("sort")
            if sort is not None and (isinstance(sort, bool) or not isinstance(sort, int)):
                rep.err("CLAW_EDGE_SORT", ep + ".sort", "sort must be an integer")


def _check_claw_knowledge(content, path, rep):
    _claw_int_range(content.get("matchDataLimit"), 1, 50, path + ".matchDataLimit", rep,
                    "CLAW_KB_RANGE", "matchDataLimit")
    _range(content.get("docCorrelation"), 0.0, 1.0, path + ".docCorrelation", rep)
    _range(content.get("embeddingRate"), 0.0, 1.0, path + ".embeddingRate", rep)
    _check_enum(content.get("searchMode"), CLAW_SEARCH_MODES, "CLAW_KB_SEARCH_MODE",
                path + ".searchMode", rep, "searchMode")
    hop = content.get("graphHopLimit")
    if hop is not None:
        _claw_int_range(hop, 1, 5, path + ".graphHopLimit", rep, "CLAW_KB_RANGE", "graphHopLimit")
    logic = content.get("metadataFilterLogic")
    if logic is not None and logic not in ("AND", "OR"):
        rep.err("CLAW_KB_FILTER_LOGIC", path + ".metadataFilterLogic",
                "metadataFilterLogic must be AND or OR, got %r" % logic)
    for key in CLAW_RETIRED_KNOWLEDGE_KEYS:
        if key in content:
            rep.warn("CLAW_RETIRED_KNOWLEDGE_KEY", path + "." + key,
                     "`%s` is retired for LoopAgent (read-tolerated, never written)" % key,
                     "Remove it - the engine decides when to search")


def _check_claw_skills(content, path, rep):
    refs = content.get("skillRefs")
    if refs is None:
        return
    if not isinstance(refs, list):
        rep.err("CLAW_SKILL_REFS_SHAPE", path + ".skillRefs", "skillRefs must be a list")
        return
    if len(refs) > MAX_CLAW_SKILL_REFS:
        rep.err("CLAW_SKILL_REFS_MAX", path + ".skillRefs",
                "at most %d skills may be attached to one agent (got %d)"
                % (MAX_CLAW_SKILL_REFS, len(refs)))
    for i, ref in enumerate(refs):
        rp = "%s.skillRefs[%d]" % (path, i)
        if not isinstance(ref, dict):
            rep.err("CLAW_SKILL_REF_SHAPE", rp, "each skillRef must be {skillId, enabled, source}")
            continue
        if not isinstance(ref.get("skillId"), str) or not ref.get("skillId"):
            rep.err("CLAW_SKILL_REF_ID", rp + ".skillId", "skillId must be a non-empty string")
        if not isinstance(ref.get("enabled"), bool):
            rep.err("CLAW_SKILL_REF_ENABLED", rp + ".enabled",
                    "enabled must be a boolean - a malformed row is dropped silently on read")
        if ref.get("source") not in CLAW_SKILL_REF_SOURCES:
            rep.err("CLAW_SKILL_REF_SOURCE", rp + ".source",
                    "source must be one of %s, got %r"
                    % (sorted(CLAW_SKILL_REF_SOURCES), ref.get("source")),
                    "An unknown source makes the whole row malformed and it is dropped on read")


def check_claw_rule(cfg, rep):
    """Validate a LoopAgent config: the clawRule topology plus its LoopAgent-only top-level fields."""
    rule = cfg.get("clawRule")
    if not isinstance(rule, dict):
        rep.err("CLAW_RULE_MISSING", "$.clawRule",
                "a LoopAgent must carry a clawRule object",
                "Generate it with scripts/build_gptbots_loopagent.py (1 ClawCenter + 7 satellites)")
        return
    components = rule.get("components")
    if not isinstance(components, list) or not components:
        rep.err("CLAW_COMPONENTS_MISSING", "$.clawRule.components",
                "clawRule.components must be a non-empty list")
        return
    if len(components) > MAX_CLAW_COMPONENTS:
        rep.err("CLAW_TOO_MANY_COMPONENTS", "$.clawRule.components",
                "clawRule has too many components (%d > %d) - the import security scan rejects it"
                % (len(components), MAX_CLAW_COMPONENTS),
                "The legal topology is 8: 1 ClawCenter + 7 satellites")

    seen_ids = set()
    by_id = {}
    for i, comp in enumerate(components):
        cp = "$.clawRule.components[%d]" % i
        if not isinstance(comp, dict):
            rep.err("CLAW_COMP_SHAPE", cp, "each component must be an object")
            continue
        cid = comp.get("id")
        if not isinstance(cid, str) or not cid:
            rep.err("CLAW_COMP_ID_NOT_STRING", cp + ".id",
                    "component id must be a non-empty STRING on a LoopAgent "
                    "(got %r) - FlowAgent's integer ids do not apply here" % (cid,))
        else:
            if cid in seen_ids:
                rep.err("CLAW_COMP_ID_DUP", cp + ".id", "duplicate component id %r" % cid)
            seen_ids.add(cid)
            by_id[cid] = comp
        ctype = comp.get("type")
        if not isinstance(ctype, str) or not ctype:
            rep.err("CLAW_COMP_TYPE", cp + ".type", "component type must be a non-empty string")
        elif ctype not in CLAW_COMPONENT_TYPES:
            rep.warn("CLAW_COMP_TYPE_UNKNOWN", cp + ".type",
                     "unknown Claw component type %r - the engine ignores it" % ctype,
                     "Use one of: " + ", ".join(sorted(CLAW_COMPONENT_TYPES)))
        if comp.get("content") is not None and not isinstance(comp.get("content"), dict):
            rep.err("CLAW_COMP_CONTENT", cp + ".content", "component content must be an object")
        if ctype != CLAW_CENTER_TYPE and comp.get("nextComponents"):
            rep.warn("CLAW_SATELLITE_EDGES", cp + ".nextComponents",
                     "satellites carry no outgoing edges in the radial topology",
                     "Drop the field; only the center owns edges")

    centers = _claw_find(components, CLAW_CENTER_TYPE)
    if not centers:
        rep.err("CLAW_CENTER_MISSING", "$.clawRule.components",
                "no ClawCenter component - the engine rejects the rule with "
                "\"center node required\" (40001 botRule invalid), and the import silently "
                "replaces the whole rule with the platform default topology",
                "Add the center node (build_gptbots_loopagent.claw_center())")
    else:
        if len(centers) > 1:
            rep.err("CLAW_CENTER_DUPLICATE", "$.clawRule.components",
                    "%d ClawCenter components - exactly one is allowed" % len(centers))
        _check_claw_center(centers[0], rep)

    for sid, stype in CLAW_SATELLITES:
        comp = by_id.get(sid)
        if comp is None:
            if not _claw_find(components, stype):
                rep.warn("CLAW_SATELLITE_MISSING", "$.clawRule.components",
                         "satellite %s (%s) is missing - that capability is simply unavailable"
                         % (sid, stype),
                         "Emit the full default topology unless you deliberately dropped it")
            continue
        if comp.get("type") != stype:
            rep.err("CLAW_SATELLITE_TYPE", "$.clawRule.components[%s].type" % sid,
                    "satellite %s must have type %s, got %r" % (sid, stype, comp.get("type")))
        content = comp.get("content")
        if not isinstance(content, dict):
            continue
        path = "$.clawRule.components[%s].content" % sid
        if stype == "Dataset":
            _check_claw_knowledge(content, path, rep)
            if content.get("docGroupIds") or content.get("datasetIds"):
                rep.warn("CLAW_ENV_REFS", path + ".docGroupIds",
                         "knowledge-base ids are environment-bound and are cleared when the file "
                         "is imported as a new Agent",
                         "Ship an empty list and bind the knowledge bases after import")
        elif stype == "ClawDB":
            if content.get("tableIds"):
                rep.warn("CLAW_ENV_REFS", path + ".tableIds",
                         "data-table ids are environment-bound and are cleared on import as a new Agent",
                         "Ship an empty list and pick the tables after import")
        elif stype == "ToolApi":
            if content.get("pluginIds"):
                rep.warn("CLAW_ENV_REFS", path + ".pluginIds",
                         "plugin/MCP ids are filtered against the target organization on import",
                         "Ship an empty list unless the target org owns exactly these plugins")
        elif stype == "ClawSkill":
            _check_claw_skills(content, path, rep)
        elif stype == "ClawKeyEvent":
            _check_enum(content.get("defaultSeverity"), CLAW_SEVERITIES, "CLAW_KEYEVENT_SEVERITY",
                        path + ".defaultSeverity", rep, "defaultSeverity")
        elif stype == "ClawSubAgent":
            _claw_int_range(content.get("parallelCount"), 1, 5, path + ".parallelCount", rep,
                            "CLAW_SUBAGENT_RANGE", "parallelCount")
            if "maxWaitMinutes" in content:
                rep.warn("CLAW_INERT_FIELD", path + ".maxWaitMinutes",
                         "maxWaitMinutes is persisted but never consumed by the engine",
                         "Remove it, and do not promise the behaviour to the user")

    # --- LoopAgent-only top-level fields -------------------------------------
    if not _is_blank(cfg.get("prompt")):
        rep.warn("CLAW_TOP_LEVEL_PROMPT", "$.prompt",
                 "a LoopAgent's identity is clawRule.center.content.prompts.persona - the "
                 "top-level prompt is dead text",
                 "Move the text into the center's persona prompt and leave this empty")
    if "clawToolTraceRecentRounds" in cfg:
        _claw_int_range(cfg.get("clawToolTraceRecentRounds"), 0, 5,
                        "$.clawToolTraceRecentRounds", rep, "CLAW_TOOL_TRACE_ROUNDS",
                        "clawToolTraceRecentRounds")
    mm = cfg.get("multiModal")
    mmi = mm.get("multiModalInput") if isinstance(mm, dict) else None
    if isinstance(mmi, dict):
        mode = mmi.get("messageMode")
        if mode is None:
            rep.warn("CLAW_MESSAGE_MODE", "$.multiModal.multiModalInput.messageMode",
                     "messageMode is unset - historical data is treated as QUEUE",
                     "Set it explicitly to QUEUE (merge queued messages at the turn boundary) "
                     "or APPEND (absorb them into the running turn)")
        elif mode not in CLAW_MESSAGE_MODES:
            rep.err("CLAW_MESSAGE_MODE", "$.multiModal.multiModalInput.messageMode",
                    "messageMode must be QUEUE or APPEND, got %r" % mode)
    skills = cfg.get("privateSkills")
    if isinstance(skills, list):
        if len(skills) > MAX_PRIVATE_SKILLS:
            rep.err("CLAW_PRIVATE_SKILLS_MAX", "$.privateSkills",
                    "at most %d embedded private skills are allowed (got %d)"
                    % (MAX_PRIVATE_SKILLS, len(skills)))
        for i, skill in enumerate(skills):
            sp = "$.privateSkills[%d]" % i
            if not isinstance(skill, dict):
                rep.err("CLAW_PRIVATE_SKILL_SHAPE", sp, "each privateSkills entry must be an object")
                continue
            if _is_blank(skill.get("name")):
                rep.err("CLAW_PRIVATE_SKILL_NAME", sp + ".name",
                        "a skill without a name is discarded entirely on import")
            if _is_blank(skill.get("skillMdContent")):
                rep.warn("CLAW_PRIVATE_SKILL_BLANK", sp + ".skillMdContent",
                         "a blank SKILL.md body is dropped at runtime "
                         "(engine warns \"blank SKILL.md content - dropped\")")


# --------------------------- L8 Audio Agent (multiModal) ---------------------------
# Sources: backend .../bean/entity/BotMultiModal.java (+ audio/*.java),
#   .../helper/audio/AudioConfigValidator.java (server-side ranges/enums),
#   .../common/enums/AudioEngineMode.java + Bot*Enum, frontend types/audio-agent.ts

AUDIO_ENGINE_MODES = {"REALTIME", "ASR_LLM_TTS", "LLM_TTS"}
AUDIO_VOICES = {"none", "alloy", "echo", "fable", "onyx", "nova", "shimmer"}
AUDIO_QUALITY = {"DEFAULT", "HD"}                  # BotAudioModeType
AUDIO_OUTPUT_MODES = {"TTS", "LLM", "DISABLED"}    # BotAudioOutputModeEnum
AUDIO_INPUT_MODES = {"ASR", "LLM", "DISABLED"}     # BotAudioModeEnum
AUDIO_CHAT_MODES = {"Q_A", "INTERRUPT"}            # BotChatModeEnum
AUDIO_IMAGE_MODES = {"auto", "low", "high"}        # BotImageModeType
AUDIO_RECOGNITION_MODES = {"semantic", "server", "preset"}
AUDIO_RESPONSE_SPEEDS = {"low", "medium", "high"}
BG_SOUND_MODES = {"DISABLED", "PRESET", "CUSTOM"}
AUDIO_WELCOME_KEYS = ("speakingAvatar", "waitingAvatar", "welcomeAudio", "welcomeMessage")


def check_audio_config(cfg, rep):
    """Validate an Audio Agent config: the multiModal voice block."""
    mm = cfg.get("multiModal")
    if not isinstance(mm, dict):
        rep.err("AUDIO_MULTIMODAL_MISSING", "$.multiModal",
                "an Audio Agent must carry a multiModal block",
                "Generate it with scripts/build_gptbots_audioagent.py")
        return

    mode = mm.get("engineMode")
    if mode is None:
        rep.err("AUDIO_ENGINE_MODE", "$.multiModal.engineMode",
                "engineMode is required - without it the agent cannot start a voice session "
                "(\"engineMode not configured\")",
                "Set REALTIME, ASR_LLM_TTS or LLM_TTS")
    elif mode not in AUDIO_ENGINE_MODES:
        rep.err("AUDIO_ENGINE_MODE", "$.multiModal.engineMode",
                "invalid engineMode: %r" % mode,
                "Use one of: " + ", ".join(sorted(AUDIO_ENGINE_MODES)))

    if _is_blank(mm.get("identityPrompt")):
        rep.warn("AUDIO_IDENTITY_PROMPT_EMPTY", "$.multiModal.identityPrompt",
                 "the voice session runs multiModal.identityPrompt, not the top-level prompt - "
                 "it is empty",
                 "Write the identity prompt here, phrased for speech (short sentences, no "
                 "markdown, no URLs read aloud)")
    else:
        _check_single_brace_vars(mm.get("identityPrompt"), "$.multiModal.identityPrompt", rep)

    tokens = cfg.get("maxRespTokens")
    if tokens is not None and (isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0):
        rep.err("AUDIO_MAX_RESP_TOKENS", "$.maxRespTokens",
                "maxRespTokens must be a positive integer, got %r" % (tokens,),
                "It must also stay below the chat model's context limit - the audio path budgets "
                "knowledge/plugin tokens as tokensLimit - maxRespTokens")

    mmi = mm.get("multiModalInput")
    if isinstance(mmi, dict):
        base = "$.multiModal.multiModalInput"
        _check_enum(mmi.get("audioMode"), AUDIO_INPUT_MODES, "AUDIO_INPUT_MODE",
                    base + ".audioMode", rep, "multiModalInput.audioMode")
        _check_enum(mmi.get("chatMode"), AUDIO_CHAT_MODES, "AUDIO_CHAT_MODE",
                    base + ".chatMode", rep, "multiModalInput.chatMode")
        _check_enum(mmi.get("fileMode"), FILE_MODES, "AUDIO_FILE_MODE",
                    base + ".fileMode", rep, "multiModalInput.fileMode")
        _check_enum(mmi.get("imageMode"), AUDIO_IMAGE_MODES, "AUDIO_IMAGE_MODE",
                    base + ".imageMode", rep, "multiModalInput.imageMode")
        _check_list_enum(mmi.get("fileSupportTypes"), MULTI_MODAL_DATA_TYPES,
                         "AUDIO_FILE_TYPES", base + ".fileSupportTypes", rep, "fileSupportTypes")
        lang = mmi.get("sourceLang")
        if lang is not None:
            if not isinstance(lang, dict):
                rep.err("AUDIO_SOURCE_LANG", base + ".sourceLang",
                        "sourceLang must be an object containing a boolean autoDetect")
            elif not isinstance(lang.get("autoDetect"), bool):
                rep.err("AUDIO_SOURCE_LANG", base + ".sourceLang.autoDetect",
                        "sourceLang.autoDetect must be a BOOLEAN, got %r" % (lang.get("autoDetect"),),
                        'Use {"autoDetect": true} or {"autoDetect": false, "languages": ["en"]}')

    mmo = mm.get("multiModalOutput")
    if isinstance(mmo, dict):
        base = "$.multiModal.multiModalOutput"
        _check_enum(mmo.get("audioVoice"), AUDIO_VOICES, "AUDIO_VOICE",
                    base + ".audioVoice", rep, "multiModalOutput.audioVoice")
        _check_enum(mmo.get("audioMode"), AUDIO_QUALITY, "AUDIO_QUALITY",
                    base + ".audioMode", rep, "multiModalOutput.audioMode")
        _check_enum(mmo.get("audioModeOutput"), AUDIO_OUTPUT_MODES, "AUDIO_OUTPUT_MODE",
                    base + ".audioModeOutput", rep, "multiModalOutput.audioModeOutput")
        sf = mmo.get("symbolFilter")
        if sf is not None:
            if not isinstance(sf, dict):
                rep.err("AUDIO_SYMBOL_FILTER", base + ".symbolFilter",
                        "symbolFilter must be {remove: [...], replace: [{from, to}]}")
            else:
                for j, rule in enumerate(sf.get("replace") or []):
                    if not isinstance(rule, dict) or "from" not in rule or "to" not in rule:
                        rep.err("AUDIO_SYMBOL_FILTER",
                                "%s.symbolFilter.replace[%d]" % (base, j),
                                "each replace rule must be {from, to}")

    vad = mm.get("vad")
    if isinstance(vad, dict):
        base = "$.multiModal.vad"
        _claw_int_range(vad.get("pauseThresholdMs"), 0, 5000, base + ".pauseThresholdMs", rep,
                        "AUDIO_CONFIG_RANGE", "vad.pauseThresholdMs")
        _range(vad.get("interruptSensitivity"), 0.0, 1.0, base + ".interruptSensitivity", rep)
        _range(vad.get("minVolume"), 0.0, 1.0, base + ".minVolume", rep)
        _range(vad.get("activationThreshold"), 0.0, 1.0, base + ".activationThreshold", rep)
        _check_enum(vad.get("recognitionMode"), AUDIO_RECOGNITION_MODES, "AUDIO_CONFIG_RANGE",
                    base + ".recognitionMode", rep, "vad.recognitionMode")
        _check_enum(vad.get("responseSpeed"), AUDIO_RESPONSE_SPEEDS, "AUDIO_CONFIG_RANGE",
                    base + ".responseSpeed", rep, "vad.responseSpeed")

    out = mm.get("output")
    if isinstance(out, dict):
        base = "$.multiModal.output"
        _claw_int_range(out.get("bufferMs"), 0, 1500, base + ".bufferMs", rep,
                        "AUDIO_CONFIG_RANGE", "output.bufferMs")
        bg = out.get("bgSound")
        if isinstance(bg, dict):
            _check_enum(bg.get("mode"), BG_SOUND_MODES, "AUDIO_BG_SOUND_MODE",
                        base + ".bgSound.mode", rep, "output.bgSound.mode")
            _claw_int_range(bg.get("volume"), 1, 50, base + ".bgSound.volume", rep,
                            "AUDIO_CONFIG_RANGE", "output.bgSound.volume")
            bad = _public_http_url(bg.get("uploadUrl"))
            if bad:
                rep.err("AUDIO_URL", base + ".bgSound.uploadUrl", "uploadUrl %s" % bad)

    cc = mm.get("callControl")
    if isinstance(cc, dict):
        base = "$.multiModal.callControl"
        cold = cc.get("coldStart")
        if isinstance(cold, dict):
            _claw_int_range(cold.get("silenceThresholdSec"), 5, 60,
                            base + ".coldStart.silenceThresholdSec", rep,
                            "AUDIO_CONFIG_RANGE", "callControl.coldStart.silenceThresholdSec")
        hangup = cc.get("hangup")
        if isinstance(hangup, dict):
            _claw_int_range(hangup.get("maxCallSec"), 30, 3600, base + ".hangup.maxCallSec", rep,
                            "AUDIO_CONFIG_RANGE", "callControl.hangup.maxCallSec")
            _claw_int_range(hangup.get("maxSilenceSec"), 1, 180, base + ".hangup.maxSilenceSec",
                            rep, "AUDIO_CONFIG_RANGE", "callControl.hangup.maxSilenceSec")
            _claw_int_range(hangup.get("maxSilenceCount"), 1, 100,
                            base + ".hangup.maxSilenceCount", rep,
                            "AUDIO_CONFIG_RANGE", "callControl.hangup.maxSilenceCount")

    welcome = mm.get("welcome")
    if isinstance(welcome, dict):
        for key in AUDIO_WELCOME_KEYS:
            value = welcome.get(key)
            if value is None:
                continue
            if not isinstance(value, dict):
                rep.err("AUDIO_WELCOME_SHAPE", "$.multiModal.welcome." + key,
                        "%s must be a {language: value} map" % key)
                continue
            for lang, item in value.items():
                wp = "$.multiModal.welcome.%s.%s" % (key, lang)
                if not isinstance(item, str):
                    rep.err("AUDIO_WELCOME_SHAPE", wp, "the value must be a string")
                elif key != "welcomeMessage":
                    bad = _public_http_url(item)
                    if bad:
                        rep.err("AUDIO_URL", wp, "media URL %s" % bad)


# --------------------------- L9 cross-type block placement ---------------------------

def check_cross_type_blocks(cfg, bot_type, rep):
    """Warn when a type-specific block sits on the wrong botType (it is ignored on import)."""
    if bot_type is None:
        return
    if cfg.get("clawRule") and bot_type != "LoopAgent":
        rep.warn("XTYPE_CLAW_RULE", "$.clawRule",
                 "clawRule only applies to botType=LoopAgent - it is ignored here",
                 "Remove it, or set botType to LoopAgent")
    if cfg.get("flowRule") and bot_type != "Flow":
        rep.warn("XTYPE_FLOW_RULE", "$.flowRule",
                 "flowRule only applies to botType=Flow - it is ignored here",
                 "Remove it, or set botType to Flow")
    if cfg.get("privateSkills") and bot_type != "LoopAgent":
        rep.warn("XTYPE_PRIVATE_SKILLS", "$.privateSkills",
                 "embedded private skills are a LoopAgent-only feature")
    mm = cfg.get("multiModal")
    if isinstance(mm, dict) and bot_type != "Audio":
        for key in ("engineMode", "vad", "output", "callControl", "welcome", "identityPrompt"):
            if mm.get(key):
                rep.warn("XTYPE_AUDIO_BLOCK", "$.multiModal." + key,
                         "`%s` is an Audio Agent field - it has no effect on botType=%s"
                         % (key, bot_type))
    mmi = mm.get("multiModalInput") if isinstance(mm, dict) else None
    if isinstance(mmi, dict) and mmi.get("messageMode") and bot_type != "LoopAgent":
        rep.warn("XTYPE_MESSAGE_MODE", "$.multiModal.multiModalInput.messageMode",
                 "messageMode (QUEUE/APPEND) only applies to LoopAgent; other types keep it null")



# ----------------------------- main flow -----------------------------

def validate(cfg, raw_len):
    rep = Report()
    if raw_len > MAX_FILE_SIZE:
        rep.err("L0_SIZE", "$", f"The file exceeds the {MAX_FILE_SIZE}-byte limit")
    bot_type = check_top_level(cfg, rep)
    check_top_level_enums(cfg, rep)
    if bot_type == "Workflow":
        check_workflow_graph(cfg.get("workflow"), rep, "$.workflow")
    elif bot_type == "Flow":
        check_flow(cfg.get("flowRule"), rep)
        if cfg.get("workflow"):
            check_workflow_graph(cfg.get("workflow"), rep, "$.workflow")
    elif bot_type == "LoopAgent":
        check_claw_rule(cfg, rep)
    elif bot_type == "Audio":
        check_audio_config(cfg, rep)
    check_cross_type_blocks(cfg, bot_type, rep)
    check_secrets_and_refs(cfg, rep)
    check_human_config(cfg, rep)
    return rep


def main(argv):
    parser = argparse.ArgumentParser(description="GPTBots .bot/.flow config quality check")
    parser.add_argument("file", help="path to the .bot or .flow file")
    parser.add_argument("--json", action="store_true", help="output the result as JSON")
    args = parser.parse_args(argv)

    try:
        with open(args.file, "rb") as f:
            raw = f.read()
    except OSError as e:
        print(f"Unable to read file: {e}", file=sys.stderr)
        return 2
    try:
        cfg = json.loads(raw.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        result = {"ok": False, "errors": [{"code": "L0_JSON", "path": "$",
                  "message": f"Invalid JSON: {e}", "fix": "Fix the JSON syntax"}], "warnings": []}
        _emit(result, args.json)
        return 1

    rep = validate(cfg, len(raw))
    result = {"ok": rep.ok, "errors": rep.errors, "warnings": rep.warnings}
    _emit(result, args.json)
    return 0 if rep.ok else 1


def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if result["ok"]:
        print("✅ Quality check passed" + (f" ({len(result['warnings'])} warning(s))" if result["warnings"] else ""))
    else:
        print(f"❌ Quality check failed: {len(result['errors'])} error(s), {len(result['warnings'])} warning(s)")
    for e in result["errors"]:
        print(f"  [ERROR {e['code']}] {e['path']}: {e['message']}"
              + (f" → {e['fix']}" if e['fix'] else ""))
    for w in result["warnings"]:
        print(f"  [WARN  {w['code']}] {w['path']}: {w['message']}"
              + (f" → {w['fix']}" if w['fix'] else ""))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
