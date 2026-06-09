# GPTBots Workflow Node Reference (21 WorkflowNodeType)

> Used to generate `.flow` (`exportType=WORKFLOW`). A workflow is a DAG: `workflow.workflowNodes` + `workflow.workflowEdges`.
> Each node must carry its corresponding `*Param` (see the table below); missing it is rejected by the backend import/runtime validation. After generation you *must* run `../scripts/validate_gptbots_config.py`.
>
> **`workflowNodes[].type` must be one of these exact `WorkflowNodeType` enum values (case-sensitive)** — an unknown value fails import:
> `START, END, LLM, DATABASE, DATASET, AUDIO_LLM, INTENT, CODE, HTTP, CONDITION, COMMENT, TOOL_API, FILE_PARSE, TEXT_PROCESS, VARIABLE_AGGREGATE, LOOP, BATCH, NEXT_LOOP, CONTINUE, BREAK, SET_INTERMEDIATE_VARIABLE`.

## Graph integrity hard rules (backend WorkflowRuntimeChecker)

- Exactly one `START` and exactly one `END` (inner subworkflows are an exception).
- Every node: `id` non-empty and unique, `name` non-empty and unique, `type` valid, **must have `x`/`y` coordinates**.
- Every edge: `id` unique, `sourceNodeID`/`targetNodeID`/`sourceHandle`/`targetHandle` all non-empty, endpoints must exist, **no self-loops**.
- The whole graph must be a **DAG (acyclic)**.
- `START`: no inbound edge, ≥1 outbound edge; `END`: ≥1 inbound edge, no outbound edge; `COMMENT`: no edges at all; other nodes: ≥1 inbound and ≥1 outbound edge (`BREAK/CONTINUE/NEXT_LOOP` may have no outbound edge).
- `CONDITION`: `conditionParam.conditionBranches` non-empty and **exactly one `ELSE` branch**; every branch's `sourceHandle` must have an outbound edge.
- `INTENT`: `intentParam.intents` non-empty; every intent branch must be connected.
- `LOOP`/`BATCH`: must carry a `subWorkflow` (the subgraph recursively satisfies the same rules).

## Node types and required parameters

| Type | Required param | Key required fields | Notes |
|---|---|---|---|
| `START` | — (define the input schema in `outputs`) | outputs | Entry; only one |
| `END` | `endParam` | `outputType` (TEXT/VARIABLE); `outputText` when TEXT | Exit; only one |
| `LLM` | `llmParam` | `userPrompt`; `chatModelVersionId` may be blank (backend backfills) | `responseFormat` Text/JSON/NATIVE; `shortTermMemory`; `plugins[].pluginId` |
| `AUDIO_LLM` | `audioLlmParam` | `voice`, `userPrompt` | Audio LLM |
| `INTENT` | `intentParam` | `intents[]` (each with `sourceHandle`+`value`), `query` | Intent routing; `chatModelVersionId` may be blank |
| `CONDITION` | `conditionParam` | `conditionBranches[]` (with `IF`/`ELSE_IF`/`ELSE`, each `sourceHandle`), exactly one `ELSE` | Variable-based conditional branches |
| `CODE` | `codeParam` | `code`, `language` (PYTHON/JS) | Code node |
| `HTTP` | `httpParam` | `request.url` (no intranet/loopback IP), `request.method` | Put authentication in `authentication` (leave blank when generating, configure after import) |
| `DATASET` | `datasetParam` | `query`; `dataGroupIds` queried as real ids via this organization's API (otherwise blank) | Knowledge retrieval |
| `DATABASE` | `databaseParam` | `sqlQuery`, `databaseIds` (real ids or blank) | Dataset query |
| `TOOL_API` | `toolApiParam` | `toolId`/`toolApiId` (real ids of this organization) | Call a platform tool |
| `FILE_PARSE` | `fileParseParam` | `parseMode` (DEFAULT/HIGHLEVEL) | Document parsing |
| `TEXT_PROCESS` | `textProcessParam` | `mode` (SPLIT needs `splitTarget`+`delimiters` / JOIN needs `joinText`) | Text processing |
| `VARIABLE_AGGREGATE` | `variableAggregateParam` | `strategy`=FIRST_NON_NULL, `groups[]` (1–10) | Variable aggregation |
| `LOOP` | `loopParam` + `subWorkflow` | `loopType` (ARRAY_BASED needs `inputArrays` / LIMITED_LOOP needs `limitedLoopCount`); variable names must not use `index` and must not repeat | Loop |
| `BATCH` | `batchParam` + `subWorkflow` | `inputArrays` (must not use `index`) | Batch processing |
| `SET_INTERMEDIATE_VARIABLE` | `setIntermediateVariableParam` | Must be inside a LOOP; `assignments[].leftValue` is an intermediate variable of that LOOP | Set loop intermediate variable |
| `NEXT_LOOP` / `CONTINUE` / `BREAK` | — (inner workflow only) | Must not be inside a "partial parallel branch" | Loop control |
| `COMMENT` | `commentParam` | No edges | Comment |

## Variable references

- A node's input `inputs[]` uses `WorkflowVariableValue`: `source` (DIRECT/NODE/ENV/GLOBAL) + `value`.
- For a `NODE` source, `value` looks like `nodeId#variable_name#variable_id`; the referenced node must be **upstream** (no forward/cyclic references), and its `outputs` must contain that field.
- `GLOBAL`: system variables such as `sys.agent_id` / `sys.workflow_run_id` / `sys.user_id`.

## Edge handle conventions (confirmed against a real workflow export)

- A normal edge uses `sourceHandle: "source-<sourceNodeId>"` and `targetHandle: "target-<targetNodeId>"`. (This is the Workflow convention — it is **different** from the FlowAgent `right<id>-<key>` / `left<id>-<key>` form. Don't mix them up.)
- For a `CONDITION`/`INTENT` node, each branch/intent defines its own `sourceHandle` (an arbitrary unique string, e.g. `source-<nodeId>-<rand>`) in `conditionParam.conditionBranches[].sourceHandle` / `intentParam.intents[].sourceHandle`. The outgoing edge for that branch sets `sourceHandle` to **exactly that value** (targetHandle stays `target-<targetNodeId>`).
- **The backend requires every branch/intent sourceHandle to have a connected outgoing edge** (`WorkflowRuntimeChecker`: "must have all branches/intents connected"); the validator flags a missing one as `WF_COND_NOT_CONNECTED` / `WF_INTENT_NOT_CONNECTED`.
- The builder (`build_gptbots_workflow.py`) emits `source-`/`target-` automatically; use `branch_handle(node_id, suffix)` to mint a CONDITION/INTENT handle and pass the same value to both the branch param and `edge(source_handle=...)`.
- Graph rules enforced by `WorkflowRuntimeChecker` (and the validator): exactly one START / one END; START has out-edges and no in-edge; END has in-edges and no out-edge; COMMENT has no edges; BREAK/CONTINUE/NEXT_LOOP have in-edges and no out-edge; every other node ≥1 in and ≥1 out; unique node id/name; unique edge id; no self-loop; both endpoints exist; the graph is a DAG; LOOP/BATCH carry a `subWorkflow` that recursively satisfies the same rules.

## Per-node parameter rules (backend WorkflowNodeChecker — the validator enforces these)

- Each node must carry its required `*Param` (table above); the validator flags `WF_PARAM_MISSING`. (Exception: inner LOOP/BATCH sub-workflow `END` nodes may have a null `endParam`.)
- `CONDITION`: `conditionParam.conditionBranches` non-empty with **exactly one `ELSE`**; every branch `sourceHandle` connected (`WF_COND_ELSE` / `WF_COND_NOT_CONNECTED`).
- `INTENT`: `intentParam.intents` non-empty; every intent `sourceHandle` connected (`WF_INTENT_NOT_CONNECTED`).
- `HTTP`: `request.url` present and **not an internal/loopback host** (localhost/127.x/10.x/192.168.x/172.16–31.x/169.254.x/::1) on non-OP deployments (`WF_HTTP_INTERNAL_IP`).
- `VARIABLE_AGGREGATE`: `strategy` must be `FIRST_NON_NULL`; 1–20 groups; each group has a valid identifier `groupName` (`^[a-zA-Z_][a-zA-Z0-9_]*$`), a `groupType`, and 1–10 `variables` whose `type` equals the group type.
- `LOOP`/`BATCH`: `inputArrays` (and LOOP `intermediateVariables`) must not use the reserved name `index` and must not collide; the node must carry a `subWorkflow` (recursively validated).
- `SET_INTERMEDIATE_VARIABLE`: at least one `assignment`, each with a non-null `leftValue`; must live inside a LOOP whose `intermediateVariables` define that left value (the runtime checks the cross-level reference).
- `CODE` needs `code`; `DATABASE` needs `sqlQuery`; `TEXT_PROCESS`/`FILE_PARSE`/`TOOL_API`/`COMMENT` need their param.

Per-node functionality reference (official docs): https://www.gptbots.ai/zh_CN/docs/tutorial/workflow/node

## Stripped/backfilled on import (follow when generating)

- Model version id (`chatModelVersionId`, etc.): leave blank/placeholder; the backend backfills the default model — **never invent real ids**.
- Cross-organization plugins, `dataGroupIds`/`databaseIds`/`databaseTableIds`, HTTP/plugin authentication: cleared on import. Either leave them blank, or fill in real ids queried via **this organization's public API**.
