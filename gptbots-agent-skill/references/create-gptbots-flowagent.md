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
- Use If/Else (free) where appropriate; do not misuse Condition or Classifier (both are LLM-driven and consume LLM on every run).
- **`ChatGather` is LLM-driven and monopolizes the conversation while collecting.** Its prompt's field definitions + SOP alone drive both the asking and the extraction — no knowledge base involved. Critically, once collection starts the node **exclusively owns the dialogue** (platform behavior): mid-collection user questions ("怎么拿回执/怎么截图" and other how-to asks) can NOT be routed to knowledge search or any other component. So anticipate the help users will need to produce each field and **embed those short how-to guides directly in the ChatGather prompt**; never design a flow that assumes a Dataset/LLM fallback can answer during collection.
- **Prompts decide runtime quality**: the Classifier (`Branch`) and `Condition` are LLM-driven, just like `LLM` components — each `Branch` category rule and each `Condition` condition is a prompt the LLM executes on every run to route the message, so routing accuracy depends directly on how the rules are written. Make category rules mutually exclusive and unambiguous, with concrete examples of what belongs in each category when intents are easy to confuse.
- **Route with conversation context, not just the last message.** Follow-up messages are often fragments — emotion-only replies (an emoji, a sigh), short acknowledgments, "还是不行" — that are meaningless in isolation but perfectly clear given the issue under discussion. Enable short-term memory on the Classifier and state in the branch rules that fragmentary/emotional follow-ups to an unresolved issue belong to **that issue's business branch**, not the fallback/"无意义" branch; reserve the fallback for messages that stay off-topic even with context. A classifier that judges each message in isolation misroutes exactly the users who most need help — the ones still stuck after the first answer.
- **Key events (关键事件) give LLM-driven nodes long-term, cross-session business memory.** The platform auto-extracts business-valuable events from conversations into per-user structured records — customer-defined event type, summary, entities, status (`PENDING`/`IN_PROGRESS`/`RESOLVED`/`CLOSED`), priority, confidence — and injects recent events back into prompts. Classifier (`Branch`), `LLM`, and `Condition` components all support enabling key events in their memory settings (per-node switch + event-type selection + recent-event count, default 5; events are fetched once per session and shared across nodes), and If/Else can branch on key-event variables. Injection is implicit (auto-appended `## Recent Key Events`) or explicit via `{{key_event_<eventType>}}` placeholders. Design guidance:
  - Use key events where they earn their keep: when the user **switches topic and later returns**, or **follows up on a historical issue** from an earlier session — the event's type/status/progress lets routing and answers pick up where things left off instead of starting cold.
  - Enable only on nodes that genuinely need event context (answering, escalation/judgment nodes); blanket-enabling inflates every node's prompt with events it doesn't use.
  - The event-type dictionary is customer-defined (name + description, ~5–10 types) — the descriptions drive extraction accuracy, and renaming a type after launch orphans existing `{{key_event_<旧名>}}` references, so name types carefully up front.
  - Extraction is asynchronous (message-threshold / idle-timeout triggered), so treat events as auxiliary memory — never the source of truth for strict-consistency decisions.
  - Docs: https://www.gptbots.ai/zh_CN/docs/tutorial/bot/user-list/key-events Write them clear, concise, and precisely executable; scope each to its node's single job; and check the whole set (including the top-level identity prompt) for conflicting goals/tone/boundaries before delivery (see *Prompt quality for LLM-capable nodes* in SKILL.md).

### 3. Reuse the existing public API to fetch real references
Same as create-gptbots-agent: use `Authorization: Bearer <API_KEY>` against the regional base URL `https://api-${endpoint}.gptbots.ai` (`sg` default, `jp`, `th`) to call `GET /v1/bot/knowledge/base/page`, `/v1/database/tables/page`, etc., to fetch real ids and write them into Dataset/ToolApi/Workflow components; if not found, leave them blank. **Never call internal/console APIs**.

### 4. Generate
- **Use the builder script instead of hand-writing JSON**: write a generation script that imports `FlowAgentBuilder` (plus `role/user_input/kb_msg/cond_msg/mem/ke/gather_fields/var_cfgs` helpers) from `../scripts/build_gptbots_flowagent.py` — it auto-generates component ids, the strict edge handles (and rejects key-repeating suffixes that distort canvas lines), branch ids, and layout, and `save()` runs the validator. Keep the identity prompt / branch rules / gather SOPs as Python constants and factor repeated node shapes into helper functions; regenerate from the script on every revision. (`python3 ../scripts/build_gptbots_flowagent.py` prints usage; `--demo <dir>` emits a validated example.)
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
