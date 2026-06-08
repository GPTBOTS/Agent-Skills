# Create / optimize a GPTBots Workflow (.flow)

> Reference for the `GPTBots Skill` workflow when the target is a **Workflow**. Turn a piece of deterministic data-processing/orchestration logic (or a user-provided existing `.flow` file) into a **plaintext `.flow`** importable into the platform (`exportType=WORKFLOW`, `botType=Workflow`, config in `workflow`).

## Workflow

### 1. Requirements discussion
Clarify the input/output contract, the external APIs / datasets / knowledge bases to call, whether loops/batch/conditional branches are needed, and error handling. When optimizing, start from the `.flow` file the user provided; if they want to optimize but provided no file, ask them to export it from the platform first.

### 2. Node graph design (strictly follow the node spec)
Read `./workflow-nodes.md` (21 node types + required parameters + graph integrity + handle conventions). Be sure to:
- Exactly one `START` and one `END`; the whole graph is a DAG (acyclic); every node has `x`/`y`, a unique `id`/`name`.
- Every edge has 4 non-empty fields (`sourceNodeID`/`targetNodeID`/`sourceHandle`/`targetHandle`), with existing endpoints and no self-loops.
- `CONDITION` has exactly one `ELSE` with all branches connected; `INTENT` has all intents connected; `LOOP`/`BATCH` carry a `subWorkflow`.
- Each node type carries its corresponding `*Param` and required fields (HTTP `request.url`, CODE `code`+`language`, DATABASE `sqlQuery`…).

### 3. Reuse the existing public API to fetch real references
Use `Authorization: Bearer <API_KEY>` against the regional base URL `https://api-${endpoint}.gptbots.ai` (`sg` default, `jp`, `th`) to call `GET /v1/database/tables/page`, `/v1/bot/knowledge/base/page` to fetch real table/knowledge-base ids and write them into DATABASE/DATASET nodes; leave HTTP authentication blank (configured after import). **Never call internal/console APIs**.

### 4. Generate
- **Use the builder script instead of hand-writing JSON**: write a generation script that imports `WorkflowBuilder` from `../scripts/build_gptbots_workflow.py` — it auto-generates edge handles and layout, and `save()` runs the validator (pass `source_handle=` explicitly for CONDITION/INTENT branch edges, matching each branch's `sourceHandle`). Keep prompts as Python constants; regenerate from the script on every revision. (`python3 ../scripts/build_gptbots_workflow.py` prints usage; `--demo <dir>` emits a validated example.)
- Top level: `formatVersion`, `exportType=WORKFLOW`, `exportTime`, `name`, `botType=Workflow`, `workflow.workflowNodes[]`, `workflow.workflowEdges[]`.
- Leave model id blank (backend backfills); leave cross-organization references and authentication blank (cleared on import).
- A `NODE` reference in a node's `inputs[]` looks like `nodeId#name#id`, and the referenced node must be upstream.
- **Prompts decide runtime quality**: every `LLM` node's system prompt and every `INTENT` node's intent description is executed by an LLM on each run. Write them clear, concise, and precisely executable; scope each to its node's single job; and check all prompts in the workflow as a set for conflicts before delivery (see *Prompt quality for LLM-capable nodes* in SKILL.md).
- **Always (re)generate a mermaid flow diagram of the design** and write it into a `## Flow (mermaid)` section of an `overview.md` delivered next to the output file, so the design intent is reviewable.

### 5. Quality check (mandatory)
```
python3 ../scripts/validate_gptbots_config.py <name>.flow
```
Non-zero exit code → fix per the `path`/`fix` in `errors` → rerun, until it passes before delivery.

### 6. Delivery
Place the new/updated `.flow` file and its `overview.md` (including the mermaid diagram) in the current working directory and return their local paths (never overwrite the user's original file unless asked — deliver an updated copy alongside it). Then tell the user: on **www.gptbots.ai** (developer space), **Create Agent / Workflow → Import**, then select the file.

## References
- Node spec: `./workflow-nodes.md`
- Variable catalog: `./variables-reference.md`
- Public API: https://www.gptbots.ai/docs/api-reference/overview
