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
    from build_gptbots_flowagent import FlowAgentBuilder, role, user_input, kb_msg, cond_msg, mem, ke

    b = FlowAgentBuilder("My Agent",
            description="…", human_config={"manufacturer": "LiveChat", "status": "enable"},
            key_event_config={  # bot-level key-event extraction (verify against a real export)
                "enable": True, "messageThreshold": 10, "idleTimeoutMinutes": 3,
                "recentEventCount": 5, "extractionRules": "…",
                "eventTypes": [{"name": "deposit", "description": "…"}]})
    i  = b.add("Input", "User Input")
    cl = b.add("Branch", "Intent Classifier", exceptionSwitch=True, chatModelVersionId="",
               **mem(short=True), **ke(2),
               messages=[role(CLASSIFIER_PROMPT), user_input()])
    ds = b.add("Dataset", "KB Search", **b.dataset_defaults())
    ans = b.add("LLM", "Answer", **b.llm_defaults(),
                messages=[role(ANSWER_PROMPT), kb_msg("KB Search"), user_input()])
    out = b.add("Output", "Output"); hm = b.add("Human", "Human Handoff")
    b.connect(i, cl)
    b.branch_edge(cl, ds, rule="The user is asking about product features...", name="features")
    b.branch_other(cl, hm)
    b.connect(cl, hm, suffix="exception", name="Exception")   # exceptionSwitch=True
    b.connect(ds, ans, suffix="true"); b.connect(ds, hm, suffix="false")
    b.connect(ans, out); b.connect(ans, hm, suffix="exception")
    b.save("my-agent.bot")
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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


# ---------------------------------------------------------------------------
# message / config factories (shapes observed in real platform exports)
# ---------------------------------------------------------------------------
def role(content):
    """System (Role) message carrying a prompt."""
    return {"type": "Role", "role": "system", "content": content}


def user_input():
    """Re-inject the user's original input (needed after replacement-type nodes)."""
    return {"type": "Input", "role": "user", "content": "{{start_msg_text}}"}


def kb_msg(kb_node_name, label="[Knowledge base content]"):
    """Inject an upstream Dataset node's retrieval result into an LLM's messages.
    Pass a localized `label` if the bot's prompts use another language."""
    return {"type": "Dataset", "role": "system", "content": label + ": {{" + kb_node_name + "}}"}


def cond_msg(text):
    """The If-condition text of a Condition component (must be non-empty)."""
    if not (text and text.strip()):
        raise ValueError("Condition If-text must be non-empty (canvas rejects it)")
    return {"type": "Condition", "role": "system", "content": text}


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


def gather_fields(fields):
    """ChatGather/FormGather fields from (name, description, required) tuples."""
    return [{"gatherType": "selfDefining", "name": n, "valueType": "string",
             "description": d, "isRequired": bool(req)} for (n, d, req) in fields]


def var_cfgs(pairs, operate="COVER"):
    """Variable component assignments from (name, value) pairs."""
    return [{"variableType": "USER_PROPERTY", "variableOperateType": operate,
             "variableName": k, "value": v} for (k, v) in pairs]


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
        self._branch_seq = int(time.time() * 1000)

    # -- components ---------------------------------------------------------
    def add(self, ctype, name, x=None, y=None, **fields):
        """Add a component; returns its int id. x/y optional (auto-layout in build())."""
        if ctype not in _TARGET_KEY:
            raise ValueError(f"unknown FlowComponentType {ctype!r} — use the enum value "
                             f"(Classifier→Branch, If-Else→Bool, Knowledge Search→Dataset, "
                             f"Card→Predefine, Tools→ToolApi, Human Service→Human)")
        cid = self._next_id
        self._next_id += 1
        comp = {"type": ctype, "id": cid, "name": name, "title": name,
                "x": x, "y": y, "nextComponents": []}
        comp.update(fields)
        self.components.append(comp)
        self._by_id[cid] = comp
        return cid

    @staticmethod
    def llm_defaults(max_tokens=1024, exception=True, short_memory=True, userprop=False):
        """Known-good baseline for an LLM component (merge, then add name/messages)."""
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

    def connect(self, src, dst, suffix="", condition="", name="", edge_id=None):
        """Add an edge src→dst with correct handles.
        suffix: '' (single-output success), 'true'/'false' (Dataset/Bool/Condition/
        ChatGather/FormGather), 'other' (Bool/Branch fallback), 'exception'
        (when exceptionSwitch=True), or a Branch branch-id (prefer branch_edge())."""
        scomp = self._by_id[src]
        if scomp["type"] in _TERMINAL:
            raise ValueError(f"{scomp['type']} #{src} is terminal — no outgoing edges")
        self._edge_seq += 1
        scomp["nextComponents"].append({
            "id": edge_id or f"edge_{self._branch_seq}_{self._edge_seq}",
            "nextComponentId": dst,
            "sourceHandle": self.sh(src, suffix),
            "targetHandle": self.th(dst),
            "condition": condition,
            "sort": len(scomp["nextComponents"]) + 1,
            "name": name,
        })

    def branch_edge(self, branch_cid, dst, rule, name="", branch_id=None, condition=None):
        """Add one Classifier (Branch) category edge.

        `rule` is the category's branch rule — a prompt the LLM executes to route
        each message. Make rules concrete and mutually exclusive, instruct routing
        by conversation context (fragmentary follow-ups → the ongoing topic's
        branch), and never leave one empty.
        sourceHandle becomes right{id}-branch_{branchId} (suffix = the id only).
        `condition` defaults to the rule text; real platform exports have also
        been observed carrying the branch id here — pass condition=branch_id to
        mirror a specific export's convention."""
        if not (rule and rule.strip()):
            raise ValueError("Branch category rule must be non-empty "
                             "(canvas rejects 'Cannot be empty' and the node is unusable)")
        self._branch_seq += 1
        bid = str(branch_id or self._branch_seq)
        self.connect(branch_cid, dst, suffix=bid,
                     condition=rule if condition is None else condition,
                     name=name, edge_id=f"branch_{bid}")

    def branch_other(self, branch_cid, dst, name="Other"):
        """The Classifier's fallback ('Other') edge — always connect it."""
        self._branch_seq += 1
        self.connect(branch_cid, dst, suffix="other", condition="", name=name,
                     edge_id=f"branch_other_{self._branch_seq}")

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
        rows = {}
        for c in self.components:
            d = depth.get(c["id"], 0)
            if c.get("x") is None or c.get("y") is None:
                r = rows.get(d, 0)
                rows[d] = r + 1
                c["x"], c["y"] = 440 * d, 240 * r

    def build(self):
        self._auto_layout()
        cfg = {"formatVersion": "1.0", "exportType": "BOT",
               "exportTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "name": self.name, "botType": "Flow"}
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
    gather + variable + message + human + output, with exception edges)."""
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    b = FlowAgentBuilder("Demo FlowAgent", description="demo")
    i = b.add("Input", "User Input")
    cl = b.add("Branch", "Intent Classifier", chatModelVersionId="", exceptionSwitch=True,
               **mem(short=True), **ke(2),
               messages=[role("Classify the message by intent. Judge with conversation "
                              "context: follow-ups about an unresolved issue belong to "
                              "that issue's branch."), user_input()])
    ds = b.add("Dataset", "KB", **b.dataset_defaults())
    ans = b.add("LLM", "Answer", **b.llm_defaults(800),
                messages=[role("Answer strictly from the knowledge base content."),
                          kb_msg("KB"), user_input()])
    ga = b.add("ChatGather", "Collect", chatModelVersionId="", exceptionSwitch=True,
               **mem(short=True), gatherControl={"chatCountLimit": 6, "timeoutLimit": 10},
               gatherFields=gather_fields([("username", "The user's account name", True)]),
               messages=[role("Collect the required fields one by one. Collection "
                              "monopolizes the dialogue, so embed common how-to "
                              "guidance directly in this prompt.")])
    va = b.add("Variable", "Save", variableSetValueConfigs=var_cfgs([("intent", "case")]))
    ms = b.add("Message", "Handoff Notice", contentType="Text",
               content="Transferring you to a human agent, one moment please.")
    hm = b.add("Human", "Human Handoff")
    ot = b.add("Output", "Output")
    b.connect(i, cl)
    b.branch_edge(cl, ds, rule="The user is asking about product features, usage, or rules.",
                  name="faq")
    b.branch_edge(cl, ga, rule="The user describes a personal-account case that needs "
                               "back-office verification.", name="case")
    b.branch_other(cl, ms)
    b.connect(cl, ms, suffix="exception", name="Exception")
    b.connect(ds, ans, suffix="true"); b.connect(ds, ms, suffix="false")
    b.connect(ans, ot); b.connect(ans, ms, suffix="exception")
    b.connect(ga, va, suffix="true"); b.connect(ga, ms, suffix="false")
    b.connect(ga, ms, suffix="exception")
    b.connect(va, ms, suffix="true"); b.connect(va, ms, suffix="exception")
    b.connect(ms, hm)
    return b.save(out / "demo-flowagent.bot")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--demo":
        sys.exit(_demo(sys.argv[2]))
    print(__doc__)
