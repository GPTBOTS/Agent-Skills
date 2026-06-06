# Create / optimize a GPTBots FlowAgent (.bot, botType=Flow)

> Reference for the `GPTBots Skill` workflow when the target is a **FlowAgent (orchestrated agent, `botType=Flow`)**. Orchestrate the requirements into an AgentFlow built from components and connections, producing a **plaintext `.bot`** importable into the platform (`exportType=BOT`, `botType=Flow`, config in `flowRule`).

## Workflow

### 1. Requirements discussion
Clarify channels / materials / primary intents (mutually exclusive intents → Classifier=`Branch`, judging by content → `Condition`, judging by variable → If-Else=`Bool`) / data to collect (multi-turn → conversational collection, form → form collection, cross-turn memory → user attributes + variable assignment) / handoff method / boundaries. When optimizing, start from the `.bot` file the user provided; if they want to optimize but provided no file, ask them to export it from the platform first.

### 2. Component design (strictly follow platform rules)
Read `./flowagent-components.md` (capabilities/branches/connection rules for 14+ components) and `./variables-reference.md`. Be sure to:
- **Connect every meaningful branch**: knowledge search `no result`, Condition `else`, Classifier `other`, every `exception branch`.
- **Give every Classifier category a non-empty branch rule** (and every Condition a non-empty condition): the canvas rejects an empty rule with "Cannot be empty" and the node becomes unusable.
- Exactly one `Input` and one `Output`; `Output`/`Human Service` are terminal (no downstream).
- **Human Service nodes**: write `humanConfig` at the **component level** (not only bot-entity level), or the node config renders blank — see `./flowagent-components.md` → Human Service.
- `{{...}}` can only reference **upstream**; after replacement-type nodes (cards / LLM output), explicitly re-inject the original input with `{{start_msg_text}}` etc.
- Use If/Else (free) where appropriate; do not misuse Condition (consumes LLM).

### 3. Reuse the existing public API to fetch real references
Same as create-gptbots-agent: use `Authorization: Bearer <API_KEY>` against the regional base URL `https://api-${endpoint}.gptbots.ai` (`sg` default, `jp`, `th`) to call `GET /v1/bot/knowledge/base/page`, `/v1/database/tables/page`, etc., to fetch real ids and write them into Dataset/ToolApi/Workflow components; if not found, leave them blank. **Never call internal/console APIs**.

### 4. Generate
- Top level: `formatVersion`, `exportType=BOT`, `exportTime`, `name`, `botType=Flow`, `flowRule.components[]`.
- **Each component's `type` MUST be the `FlowComponentType` enum value, not the UI name** (e.g. Classifier→`Branch`, If-Else→`Bool`, Knowledge Search→`Dataset`, Card Message→`Predefine`, Tools→`ToolApi`, Human Service→`Human`). See the mapping table in `./flowagent-components.md`. A UI name like `"Classifier"` will fail import.
- Component `id` must be unique; `nextComponents[].nextComponentId` must point to an existing component.
- **Set each component's fields & enum values, and build connection handles correctly** — see *Per-component JSON fields & enum values* and *Connections & handles* in `./flowagent-components.md`. Every `nextComponents[]` edge needs `sourceHandle = right{thisId}-{key}[_suffix]` and `targetHandle = left{nextComponentId}-{key}` with keys matching each component type; a wrong handle id/key still imports but renders a **distorted/misrouted line** on the canvas. Any out-of-enum value (e.g. `contentType`, `reasoningEffort`) fails import.
- Leave model id blank (backend backfills); leave plugin/tool authentication and cross-organization references blank (cleared on import).
- **Always (re)generate a mermaid flow diagram of the design** and write it into a `## Flow (mermaid)` section of an `overview.md` delivered next to the output file, so the design intent is reviewable.

### 5. Quality check (mandatory)
```
python3 ../scripts/validate_gptbots_config.py <name>.bot
```
Non-zero exit code → fix per `errors` → rerun, until it passes before delivery.

### 6. Delivery
Place the new/updated `.bot` file and its `overview.md` (including the mermaid diagram) in the current working directory and return their local paths (never overwrite the user's original file unless asked — deliver an updated copy alongside it). Then tell the user: on **www.gptbots.ai** (developer space), **Create Agent / Workflow → Import**, then select the file.

## References
- Component spec: `./flowagent-components.md`
- Variable catalog: `./variables-reference.md`
- Material → mechanism: `./materials-mapping.md`
- Public API: https://www.gptbots.ai/docs/api-reference/overview
