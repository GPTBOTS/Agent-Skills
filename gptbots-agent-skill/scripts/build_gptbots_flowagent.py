#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlowAgent `.bot` builder (botType=Flow). One of three generators:
  build_gptbots_agent.py     → QuestionAnswer .bot
  build_gptbots_flowagent.py → FlowAgent .bot (this file)
  build_gptbots_workflow.py  → Workflow .flow

Why a builder: hand-written FlowAgent JSON reliably goes wrong in three places —
edge handles (strict `right{srcId}-{key}[_{suffix}]` / `left{dstId}-{key}` with the
key matched to component type), unique component/edge/branch ids, and repeated
boilerplate. This builder generates all three mechanically so your effort goes
into prompts, branch rules, and flow design. Field semantics come from
`../references/create-gptbots-flowagent.md` + `flowagent-components.md`;
`save()` runs `validate_gptbots_config.py` as the final gate.

Recommended pattern (proven on a real 30+ node production bot): write a
generation script that imports this builder, keeps the identity prompt /
branch rules / gather SOPs as Python string constants, factors *your* repeated
node shapes into small functions (answer_node(), gather_node(), …), then
save() → fix reported issues → rerun. The generation script is the source;
the .bot is its regenerable build artifact.

⚠️ The classic handle mistake this builder makes impossible: passing the key
inside the suffix (e.g. suffix="knowledge_true" → right4-knowledge_knowledge_true,
or suffix="branch_<id>" → right2-branch_branch_<id>). The offline validator only
checks the base key, so the doubled form slips through — but the canvas can't
resolve the port and draws distorted lines. `connect()` raises on it; pass only
the part AFTER the key: "true" / "false" / "other" / "exception" / a branch id.

Example
-------
    from build_gptbots_flowagent import (FlowAgentBuilder, role, user_input, kb_msg,
                                         cond_msg, mem, ke, load_prompt_store)

    P = load_prompt_store("prompts/")   # one <node name>.md per node (the standard)
    b = FlowAgentBuilder("My Agent",
            description="…", human_config={"manufacturer": "LiveChat", "status": "enable"},
            key_event_config={  # bot-level key-event extraction (verify against a real export)
                "enable": True, "messageThreshold": 10, "idleTimeoutMinutes": 3,
                "recentEventCount": 5, "extractionRules": "…",
                "eventTypes": [{"name": "deposit", "description": "…"}]})
    i  = b.add("Input", "User Input")
    cl = b.add("Branch", "Intent_Classifier", exceptionSwitch=True, chatModelVersionId="",
               **mem(short=True), **ke(2),
               messages=[role(P.require("Intent_Classifier")), user_input()])
    ds = b.add("Dataset", "KB_Search", **b.dataset_defaults())
    ans = b.add("LLM", "Answer", **b.llm_defaults(),
                messages=[role(P.require("Answer")), kb_msg("KB_Search"), user_input()])
    out = b.add("Output", "Output"); hm = b.add("Human", "Human Handoff")
    b.connect(i, cl)
    b.branch_edge(cl, ds, rule="The user is asking about product features...", name="features")
    b.branch_other(cl, hm)   # exceptionSwitch=True handles the classifier's exception (no edge)
    b.connect(ds, ans, suffix="true"); b.connect(ds, hm, suffix="false")
    b.connect(ans, out); b.connect(ans, hm, suffix="exception")
    b.save("my-agent.bot")
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Convenience re-export: keep long prompts in an external prompts.md / .json and
# load them with load_prompts("prompts.md") — see gptbots_prompts.py.
try:
    from gptbots_prompts import load_prompts, load_prompt_store  # noqa: F401
except ImportError:  # allow importing this builder without the prompts helper
    load_prompts = load_prompt_store = None

# Per-type handle keys. left = target/input key, right = source/output key.
# Case-sensitive; only LLM is uppercase. FormGather is asymmetric (the one exception).
_TARGET_KEY = {
    "Input": "input", "Output": "output", "LLM": "LLM", "Bool": "boolean",
    "Branch": "branch", "Predefine": "preset", "Message": "message",
    "Dataset": "knowledge", "Human": "artificial", "Condition": "conditions",
    "Regular": "regular", "ChatGather": "qa-collect", "FormGather": "form-collect",
    "ToolApi": "toolapi", "Workflow": "workflow", "Variable": "variable",
}
_SOURCE_KEY = dict(_TARGET_KEY, FormGather="formgather")
_TERMINAL = {"Output", "Human"}

# Default maxRespTokens for LLM-driven nodes (a null/missing value shows an empty
# "Maximum Response" on the canvas).
DEFAULT_MAX_TOKENS = 4096
# Node types that carry an LLM core and therefore need maxRespTokens set.
_LLM_DRIVEN = {"LLM", "Branch", "Condition", "ChatGather", "FormGather"}
# Platform built-in avatar — a blank/custom logo URL renders as a broken icon.
DEFAULT_AGENT_LOGO = "/developer/static/images/avatar/default_avatar_202506131619.png"


# ---------------------------------------------------------------------------
# message / config factories (shapes verified against real platform exports)
# ---------------------------------------------------------------------------
# A FlowAgent prompt message is this exact object — the text lives in `text`
# (NOT `content`: a `content` key is silently ignored on import and the prompt
# imports BLANK). An LLM-capable node's `messages` is the standard array
# [Role, LongMemory, ShortMemory, Plugin, (Condition for Condition nodes), Input];
# build() assembles it and backfills the Input message's `upstream`.
def _msg(mtype, text="", upstream=None):
    return {"lineId": None, "type": mtype, "text": text, "ids": [],
            "upstream": upstream, "children": None, "datasetType": None}


def role(text):
    """The identity / system prompt (Role message) — the highest-leverage field.
    Accepts the prompt string; build() wraps it in the full message object."""
    return _msg("Role", text)


def message_content(text, content_type="Text"):
    """Build a Message (pass-through) component's `content`: a JSON STRING keyed by
    contentType, e.g. message_content("hi") -> '{"Text":"hi"}'. The platform parses
    `content` as JSON and reads the value under the contentType key; a plain string
    renders an empty message."""
    return json.dumps({content_type: text}, ensure_ascii=False)


def _encode_message_content(value, content_type):
    """Normalize a Message `content` to the required JSON-string form. Passes through
    a value that already decodes to a dict containing the contentType key."""
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        try:
            d = json.loads(value)
            if isinstance(d, dict) and content_type in d:
                return value
        except (ValueError, TypeError):
            pass
        return json.dumps({content_type: value}, ensure_ascii=False)
    return json.dumps({content_type: "" if value is None else str(value)}, ensure_ascii=False)


def cond_msg(text):
    """DEPRECATED for the IF text. A Condition node's IF condition is read from
    the **conditions_true edge's `condition` field**, not a node message — use
    `condition_edges(cond, if_text, true_dst, false_dst)`. Putting the IF text in
    a node message leaves the platform's IF box empty. Kept only for callers that
    still want a Condition-type message object."""
    if not (text and text.strip()):
        raise ValueError("Condition If-text must be non-empty (canvas rejects it)")
    return _msg("Condition", text)


# Back-compat shims: older scripts called these; the real schema injects the
# user input via the auto-assembled Input message and KB via dataEnable +
# datasetMessages, so these now return None and are dropped during assembly.
def user_input():
    """Deprecated — the Input message is auto-assembled with upstream backfill.
    Returns None (dropped during message assembly)."""
    return None


def kb_msg(kb_node_name=None, label=None):
    """Deprecated — knowledge retrieval is injected via dataEnable + datasetMessages
    (set reads_kb=True on the consuming LLM), not via a Dataset message. Returns None."""
    return None


def mem(short=True, longterm=False, userprop=False):
    """Memory switches for LLM-driven components. Short-term memory is what lets a
    Classifier/Condition judge fragmentary follow-ups by conversation context."""
    return {"memoryEnable": True, "shortTermMemory": bool(short),
            "longTermMemory": bool(longterm), "userPropertyEnable": bool(userprop)}


def ke(recent_count=5, enable=True, event_types=None):
    """Per-component key-event memory config (Classifier/LLM/Condition/ChatGather).
    ⚠️ The exact field shape is not in the import spec — verify against a real
    platform export and check the node's Memory→Key Events panel after import."""
    return {"keyEventConfig": {"enable": bool(enable),
                               "recentEventCount": int(recent_count),
                               "eventTypes": event_types or []}}


_FIELD_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def gather_fields(fields):
    """ChatGather/FormGather fields from (name, description, required) tuples.

    Confirmed against a real export: the backend reads the field name from
    **fieldName** (with showName as the display label). The keys name /
    variableName / key are silently DROPPED on import — using them makes the
    platform assign random default names (age / user_birthday / age1 …).
    optionFieldType is required (None for free-text fields).

    `fieldName` becomes a variable key, so it must contain only lowercase
    letters, digits, and underscores (`[a-z0-9_]`); this raises on a bad name."""
    out = []
    for (n, d, req) in fields:
        if not _FIELD_NAME_RE.match(n or ""):
            raise ValueError(f"gather field name {n!r} is invalid — fieldName must be "
                             f"lowercase letters, digits, and underscores only ([a-z0-9_])")
        out.append({"showName": n, "fieldName": n, "gatherType": "selfDefining",
                    "valueType": "string", "description": d, "isRequired": bool(req),
                    "optionFieldType": None})
    return out


def var_cfgs(pairs, operation="Cover"):
    """Variable (assignment) component configs from (name, value) pairs.
    Per-assignment shape is {variableName, operation, value}; `operation` is
    Cover / Clear / Append (capitalized).

    ⚠️ A Variable node can only assign to a **User Attribute or Custom Variable
    that already exists on the platform** — importing a .bot does NOT auto-create
    them, so assignments to undefined targets are silently dropped (the node shows
    "No variables available"). For the common "collect fields, then act" pattern,
    you usually do NOT need a Variable node at all: route the ChatGather's
    collect-complete edge straight to the next step (e.g. human handoff); the
    collected fields + conversation context carry forward, and key events capture
    the business type/status. Only use this helper when the target attributes are
    pre-defined in the workspace."""
    return [{"variableName": k, "operation": operation, "value": v}
            for (k, v) in pairs]


# Known-good multiModal block copied verbatim from a real platform export.
# Used as the builder default: satisfies the auto-save NPE guard AND carries
# real enum values (do not hand-edit the enum strings — copy from an export).
_DEFAULT_MULTIMODAL = {
    "multiModalInput": {"fileLimit": 1, "fileMode": "DISABLED", "imageMode": "auto",
                        "audioMode": "ASR", "chatMode": "Q_A", "textSwitch": True,
                        "fileSupportTypes": None, "audioModelVersionId": None,
                        "fileSwitch": None, "asrPrompt": None},
    "multiModalOutput": {"textLanguage": "auto", "audioMode": "DEFAULT", "audioVoice": None,
                         "audioModelVersionId": None, "audioModeOutput": "TTS",
                         "textSwitch": True, "showAiGeneratedContent": False},
}


# ---------------------------------------------------------------------------
class FlowAgentBuilder:
    """Assemble a FlowAgent .bot: auto component ids, auto edge handles, auto layout."""

    def __init__(self, name, description="", brief_introduction="", human_config=None,
                 key_event_config=None, **top_fields):
        self.name = name
        self.description = description
        self.brief_introduction = brief_introduction
        self.human_config = human_config or {"manufacturer": "Webhook", "status": "disable"}
        self.key_event_config = key_event_config
        self.top_fields = top_fields      # e.g. modeType, reasoningEffort, showReasoning
        self.components = []
        self._by_id = {}
        self._next_id = 1
        self._edge_seq = 0
        self._branch_counts = {}   # per-Branch component: sequential branch number (branch_1, branch_2, …)

    # -- components ---------------------------------------------------------
    def add(self, ctype, name, x=None, y=None, **fields):
        """Add a component; returns its int id. x/y optional (auto-layout in build())."""
        if ctype not in _TARGET_KEY:
            raise ValueError(f"unknown FlowComponentType {ctype!r} — use the enum value "
                             f"(Classifier→Branch, If-Else→Bool, Knowledge Search→Dataset, "
                             f"Card→Predefine, Tools→ToolApi, Human Service→Human)")
        cid = self._next_id
        self._next_id += 1
        # Conveniences: prompt= (the Role text) and reads_kb= (consumes an upstream
        # Dataset/Knowledge node's retrieval). Both desugar to the real schema.
        prompt = fields.pop("prompt", None)
        reads_kb = fields.pop("reads_kb", False)
        # x/y are backend Integer fields — coerce so floats/strings never reach the JSON
        comp = {"type": ctype, "id": cid, "name": name, "title": name,
                "x": None if x is None else int(x), "y": None if y is None else int(y),
                "nextComponents": []}
        comp.update(fields)
        # Classifier defaults to EXTRACT run mode (each branch receives only the
        # part matching its rule; Other receives the full message) unless overridden.
        if ctype == "Branch" and "branchRunMode" not in comp:
            comp["branchRunMode"] = "EXTRACT"
        # Every LLM-driven node needs maxRespTokens, or the canvas shows an empty
        # "Maximum Response". Default to 4096 unless the caller set it.
        if ctype in _LLM_DRIVEN and "maxRespTokens" not in comp:
            comp["maxRespTokens"] = DEFAULT_MAX_TOKENS
        # A Message (pass-through) component's `content` must be a JSON STRING keyed by
        # contentType, e.g. contentType="Text" → content='{"Text":"...the text..."}'.
        # A plain string fails to parse and the message renders empty. Auto-encode a
        # plain string (and default contentType to Text); leave an already-encoded
        # value or a dict handled correctly.
        if ctype == "Message" and "content" in comp:
            comp.setdefault("contentType", "Text")
            comp["content"] = _encode_message_content(comp["content"], comp["contentType"])
        if prompt is not None and "messages" not in comp:
            comp["messages"] = [role(prompt)]
        if reads_kb:
            # KB retrieval is injected via dataEnable + datasetMessages (a Content
            # placeholder the backend fills with the upstream Dataset result) — NOT
            # via a message in the `messages` array.
            comp["dataEnable"] = True
            comp["datasetMessages"] = [_msg("Content")]
        self.components.append(comp)
        self._by_id[cid] = comp
        return cid

    @staticmethod
    def llm_defaults(max_tokens=DEFAULT_MAX_TOKENS, exception=True, short_memory=True, userprop=False):
        """Known-good baseline for an LLM component (merge, then add name/messages).
        maxRespTokens defaults to 4096."""
        return {"chatModelVersionId": "", "maxRespTokens": int(max_tokens),
                "responseFormat": "Text", **mem(short=short_memory, userprop=userprop),
                "toolsEnable": False, "databaseEnable": False,
                "exceptionSwitch": bool(exception)}

    @staticmethod
    def dataset_defaults(match_limit=4, rerank=True):
        """Known-good baseline for a Dataset (knowledge search) component."""
        d = {"docCorrelation": 0.5, "matchDataLimit": int(match_limit),
             "rerankSwitch": bool(rerank), "dataSourceShowType": "LIST_SHOW",
             "customKnowledgeType": "DEFAULT", "docGroupIds": []}
        if rerank:
            d["rerankModelVersionId"] = ""
        return d

    # -- handles & edges ------------------------------------------------------
    def th(self, cid):
        return f"left{cid}-{_TARGET_KEY[self._by_id[cid]['type']]}"

    def sh(self, cid, suffix=""):
        key = _SOURCE_KEY[self._by_id[cid]["type"]]
        if suffix and (suffix == key or suffix.startswith(key + "_") or suffix.startswith(key.lower() + "_")):
            raise ValueError(
                f"suffix {suffix!r} repeats the handle key {key!r} — this produces a doubled "
                f"handle (right{cid}-{key}_{suffix}) that the canvas cannot resolve (distorted "
                f"lines). Pass only the part after '{key}_': 'true'/'false'/'other'/'exception' "
                f"or a branch id.")
        return f"right{cid}-{key}_{suffix}" if suffix else f"right{cid}-{key}"

    def connect(self, src, dst, suffix="", condition="", name=""):
        """Add an edge src→dst with correct handles.
        suffix: '' (single-output success), 'true'/'false' (Dataset/Bool/Condition/
        ChatGather/FormGather), 'other' (Bool/Branch fallback), or 'exception'
        (a wired exception outlet on LLM/Condition/ChatGather/Variable when
        exceptionSwitch=True). The Classifier (Branch) is the exception: it has
        NO branch_exception edge — its exception is the preset exceptionSwitch
        row (set exceptionSwitch=True, don't wire it). Prefer branch_edge() for
        Branch categories.

        The edge `id` is auto-generated as a unique integer (100000 + seq).
        The backend DTO parses this field as a Long, so ANY string value —
        "e1", "vueflow__edge-...", anything — fails import with
        'value X is not allowed for field id'. The 100000+ offset keeps edge
        ids from colliding with component ids."""
        scomp = self._by_id[src]
        if scomp["type"] in _TERMINAL:
            raise ValueError(f"{scomp['type']} #{src} is terminal — no outgoing edges")
        if scomp["type"] == "Branch" and suffix == "exception":
            raise ValueError(
                "the Classifier (Branch) has no branch_exception edge — its exception is "
                "governed by the exceptionSwitch toggle (a system-preset row, like Other), "
                "not a wired edge. Set exceptionSwitch=True on the classifier and do not "
                "connect an exception branch. (LLM/Condition/ChatGather/Variable do expose a "
                "wired exception outlet — suffix='exception' is valid for those.)")
        # A Condition node's outlets carry fixed names: the conditions_true edge is
        # name="_true" and its `condition` holds the IF text; conditions_false is
        # name="_false" with empty condition. Auto-fill the name if not given so raw
        # connect() calls still produce the schema the platform expects.
        if scomp["type"] == "Condition" and not name:
            if suffix == "true":
                name = "_true"
            elif suffix == "false":
                name = "_false"
        self._edge_seq += 1
        eid = 100000 + self._edge_seq
        sh, th = self.sh(src, suffix), self.th(dst)
        scomp["nextComponents"].append({
            "id": eid,
            "nextComponentId": dst,
            "sourceHandle": sh,
            "targetHandle": th,
            "condition": condition,
            # `sort` must equal the edge `id` — a globally unique integer. Using a
            # per-node counter (1, 2, …) makes many edges across the bot share the
            # same sort; that collision makes the canvas mis-render and shows branch
            # target nodes as greyed/unusable. Real exports set sort == id.
            "sort": eid,
            "name": name,
        })

    def branch_edge(self, branch_cid, dst, rule, name=""):
        """Add one Classifier (Branch) category edge.

        `rule` is the category's routing rule — the LLM executes it on every
        message to decide whether to take this branch. In the real export schema
        the rule text lives in the edge's `condition` (a natural-language string),
        NOT in the classifier's identity prompt, and the handle suffix is a simple
        SEQUENTIAL number per classifier: right{id}-branch_1, branch_2, … (an
        earlier version wrongly put a timestamp id in both `condition` and the
        handle, so the UI showed the id instead of the rule). `name` is the human
        label for the category (e.g. "want_human"). Make rules concrete and
        mutually exclusive, route fragmentary follow-ups to the ongoing topic's
        branch, and never leave one empty."""
        if not (rule and rule.strip()):
            raise ValueError("Branch category rule must be non-empty "
                             "(canvas rejects 'Cannot be empty' and the node is unusable)")
        n = self._branch_counts.get(branch_cid, 0) + 1
        self._branch_counts[branch_cid] = n
        self.connect(branch_cid, dst, suffix=str(n), condition=rule, name=name)

    def branch_other(self, branch_cid, dst):
        """Route the Classifier's **system-preset** 'Other' fallback to `dst`.

        Other is NOT a category you generate — the platform provides it as the
        built-in bottom branch. The edge MUST be `name="_other"` + `condition=""`
        (an empty string, NOT null/omitted) so the platform maps it to the
        built-in Other. ⚠️ Setting `name=null` (hoping "no name = not a class")
        backfires: the platform then renders branch_other as an editable BLANK
        category, and deleting it loses the Other route. This helper emits the
        correct `_other` / `""` shape on the preset handle right{id}-branch_other;
        it carries no rule and consumes no branch number (unlike branch_edge())."""
        self.connect(branch_cid, dst, suffix="other", condition="", name="_other")

    def condition_edges(self, cond_cid, if_text, true_dst, false_dst):
        """Wire a Condition node's two outlets.

        ⚠️ The IF condition text lives on the **conditions_true edge's `condition`
        field** (name="_true") — NOT in a node message. The conditions_false edge
        is name="_false" with empty condition. (Putting the IF text only in a node
        message leaves the platform's IF box empty.) `if_text` must be non-empty."""
        if not (if_text and if_text.strip()):
            raise ValueError("Condition IF text must be non-empty "
                             "(it goes on the conditions_true edge's condition)")
        self.connect(cond_cid, true_dst, suffix="true", condition=if_text, name="_true")
        self.connect(cond_cid, false_dst, suffix="false", condition="", name="_false")

    # -- layout & output ------------------------------------------------------
    def _auto_layout(self):
        adj = {c["id"]: [e["nextComponentId"] for e in c["nextComponents"]]
               for c in self.components}
        depth = {}
        roots = [c["id"] for c in self.components if c["type"] == "Input"] or \
                ([self.components[0]["id"]] if self.components else [])
        frontier = [(r, 0) for r in roots]
        while frontier:
            nid, d = frontier.pop(0)
            if nid in depth and depth[nid] >= d:
                continue
            depth[nid] = d
            frontier.extend((m, d + 1) for m in adj.get(nid, []))
        # Platform cards are wide (~320px) and tall (collapsed config panels run
        # 300–450px), and a busy classifier fans many nodes into the same column,
        # so spacing must be generous or the imported canvas overlaps. Column and
        # row pitch are deliberately large.
        COL_W, ROW_H = 720, 600
        rows = {}
        for c in self.components:
            d = depth.get(c["id"], 0)
            if c.get("x") is None or c.get("y") is None:
                r = rows.get(d, 0)
                rows[d] = r + 1
                c["x"], c["y"] = COL_W * d, ROW_H * r

    def _assemble_messages(self):
        """Rebuild every prompt-bearing node's `messages` into the real export shape.

        Real schema: the array is always [Role, LongMemory, ShortMemory, Plugin,
        (Condition for Condition nodes), Input]; the prompt text lives in `text`
        (a `content` key is silently dropped → blank prompt). The trailing Input
        message's `upstream` is backfilled to the id of the node feeding this one,
        with a display label `name(title)` — matching what the platform emits."""
        upstream_of = {}
        for c in self.components:
            for e in c.get("nextComponents", []):
                nid = e.get("nextComponentId")
                if nid is not None and nid not in upstream_of:
                    upstream_of[nid] = c["id"]
        for c in self.components:
            raw = c.get("messages")
            if raw is None:
                continue

            def _txt(mtype):
                for m in raw:
                    if isinstance(m, dict) and m.get("type") == mtype:
                        return m.get("text") or m.get("content") or ""
                return ""

            # The Classifier (Branch) has no long-term memory and no plugins, so its
            # message array is the trimmed [Role, ShortMemory, Input]. Other
            # LLM-capable nodes use the full [Role, LongMemory, ShortMemory, Plugin, …].
            if c["type"] == "Branch":
                arr = [_msg("Role", _txt("Role")), _msg("ShortMemory")]
            else:
                arr = [_msg("Role", _txt("Role")), _msg("LongMemory"),
                       _msg("ShortMemory"), _msg("Plugin")]
            if c["type"] == "Condition":
                arr.append(_msg("Condition", _txt("Condition")))
            up = upstream_of.get(c["id"])
            label = ""
            if up is not None:
                u = self._by_id[up]
                label = f"{u['name']}({u.get('title') or u['name']})"
            arr.append(_msg("Input", label, upstream=up))
            c["messages"] = arr

    def build(self):
        self._auto_layout()
        self._assemble_messages()
        cfg = {"formatVersion": "1.0", "exportType": "BOT",
               "exportTime": int(datetime.now(timezone.utc).timestamp() * 1000),  # epoch ms (Long) — ISO strings are rejected on import
               "name": self.name, "botType": "Flow",
               "logo": DEFAULT_AGENT_LOGO,   # platform default avatar (override via top_fields logo=)
               # Anti-NPE backfill + real values: the import copies `multiModal` verbatim
               # with NO default (BotTransferService), and the console auto-save reads
               # multiModalForm.multiModalInput.chatMode WITHOUT a null check
               # (BotManageService:1538, regression 2025-12-02) → a .bot imported without a
               # non-null multiModalInput 500s on every auto-save. _DEFAULT_MULTIMODAL is a
               # known-good block copied verbatim from a real export (chatMode "Q_A", etc.) —
               # do NOT hand-edit the enum strings; override via top_fields multiModal={...}
               # only with values copied from another real export.
               "multiModal": _DEFAULT_MULTIMODAL}
        if self.description:
            cfg["description"] = self.description
        if self.brief_introduction:
            cfg["briefIntroduction"] = self.brief_introduction
        cfg.update(self.top_fields)
        cfg["humanConfig"] = self.human_config
        if self.key_event_config:
            cfg["keyEventConfig"] = self.key_event_config
        cfg["flowRule"] = {"components": self.components}
        return cfg

    def save(self, path, validate=True):
        """Write JSON; then run validate_gptbots_config.py (same dir) if present.
        Returns the validator's exit code (0 = pass)."""
        p = Path(path)
        p.write_text(json.dumps(self.build(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {p} ({len(self.components)} components)")
        validator = Path(__file__).resolve().parent / "validate_gptbots_config.py"
        if validate and validator.exists():
            return subprocess.run([sys.executable, str(validator), str(p)]).returncode
        return 0


# ---------------------------------------------------------------------------
def _demo(outdir):
    """Self-test: minimal but representative FlowAgent (classifier + KB + answer +
    gather + message + human + output, with exception edges). No Variable node:
    collect-complete routes straight to human handoff (the recommended pattern —
    Variable assignment needs pre-defined workspace attributes, see var_cfgs)."""
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    b = FlowAgentBuilder("Demo FlowAgent", description="demo")
    i = b.add("Input", "User Input")
    cl = b.add("Branch", "Intent Classifier", chatModelVersionId="", exceptionSwitch=True,
               **mem(short=True), **ke(2),
               prompt="Classify the message by intent. Judge with conversation "
                      "context: follow-ups about an unresolved issue belong to "
                      "that issue's branch.")
    ds = b.add("Dataset", "KB", **b.dataset_defaults())
    ans = b.add("LLM", "Answer", reads_kb=True, **b.llm_defaults(800),
                prompt="Answer strictly from the knowledge base content.")
    ga = b.add("ChatGather", "Collect", chatModelVersionId="", exceptionSwitch=True,
               **mem(short=True), gatherControl={"chatCountLimit": 6, "timeoutLimit": 10},
               gatherFields=gather_fields([("username", "The user's account name", True)]),
               prompt="Collect the required fields one by one. Collection "
                      "monopolizes the dialogue, so embed common how-to "
                      "guidance directly in this prompt.")
    ms = b.add("Message", "Handoff Notice", contentType="Text",
               content="Transferring you to a human agent, one moment please.")
    hm = b.add("Human", "Human Handoff")
    ot = b.add("Output", "Output")
    b.connect(i, cl)
    b.branch_edge(cl, ds, rule="The user is asking about product features, usage, or rules.",
                  name="faq")
    b.branch_edge(cl, ga, rule="The user describes a personal-account case that needs "
                               "back-office verification.", name="case")
    b.branch_other(cl, ms)   # classifier exception is via exceptionSwitch=True, not an edge
    b.connect(ds, ans, suffix="true"); b.connect(ds, ms, suffix="false")
    b.connect(ans, ot); b.connect(ans, ms, suffix="exception")
    b.connect(ga, ms, suffix="true")    # collect-complete → handoff (no Variable node)
    b.connect(ga, ms, suffix="false"); b.connect(ga, ms, suffix="exception")
    b.connect(ms, hm)
    return b.save(out / "demo-flowagent.bot")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--demo":
        sys.exit(_demo(sys.argv[2]))
    print(__doc__)
