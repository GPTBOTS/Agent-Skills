from __future__ import annotations

from .common import is_blank
from .constants import WORKFLOW_NODE_TYPES
from .model import JsonValue, Report
from .workflow_nodes import check_node_param


def check_workflow_graph(
    workflow: JsonValue,
    report: Report,
    base_path: str,
    inner: bool = False,
) -> None:
    if not isinstance(workflow, dict):
        report.err("WF_MISSING", base_path, "Missing workflow object")
        return
    nodes = workflow.get("workflowNodes") or []
    edges = workflow.get("workflowEdges") or []
    if not isinstance(nodes, list) or not nodes:
        report.err(
            "WF_NO_NODES",
            base_path + ".workflowNodes",
            "The workflow must have at least one node",
        )
        return

    names: list[JsonValue] = []
    node_ids: set[JsonValue] = set()
    for index, node in enumerate(nodes):
        node_path = f"{base_path}.workflowNodes[{index}]"
        if not isinstance(node, dict):
            report.err("WF_NODE_OBJ", node_path, "A node must be an object")
            continue
        node_id = node.get("id")
        node_type = node.get("type")
        if is_blank(node_id):
            report.err("WF_NODE_ID", node_path + ".id", "Node id cannot be empty")
        elif isinstance(node_id, (str, int, float, bool)):
            if node_id in node_ids:
                report.err(
                    "WF_NODE_ID_DUP",
                    node_path + ".id",
                    f"Duplicate node id: {node_id}",
                )
            node_ids.add(node_id)
        else:
            report.err("WF_NODE_ID", node_path + ".id", "Node id must be scalar")
        if is_blank(node_type):
            report.err("WF_NODE_TYPE", node_path + ".type", "Node type cannot be empty")
        elif not isinstance(node_type, str) or node_type not in WORKFLOW_NODE_TYPES:
            report.err(
                "WF_NODE_TYPE_INVALID",
                node_path + ".type",
                f"Invalid node type: {node_type}",
                "Use a WorkflowNodeType value: " + ", ".join(sorted(WORKFLOW_NODE_TYPES)),
            )
        name = node.get("name")
        if is_blank(name):
            report.err("WF_NODE_NAME", node_path + ".name", "Node name cannot be empty")
        elif name in names:
            report.err(
                "WF_NODE_NAME_DUP",
                node_path + ".name",
                f"Duplicate node name: {name}",
            )
        else:
            names.append(name)
        if node.get("x") is None or node.get("y") is None:
            report.err(
                "WF_NODE_XY",
                node_path,
                "Node is missing x/y coordinates (the backend import will reject it)",
                "Set x/y for every node",
            )
        check_node_param(node, node_path, report)

    starts = [node for node in nodes if isinstance(node, dict) and node.get("type") == "START"]
    ends = [node for node in nodes if isinstance(node, dict) and node.get("type") == "END"]
    if len(starts) != 1:
        report.err(
            "WF_START_COUNT",
            base_path,
            f"There must be exactly one START node (currently {len(starts)})",
        )
    if not inner and len(ends) != 1:
        report.err(
            "WF_END_COUNT",
            base_path,
            f"There must be exactly one END node (currently {len(ends)})",
        )

    out_degree: dict[JsonValue, int] = {}
    in_degree: dict[JsonValue, int] = {}
    edge_ids: set[JsonValue] = set()
    adjacency: dict[JsonValue, list[JsonValue]] = {}
    iterable_edges = edges if isinstance(edges, list) else []
    for index, edge in enumerate(iterable_edges):
        edge_path = f"{base_path}.workflowEdges[{index}]"
        if not isinstance(edge, dict):
            report.err("WF_EDGE_OBJ", edge_path, "An edge must be an object")
            continue
        edge_id = edge.get("id")
        if is_blank(edge_id):
            report.err("WF_EDGE_ID", edge_path + ".id", "Edge id cannot be empty")
        elif isinstance(edge_id, (str, int, float, bool)):
            if edge_id in edge_ids:
                report.err(
                    "WF_EDGE_ID_DUP",
                    edge_path + ".id",
                    f"Duplicate edge id: {edge_id}",
                )
            edge_ids.add(edge_id)
        source = edge.get("sourceNodeID")
        target = edge.get("targetNodeID")
        for field in ("sourceNodeID", "targetNodeID", "sourceHandle", "targetHandle"):
            if is_blank(edge.get(field)):
                report.err(
                    "WF_EDGE_FIELD",
                    f"{edge_path}.{field}",
                    f"Edge {field} cannot be empty",
                )
        source_exists = source in node_ids if isinstance(source, (str, int, float, bool)) else False
        target_exists = target in node_ids if isinstance(target, (str, int, float, bool)) else False
        if not is_blank(source) and not source_exists:
            report.err(
                "WF_EDGE_SRC",
                edge_path + ".sourceNodeID",
                f"The edge's source node does not exist: {source}",
            )
        if not is_blank(target) and not target_exists:
            report.err(
                "WF_EDGE_TGT",
                edge_path + ".targetNodeID",
                f"The edge's target node does not exist: {target}",
            )
        if not is_blank(source) and source == target:
            report.err("WF_EDGE_SELF", edge_path, f"Self-loops are not allowed: {edge_id}")
        if source_exists and target_exists:
            out_degree[source] = out_degree.get(source, 0) + 1
            in_degree[target] = in_degree.get(target, 0) + 1
            adjacency.setdefault(source, []).append(target)

    check_workflow_connectivity(nodes, node_ids, out_degree, in_degree, base_path, report)
    if has_cycle(node_ids, adjacency):
        report.err(
            "WF_CYCLE",
            base_path,
            "The workflow has a cycle (it must be a directed acyclic graph, DAG)",
        )
    for index, node in enumerate(nodes):
        if isinstance(node, dict) and node.get("type") in {"LOOP", "BATCH"}:
            subworkflow = node.get("subWorkflow")
            path = f"{base_path}.workflowNodes[{index}].subWorkflow"
            if not isinstance(subworkflow, dict):
                report.err(
                    "WF_SUBWORKFLOW",
                    path,
                    f"A {node.get('type')} node must contain a subWorkflow",
                )
            else:
                check_workflow_graph(subworkflow, report, path, inner=True)


def check_workflow_connectivity(
    nodes: list[JsonValue],
    node_ids: set[JsonValue],
    out_degree: dict[JsonValue, int],
    in_degree: dict[JsonValue, int],
    base_path: str,
    report: Report,
) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if node_id not in node_ids:
            continue
        node_type = node.get("type")
        name = node.get("name", node_id)
        if node_type == "START":
            if in_degree.get(node_id, 0) > 0:
                report.err("WF_START_IN", base_path, f"START should have no inbound edge: {name}")
            if out_degree.get(node_id, 0) == 0:
                report.err("WF_START_OUT", base_path, f"START must have an outbound edge: {name}")
        elif node_type == "END":
            if out_degree.get(node_id, 0) > 0:
                report.err("WF_END_OUT", base_path, f"END should have no outbound edge: {name}")
            if in_degree.get(node_id, 0) == 0:
                report.err("WF_END_IN", base_path, f"END must have an inbound edge: {name}")
        elif node_type == "COMMENT":
            if in_degree.get(node_id, 0) or out_degree.get(node_id, 0):
                report.err(
                    "WF_COMMENT_EDGE",
                    base_path,
                    f"A COMMENT node should have no edges at all: {name}",
                )
        else:
            if in_degree.get(node_id, 0) == 0:
                report.err("WF_NODE_NO_IN", base_path, f"Node is missing an inbound edge: {name}")
            if out_degree.get(node_id, 0) == 0 and node_type not in {
                "BREAK",
                "CONTINUE",
                "NEXT_LOOP",
            }:
                report.err("WF_NODE_NO_OUT", base_path, f"Node is missing an outbound edge: {name}")


def has_cycle(node_ids: set[JsonValue], adjacency: dict[JsonValue, list[JsonValue]]) -> bool:
    white, gray, black = 0, 1, 2
    colors = {node_id: white for node_id in node_ids}

    def visit(node_id: JsonValue) -> bool:
        colors[node_id] = gray
        for target in adjacency.get(node_id, []):
            if colors.get(target) == gray:
                return True
            if colors.get(target) == white and visit(target):
                return True
        colors[node_id] = black
        return False

    return any(colors[node_id] == white and visit(node_id) for node_id in node_ids)
