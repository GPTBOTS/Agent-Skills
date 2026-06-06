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

## Edge handle conventions (frontend handle-connection-point.ts)

- Source handle prefix `right`, target prefix `left`, suffixed by node type in lowercase: e.g. `right<id>-llm` / `left<id>-condition`.
- The branch handles of `CONDITION`/`INTENT` come from each `conditionBranches[].sourceHandle` / `intents[].sourceHandle`, and must correspond to the edge's `sourceHandle`.

## Stripped/backfilled on import (follow when generating)

- Model version id (`chatModelVersionId`, etc.): leave blank/placeholder; the backend backfills the default model — **never invent real ids**.
- Cross-organization plugins, `dataGroupIds`/`databaseIds`/`databaseTableIds`, HTTP/plugin authentication: cleared on import. Either leave them blank, or fill in real ids queried via **this organization's public API**.
