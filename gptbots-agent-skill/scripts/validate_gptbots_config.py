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
When the schema changes, re-sync against these and bump the skill version.

Usage:
  python3 validate_gptbots_config.py <file.bot|file.flow> [--json]
Exit codes: 0 = pass (no error); 1 = has error; 2 = usage/read error.
"""
import argparse
import json
import re
import sys

# Bot types this skill authors. The backend BotType enum has additional types, but this
# skill only generates QuestionAnswer / Flow / Workflow, so the validator scopes to those.
BOT_TYPES = {"QuestionAnswer", "Flow", "Workflow"}
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
                "Set it to QuestionAnswer / Flow / Workflow")
    # exportType / botType consistency
    if bot_type == "Workflow" and export_type != "WORKFLOW":
        rep.err("L0_TYPE_MISMATCH", "$.exportType", "Workflow requires exportType=WORKFLOW")
    if bot_type in {"QuestionAnswer", "Flow"} and export_type == "WORKFLOW":
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
                    'Add at least "multiModal": {"multiModalInput": {}} (empty object is safe: '
                    "null chatMode is only compared against INTERRUPT). Do NOT guess "
                    "audioMode/chatMode/imageMode enum values — copy them from a real export")
    # QuestionAnswer field-name gotchas (confirmed against a real export): the opening
    # line is `firstMessage` and the suggested questions are `presetQuestions`. The
    # plausible-looking `welcomeMessage` / `guidingQuestions` are dropped on import.
    if bot_type == "QuestionAnswer":
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
                    # The prompt text lives in `text`. A `content` key here is the wrong
                    # schema (that's the Message/Predefine reply field) — on import the
                    # prompt deserializes BLANK, silently breaking the node.
                    if "content" in m and "text" not in m:
                        rep.err("MSG_CONTENT_FIELD", mpath + ".content",
                                "prompt message uses `content`; the field must be `text` "
                                "(a `content` key here imports as a BLANK prompt)",
                                'Rename "content" to "text"')
                    # An empty Role message = blank identity prompt (the node has no instructions).
                    if m.get("type") == "Role":
                        rtext = m.get("text") if "text" in m else m.get("content")
                        if not (rtext and str(rtext).strip()):
                            rep.err("MSG_ROLE_EMPTY", mpath + ".text",
                                    f"the Role (identity prompt) of {c.get('type')} #{c.get('id')} is empty "
                                    "— the node will run with no instructions",
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
                        rep.err("BRANCH_EXCEPTION_EDGE", ep + ".sourceHandle",
                                "Classifier has no branch_exception edge — its exception is "
                                "governed by the exceptionSwitch toggle (a system-preset row), "
                                "not an authored edge",
                                "Remove this edge; set exceptionSwitch=true on the classifier instead")
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
        # Duplicate-line detection: platform imports have been observed duplicating exception
        # edges (an old `Exception` entry with condition=null + a new `_exception` entry, same
        # id / sourceHandle). Harmless to the engine (nextComponents is pass-through, no toMap)
        # but it is dirty data and renders doubled lines — flag same (sourceHandle, target).
        line_seen = set()
        handle_seen = set()
        for k, nx in enumerate(nexts):
            if not isinstance(nx, dict):
                continue
            # Each output handle drives a single edge. A repeated sourceHandle on the
            # same component is a duplicate outlet (the classic import artifact: an old
            # `Exception`/`name=null` edge plus a new `_exception` one on the same
            # conditions_exception/branch port). These duplicates corrupt the node —
            # e.g. the Condition's IF port renders greyed/unusable — so this is an error,
            # not just a doubled line.
            shandle = nx.get("sourceHandle")
            if shandle is not None:
                if shandle in handle_seen:
                    rep.err("EDGE_DUP_HANDLE", f"{cp}.nextComponents[{k}].sourceHandle",
                            f"Duplicate sourceHandle {shandle!r} on component #{c.get('id')} — "
                            "an output port may have only one edge; duplicates (often leftover "
                            "Exception/_exception import artifacts) corrupt the node and grey out ports",
                            "Keep exactly one edge per handle; delete the duplicates")
                handle_seen.add(shandle)
            line = (nx.get("sourceHandle"), nx.get("nextComponentId"))
            if line[0] is not None and line[1] is not None:
                if line in line_seen:
                    rep.warn("EDGE_DUP_LINE", f"{cp}.nextComponents[{k}]",
                             f"Duplicate edge: sourceHandle {line[0]!r} → component {line[1]} "
                             f"appears more than once (typical import artifact: old 'Exception' "
                             f"+ new '_exception' entries) — remove the duplicate")
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
