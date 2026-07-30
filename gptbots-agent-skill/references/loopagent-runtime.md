# LoopAgent runtime semantics, gating & troubleshooting

> Companion to `./create-gptbots-loopagent.md`. Read this when you are **designing** a LoopAgent config (most capabilities are silently gated — a wrong assumption produces a bot that looks configured and does nothing) or when the user reports that a live LoopAgent misbehaves.

## 1. Mental model

Three processes, one conversation:

- **Java control plane** — session lock, per-turn injection of config + credentials + history, billing, rate limiting, the event bus, and **all tool execution**. All state lives here (Mongo / Redis).
- **Node engine** — stateless. Every turn it receives the config (`clawRule`), variables, the short-term memory window and short-lived LLM credentials, runs a bounded `reason → act → observe` loop, and calls back into Java. It stores nothing, so consecutive messages may land on different replicas without losing memory.
- **AMH LLM gateway** — every model call. **No BYOK**: LoopAgent only sees platform models. Gateway unconfigured → `50101 No LLM credentials` on the first frame.

Two levels of "turn": one **message turn** (1 user message → 1 agent reply) contains many engine **rounds** (one LLM call each, capped by `maxTurns`).

Replies do **not** come back on the request. `POST /v2/claw/execute` returns a single terminal JSON (tokens / `finishReason` / usage) used to release the lock and settle billing; the actual text, tool cards, recall lists and charts are pushed to a conversation-level SSE stream (`/conversations/{cid}/events`) with cursor-based resume. "Process messages don't show up" is therefore an event-bus/subscription problem, not an execute problem.

A single turn may legitimately run **~10 minutes** (engine read timeout 300 s ×2 → event-bus terminal wait 720 s → task timeout 900 s → session lock TTL 16 min). Do not judge it by normal-Agent latency.

## 2. Stop conditions (`finishReason`)

| value | meaning | what to do |
|---|---|---|
| `end_turn` | model stopped calling tools | normal |
| `max_turns` | hit `maxTurns` (default 25) without finishing | tool loop, or genuinely complex task → raise the limit or find the stuck tool |
| `max_errors` | **consecutive** tool errors hit `maxErrors` (default 5); one success resets the counter | not LLM errors |
| `max_budget` | cumulative input tokens hit `maxBudgetInputTokens` | `0` = unlimited (default) |
| `refusal` | model refused | content policy |
| `aborted` | user pressed stop | billed for rounds already run |

Two hidden behaviours: an empty `end_turn` from the gateway is retried once automatically; and a single user input estimated at >60 % of the input budget is rejected before the loop with *"Prompt too large… Save the content to a file"* — that is a hard guard, not a bug.

## 3. Save vs Publish (the single most common support ticket)

**Saving only updates the Debug version. Only Publish / Release changes what customers get.**

- **Debug** (debug chat; conversation type WEB / null / CHAT) reads the **live** `clawRule` — saving takes effect immediately.
- **Production** (Open API, share page, Embed, Widget, LiveChat, Telegram, Slack, LiveDesk…) reads the **snapshot frozen at the last publish**.
- A LoopAgent that was never published fails on every production channel with `AGENT_WORKFLOW_PUBLISHED_NOT_EXIST`.

| object | ships with publish? |
|---|---|
| persona / loop limits / model / satellite switches (everything in `clawRule`) | **yes** |
| skill *attachment* (`skillRefs`), tool / KB / table / workflow bindings, handoff switch | **yes** |
| **agent-private** skill body (`SKILL.md`) | **yes** — same rule as persona |
| **organization / platform** skill body | **no** — saving is instantly global |
| knowledge-base document content, key-event data, user-property values | **no** — runtime data, instantly global |

Also: the persona editor's **draft** (autosaved while typing) is visible to nobody but the editing member — not even debug chat. "I changed it and nothing happened" is usually an unsaved draft, then an unpublished save. Restoring a version only reloads it **into the draft**; it must still be saved.

## 4. Why a tool "doesn't exist" — gating checklists

Every one of these fails **silently**: the tool simply is not registered, and the model answers as if the capability never existed.

**Knowledge (`knowledge_search`, `read_source_document`)** — at least one knowledge base bound to the bot. Recall tab needs *show source* on; inline `[N]` citations additionally need source style = `CORNER_SHOW`. Sub-agent recalls never render a recall tab. `groupIds` outside the whitelist → `KB_GROUP_NOT_ALLOWED` (the model is handed the allowed list and self-corrects). Zero hits is a **success** with a "retry with a lower threshold" hint, not an error.

**Data table (`query_data_table`, `generate_chart`)** — tables must be picked in the **ClawDB satellite**; bot-level `databaseTableIds` is a no-op. Both tools appear together; there is no separate chart switch. `generate_chart` requires a successful `query_data_table` **in the same turn** (else `CHART_NO_DATA`). The model text is capped at 50 rows; the front-end table card gets all rows.

**Tools / MCP** — bot-level `toolsEnable` on; plugin bound to the bot and enabled; the specific action not disabled at plugin or bot level; MCP tool not excluded by the whitelist. A broken plugin manifest only skips itself. When total tools (plugins + MCP + workflows) ≤ 30 they are all inlined eagerly and **`tool_search` does not appear** — that is expected, not a defect. Tool errors come back as HTTP 200 with `success:false` and a `[TOOL_ERROR]` card, truncated to 500 chars; the turn continues.

**Workflow (`wf_<name>`)** — three silent preconditions: bot `workflowEnable` on, the workflow associated with the bot, **and the workflow published**. A draft-only workflow is skipped without a message; an edited-but-unpublished workflow runs its old published version. Write a real `introduction` on the workflow or the model will not find it via `tool_search`.

**Key events (`create/update/query_key_event`)** — double gate: the recorder switch on **and** ≥1 event type configured. Type strings must match the dictionary character for character (an empty dictionary instead accepts any type). Severity maps `low→LOW, normal→MEDIUM, high→HIGH, urgent→CRITICAL`. Up to 5 open events for the identified user are pre-injected into the system prompt each turn. LoopAgent writes events **synchronously during the conversation** (normal Agent / FlowAgent extract them asynchronously afterwards).

**Handoff (`manual_service`)** — `humanConfig.enable` is authoritative (the satellite flag is a lagging mirror). Result codes: `ok` / `transferred` / `already_active` (idempotent success) / `out_of_service` (the configured out-of-hours text is sent **verbatim** and the turn ends) / `not_ready` / `transfer_failed` (the agent explains and keeps serving). After a successful handoff the engine blocks every remaining tool call in the turn, and while a human session is active the engine is skipped entirely — the AI staying silent is expected. The `note` argument (≤2000 chars) is agent-visible only, generated live by the model, and is delivered on LiveChat / Intercom / LiveDesk / ZohoSalesIQ but **not** Omnichat / CrescendoLab / SoBot.

**Form collection (`collect_user_info`)** — only offered when the current channel can render a native form. It returns as soon as the form is **sent** (`form_sent`); it does not wait for the answer, which arrives later as an ordinary user message. Caps: 10 fields, 10 options per field, `fileLimit` 1–9. Titles and labels are generated per conversation by the model and cannot be edited in the console. Channel matrix: Web family + LiveDesk render natively; Telegram and LiveChat use a hosted page (requires `claw.form.hosted-page-url` pointing at a `/widget/` path — `/s/` is refused by `X-Frame-Options`); WhatsApp and anything unadapted fall back to plain-text, one field at a time. For attachments to be *understood* (not just stored as a URL) the bot's multimodal input must enable the matching category.

**Sub-agent (`spawn_subagent`)** — off by default. Fire-and-forget: it returns a task id immediately, the main turn continues, and the result is delivered on a later **sentinel round**, so it never appears in the same reply. Sub-agents never speak to the customer directly and cannot spawn further sub-agents.

## 5. Memory, context and burst messages

- **Short-term memory** is the only gate that matters: `shortTermMemory` (rounds default 30, clamped 1–200). `longTermMemory` / `memoryEnable` are meaningless for LoopAgent — do not diagnose from them.
- **`clawToolTraceRecentRounds`** (default 1, range 0–5) decides how many recent **user rounds** keep their full tool traces (`tool_use` + `tool_result`); older rounds degrade to plain Q/A text. If the model "forgets which tool it just called", raise it — 1–2 is usually enough, and higher values cost tokens fast.
- **Automatic context compaction** is non-blocking and silent: the oldest results of six read-only tools (`bash`, `knowledge_search`, `read_source_document`, `query_data_table`, `query_key_event`, `query_user_property`) are replaced with placeholders. Action tools are never cleared. "It forgot the long document it read earlier" → tell the model to search again.
- **Burst messages**: `QUEUE` (default) queues messages sent while a turn is running and merges them into **one** reply on a sentinel round after the turn ends — so "I sent three messages and only got one answer" is by design. `APPEND` absorbs them at the next round boundary inside the running turn, folding them into the reply already being generated. Queued message bodies are capped at 8192 characters.

## 6. Billing & quota

Credits are deducted from the gateway-reported `totalCredits` after the turn (never token × price locally), and settlement never blocks the reply. The balance gate runs **before** the turn — insufficient balance or member monthly cap → `COIN_NOT_ENOUGH` and the turn does not run. Plugin / MCP calls bill separately per action; workflow execution bills to the workflow's owning organization. Two reporting quirks worth quoting to users: main-turn charges are always bucketed as `CONSUME_GPT_3_5` regardless of the actual model (the amount is right, only the label is generic), and cache savings are folded into the total rather than itemised. Debug chat is a real turn and is billed. Table quota (`databaseTableLimit`, default 20) and API RPM are shared with regular Agents.

`BotMode` (`FORMAL` / `TEST`) is fixed at creation and cannot be changed — only `TEST` bots accept the Open-API agent update/publish calls (`403200 AGENT_NOT_TEST_MODE` otherwise). This is exactly what `scripts/publish_gptbots.py` needs.

## 7. Error codes

| code | meaning | cause / fix |
|---|---|---|
| `50101` | No LLM credentials (engine) | AMH gateway base-url/api-key missing, or the selected model id does not resolve in the gateway catalogue |
| `40001` (engine) | `botRule invalid` | `clawRule` missing the center node or structurally broken. **Java's 40001 is rate-limiting — different thing** |
| `40300` (engine) | ClawAgent disabled | `center.content.enabled = false` |
| `-50000` | InternalServerError wrapper | the real code is in `payload.originalCode`; tokens already spent are still billed |
| `COIN_NOT_ENOUGH` | balance gate | org balance or member monthly cap |
| `403200` | `AGENT_NOT_TEST_MODE` | Open-API update/publish against a `FORMAL` bot |
| `40343` | `TOOL_NOT_AVAILABLE` | tool/workflow not bound to the bot, or the master switch is off |
| `403215` | `SKILL_UPDATE_CONFLICT` | optimistic-lock conflict from concurrent skill editing — reload and retry |
| `SERVICE_NOT_READY` | table / chart LLM unavailable | two independent dictionaries: `CHAT_DATABASE_MODEL_VERSION` (query) and `CHAT_CHART_GENERATION_MODEL_VERSION` (chart) |
| `KB_GROUP_NOT_ALLOWED` | knowledge scope violation | the model passed group ids outside the whitelist; it is handed the allowed list and retries — not a fault |
| `CHART_NO_DATA` | nothing to chart | no successful `query_data_table` earlier in the same turn |
| `AGENT_WORKFLOW_PUBLISHED_NOT_EXIST` | never published | publish the bot once |

**Stream codes** (front-end render events): `3` text, `41` reasoning, `5`/`6` tool call / tool result (`[TOOL_ERROR]` prefix = failed), `1` recall tab, `20` inline citation (needs `CORNER_SHOW`), `36` handed to human, `0` turn end with usage, `-50000` error. LoopAgent emits no follow-up-suggestion event.

## 8. Symptom → first thing to check

| symptom | check |
|---|---|
| config / persona / knowledge change not visible to customers | §3 — saving only updates Debug; publish |
| production channel errors immediately | never published (§3) |
| no reply / error on the first frame, `50101` | AMH gateway or model id (§7) |
| can't add plugin / workflow / table / handoff, buttons greyed out | the selected brain model has no tool-calling capability |
| a tool "doesn't exist" | §4, per-capability checklist — all gates are silent |
| doesn't remember the previous turn | `shortTermMemory` switch, not `memoryEnable` (§5) |
| doesn't remember which tool it just called | `clawToolTraceRecentRounds` too low (§5) |
| several messages, one reply / stuck "queued" | by design (§5); if stuck, check session lock, sentinel-round cap (5), stop flag, pending queue |
| long silence before replying | a turn may legitimately run ~10 min (§1); read `finishReason` (§2) |
| chart/table produced but rendered as a plain tool card | `PLUGIN_ID_DATABASE` / `PLUGIN_ID_CHART_GENERATION` dictionaries not configured — the feature itself works |
| form not delivered / agent can't read the attachment | channel form support, hosted-page URL, bot multimodal input categories (§4) |

## 9. Diagnosing a specific live conversation

Use the *Agent ops diagnostics* playbook in `./call-gptbots-api.md`: find the conversation (`GET /v1/bot/conversation/page`), list messages (`GET /v2/messages`), then pull `GET /v1/bot/logtree/query?msgid=…` for the per-message execution trace. For a LoopAgent read the trace as a round sequence: which tools ran, which returned `[TOOL_ERROR]`, and what `finishReason` closed the turn — then loop back to the optimize-config workflow.
