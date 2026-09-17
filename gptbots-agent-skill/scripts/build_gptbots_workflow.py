#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workflow `.flow` builder (botType=Workflow). One of three generators:
  build_gptbots_agent.py     → QuestionAnswer .bot
  build_gptbots_flowagent.py → FlowAgent .bot
  build_gptbots_workflow.py  → Workflow .flow (this file)

Auto-generates edge handles in the real workflow convention — `source-{srcNodeId}`
/ `target-{dstNodeId}` (confirmed against a platform export; this is NOT the
FlowAgent `right{id}-{key}` form) — guards against self-loops/duplicate ids, and
auto-layouts nodes. Node `*Param` semantics come from `../references/workflow-nodes.md`;
`save()` runs `validate_gptbots_config.py` as the final gate.

Keep prompts / SQL / code as Python string constants in your generation script
and regenerate the .flow on every change — the script is the source, the file
is its build artifact.

CONDITION / INTENT branch edges: the edge's `source_handle` must equal the
branch's own `sourceHandle` from `conditionParam.conditionBranches[].sourceHandle`
/ `intentParam.intents[].sourceHandle` (an arbitrary unique string like
`source-<nodeId>-<rand>`; mint one with `branch_handle()`). The backend requires
EVERY branch/intent sourceHandle to have a connected outgoing edge. `target_handle`
is always `target-{dstNodeId}`.

Example
-------
    from build_gptbots_workflow import WorkflowBuilder
    w = WorkflowBuilder("My Flow")
    w.node("START", "start", "Start", outputs=[{"id": "q", "name": "q",
           "type": "STRING", "required": True, "desc": "input"}])
    w.node("HTTP", "http1", "Call API",
           httpParam={"request": {"url": "https://api.example.com/x", "method": "GET",
                                  "authentication": {}}},
           outputs=[{"id": "body", "name": "body", "type": "STRING"}])
    w.node("END", "end", "End", endParam={"outputType": "TEXT", "outputText": "{{body}}"})
    w.edge("start", "http1"); w.edge("http1", "end")
    w.save("my-flow.flow")
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Convenience re-export: keep long prompts in an external prompts.md / .json.
try:
    from gptbots_prompts import load_prompts, load_prompt_store  # noqa: F401
except ImportError:
    load_prompts = load_prompt_store = None


# Platform built-in workflow avatar — a blank/custom logo URL renders as a broken icon.
DEFAULT_WORKFLOW_LOGO = "/developer/static/images/avatar/default-workflow-avatar_1628.png"


def branch_handle(node_id, suffix):
    """Mint a CONDITION/INTENT branch sourceHandle: `source-{node_id}-{suffix}`.
    Use the SAME value in the branch param (conditionBranches[].sourceHandle /
    intents[].sourceHandle) and in the edge's source_handle."""
    return f"source-{node_id}-{suffix}"


class WorkflowBuilder:
    def __init__(self, name, logo=DEFAULT_WORKFLOW_LOGO):
        self.name = name
        self.logo = logo
        self.nodes = []
        self.edges = []
        self._by_id = {}
        self._edge_seq = 0

    def node(self, ntype, nid, name, x=None, y=None, desc="", inputs=None,
             outputs=None, **params):
        """Add a node. Pass its `*Param` as a keyword (e.g. httpParam={...});
        see workflow-nodes.md for which param each type requires."""
        if nid in self._by_id:
            raise ValueError(f"duplicate node id {nid!r}")
        n = {"id": nid, "name": name, "type": ntype, "x": x, "y": y, "desc": desc,
             "inputs": inputs or [], "outputs": outputs or []}
        n.update(params)
        self.nodes.append(n)
        self._by_id[nid] = n
        return nid

    def edge(self, src, dst, source_handle=None, target_handle=None, edge_id=None):
        if src == dst:
            raise ValueError("self-loops are rejected by the backend")
        for nid in (src, dst):
            if nid not in self._by_id:
                raise ValueError(f"edge references unknown node {nid!r} — add nodes first")
        self._edge_seq += 1
        self.edges.append({
            "id": edge_id or f"edge_{self._edge_seq}",
            "sourceNodeID": src,
            "targetNodeID": dst,
            "sourceHandle": source_handle or f"source-{src}",
            "targetHandle": target_handle or f"target-{dst}",
        })

    def _auto_layout(self):
        adj = {}
        for e in self.edges:
            adj.setdefault(e["sourceNodeID"], []).append(e["targetNodeID"])
        depth = {}
        roots = [n["id"] for n in self.nodes if n["type"] == "START"]
        frontier = [(r, 0) for r in roots]
        while frontier:
            nid, d = frontier.pop(0)
            if nid in depth and depth[nid] >= d:
                continue
            depth[nid] = d
            frontier.extend((m, d + 1) for m in adj.get(nid, []))
        # Generous pitch so wide/tall platform node cards don't overlap on import.
        COL_W, ROW_H = 640, 460
        rows = {}
        for n in self.nodes:
            d = depth.get(n["id"], 0)
            if n.get("x") is None or n.get("y") is None:
                r = rows.get(d, 0)
                rows[d] = r + 1
                n["x"], n["y"] = COL_W * d, ROW_H * r

    def build(self):
        self._auto_layout()
        return {"formatVersion": "1.0", "exportType": "WORKFLOW",
                "exportTime": int(datetime.now(timezone.utc).timestamp() * 1000),  # epoch ms (Long) — ISO strings are rejected on import
                "name": self.name, "botType": "Workflow", "logo": self.logo,
                "workflow": {"workflowNodes": self.nodes, "workflowEdges": self.edges}}

    def save(self, path, validate=True):
        p = Path(path)
        p.write_text(json.dumps(self.build(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {p} ({len(self.nodes)} nodes, {len(self.edges)} edges)")
        validator = Path(__file__).resolve().parent / "validate_gptbots_config.py"
        if validate and validator.exists():
            return subprocess.run([sys.executable, str(validator), str(p)]).returncode
        return 0


def _demo(outdir):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    w = WorkflowBuilder("Demo Workflow")
    w.node("START", "start", "Start",
           outputs=[{"id": "q", "name": "q", "type": "STRING", "required": True, "desc": "input"}])
    if_h = branch_handle("cond", "if")     # same value in the branch param AND the edge
    else_h = branch_handle("cond", "else")
    w.node("CONDITION", "cond", "Status Branch",
           conditionParam={"conditionBranches": [
               {"type": "IF", "priority": 1, "sourceHandle": if_h, "logicOperator": "AND",
                "conditions": [{"leftOperand": {"source": "NODE", "type": "STRING",
                                                "value": "start#q#q"},
                                "operator": "eq",
                                "rightOperand": {"source": "DIRECT", "type": "STRING", "value": "a"}}]},
               {"type": "ELSE", "priority": 2, "sourceHandle": else_h, "logicOperator": "AND",
                "conditions": []}]})
    w.node("TEXT_PROCESS", "tp_a", "Text A",
           textProcessParam={"mode": "JOIN", "joinText": "A:{{q}}"},
           outputs=[{"id": "t", "name": "t", "type": "STRING"}])
    w.node("TEXT_PROCESS", "tp_b", "Text B",
           textProcessParam={"mode": "JOIN", "joinText": "B:{{q}}"},
           outputs=[{"id": "t", "name": "t", "type": "STRING"}])
    w.node("VARIABLE_AGGREGATE", "agg", "Aggregate",
           variableAggregateParam={"strategy": "FIRST_NON_NULL", "groups": [
               {"groupName": "r", "groupType": "STRING", "variables": [
                   {"name": "t", "source": "NODE", "type": "STRING", "value": "tp_a#t#t"},
                   {"name": "t", "source": "NODE", "type": "STRING", "value": "tp_b#t#t"}]}]},
           outputs=[{"id": "r", "name": "r", "type": "STRING"}])
    w.node("END", "end", "End", endParam={"outputType": "TEXT", "outputText": "{{r}}"})
    w.edge("start", "cond")
    w.edge("cond", "tp_a", source_handle=if_h)     # edge handle == branch sourceHandle
    w.edge("cond", "tp_b", source_handle=else_h)
    w.edge("tp_a", "agg"); w.edge("tp_b", "agg"); w.edge("agg", "end")
    return w.save(out / "demo-workflow.flow")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--demo":
        sys.exit(_demo(sys.argv[2]))
    print(__doc__)
