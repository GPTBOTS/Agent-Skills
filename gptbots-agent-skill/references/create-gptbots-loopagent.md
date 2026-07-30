# Create / optimize a GPTBots LoopAgent (.bot)

> Reference for the `GPTBots Skill` workflow when the target is a **LoopAgent** (`botType=LoopAgent`, formerly `Claw`). Turn "scenario + requirements" (or a user-provided `.bot`) into an importable `.bot` with `exportType=BOT`.
> Runtime behaviour, gating rules and error codes live in `./loopagent-runtime.md` — read it before you design the config, because most LoopAgent capabilities are **silently gated** rather than validated.

## 1. What a LoopAgent is (and how that changes the config)

| | QuestionAnswer | FlowAgent | **LoopAgent** |
|---|---|---|---|
| Who picks the execution path | platform (retrieve → answer) | the builder (a fixed graph) | **the model, per message** |
| Execution | single-pass RAG | deterministic flow | **multi-round tool loop** (reason → act → observe) |
| Config lives in | flat bot fields | `flowRule` | **`clawRule`** |

You are **not drawing a flow**. You are giving the agent: an **identity** (persona) + a **set of capabilities** (knowledge / tools / tables / skills / handoff / sub-agent) + **guardrails** (loop limits). The model then decides, on every message, which of those to use and how many times.

Consequences for config authoring:
- There are no nodes, edges, branches or handles to design. The topology is **fixed**: 1 `ClawCenter` + 7 satellites, always the same ids.
- Almost all of the leverage sits in **one field** — the center's `persona` prompt — plus **which capabilities you switch on**.
- A capability that is "configured" but missing its resource (no knowledge base bound, no table picked, no webhook) produces a registered-but-broken tool. Prefer switching a satellite **off** over leaving it on and empty.

## 2. File shape

```jsonc
{
  "formatVersion": "1.0",
  "exportType": "BOT",
  "exportTime": 1765077600000,          // epoch MILLISECONDS, bare integer (Long)
  "name": "…", "botType": "LoopAgent",
  "logo": "/developer/static/images/avatar/default_avatar_202506131619.png",
  "prompt": "",                          // MUST stay empty — identity lives in clawRule (see §4)
  "chatModelVersionId": "",              // leave blank; backend backfills the default chat model
  "multiModal": {                        // mandatory (auto-save NPE guard, see SKILL.md)
    "multiModalInput": { "messageMode": "QUEUE" }
  },
  "shortTermMemory": true, "shortTermMemoryRound": 30,
  "longTermMemory": false, "memoryEnable": true,   // both meaningless for LoopAgent — keep the defaults
  "toolsEnable": true, "workflowEnable": false,
  "clawToolTraceRecentRounds": 1,        // [0,5]; full tool traces for the last N user rounds
  "clawRule": { "components": [ … ], "comments": [], "thumbnail": null },
  "privateSkills": []                    // agent-private skills carried inside the file (see §6)
}
```

`clawRule` is a `ClawFlow`: `{thumbnail, components[], comments[]}`. Each component is
`{type, id, name?, title?, x?, y?, content{}, nextComponents?[]}` — **`id` and `nextComponentId` are STRINGS here**, unlike FlowAgent where they are strict integers. `x`/`y` are not persisted (radial layout), leave them out.

### The fixed topology (ids are contractual — do not rename)

| # | id | type | purpose |
|---|---|---|---|
| — | `center` | `ClawCenter` | model + loop limits + the 3 editable prompts. **Mandatory.** |
| 0 | `keyEvent-1` | `ClawKeyEvent` | key-event (cross-session memory / ticket) switch |
| 1 | `handoff-1` | `Human` | human-handoff kill switch (real config is bot-level `humanConfig`) |
| 2 | `knowledge-1` | `Dataset` | knowledge bases + recall tuning |
| 3 | `skills-1` | `ClawSkill` | attached skills (`skillRefs`) |
| 4 | `tools-1` | `ToolApi` | plugin / MCP ids |
| 5 | `database-1` | `ClawDB` | data-table ids |
| 6 | `subagent-1` | `ClawSubAgent` | `spawn_subagent` switch + params |

Only the center carries `nextComponents` — seven edges, `id = "center->{satelliteId}"`, `nextComponentId = satelliteId`, `sort = 0…6` (integers, in the order above). Satellites must **omit** `nextComponents` entirely (the platform serializer drops empty lists; an empty `[]` is tolerated but off-contract).

## 3. Import-fatal invariants (the builder enforces these; the validator catches them)

- **`ClawCenter` is mandatory.** The engine's `fromBotFlow` throws `center node required` → runtime `40001 botRule invalid`. On import a rule without a center is silently replaced by the platform default topology, so your whole config is lost without an error. (`CLAW_CENTER_MISSING`)
- **Loop Control ranges are enforced on import**, not just in the UI — `ClawLoopControlValidator` runs on the import path and rejects the file with `PARAMETER_ERROR (40000)`: `maxTurns ∈ [1,100]`, `maxErrors ∈ [0,50]`, `maxBudgetInputTokens ≥ 0`, all **integers** (a float or a numeric string fails). (`CLAW_LOOP_RANGE`)
- **`clawRule.components` ≤ 64** — `ImportSecurityScanner` rejects larger files. The legal topology is 8. (`CLAW_TOO_MANY_COMPONENTS`)
- **`center.content.llm.baseUrl` must be `null` or a public `http(s)` URL.** Internal / loopback / link-local / cloud-metadata addresses are rejected as SSRF, and a non-http scheme is rejected too. Normally leave it `null`. (`CLAW_BASEURL_SSRF`)
- **`center.content.llm.model` is an AMH-gateway `model_version_id`** (24-hex opaque), *not* a readable model name — writing `"claude-sonnet-4-6"` produces a bot that cannot call the gateway, and LoopAgent does **not** support BYOK models. (`CLAW_MODEL_NAME_AS_ID`, warning)
- **A blank model is not backfilled** — unlike every other id in this file. `fixLoopAgentCenterModel` returns *early* when the id is blank (it only re-checks and replaces a **stale** id against the gateway catalogue), so an empty `llm.model` survives the import intact: the agent then fails the first frame with `50101 No LLM credentials`, and when you import into an **existing** LoopAgent it silently **wipes the model that target already had**. Carry the id over from an export of the target, or tell the user to re-pick the model in the console and publish again. (`CLAW_MODEL_EMPTY`, warning)
- **Environment-bound ids are cleared or filtered on import.** `Dataset.docGroupIds` and `ClawDB.tableIds` are emptied when importing as a new Agent; `ToolApi.pluginIds` is filtered to plugins that exist and belong to the target org; `skillRefs` pointing at skills that cannot be resolved are dropped. Ship them **empty** and tell the user to bind resources after import. (`CLAW_ENV_REFS`, warning)
- **`prompt` (top level) must be empty.** The identity that actually runs is `clawRule` → `center.content.prompts.persona`. A top-level prompt on a LoopAgent is dead text that misleads whoever reads the file next. (`CLAW_TOP_LEVEL_PROMPT`, warning)
- **Empty prompt string means "use the engine default".** `null` / `""` / whitespace → the engine falls back to its built-in text. Never paste an engine default back into the field: it freezes today's wording into the bot and blocks future platform improvements.
- **`multiModal.multiModalInput` must be present** (shared auto-save NPE guard). For LoopAgent also set `messageMode` — `QUEUE` (default: queued messages merge into one reply at the turn boundary) or `APPEND` (steering: queued text is absorbed at the next round). (`L0_MULTIMODAL_AUTOSAVE_NPE`, `CLAW_MESSAGE_MODE`)
- **`clawToolTraceRecentRounds ∈ [0,5]`**, default `1`. It is counted in *user rounds*, independent of `shortTermMemoryRound`. `0` = older rounds keep only the plain Q/A text (the model can no longer see which tool it called or with what arguments). (`CLAW_TOOL_TRACE_ROUNDS`)

## 4. The persona prompt (where almost all the quality lives)

`center.content.prompts.persona` is the **only** editable prompt on a LoopAgent. The sibling keys `style` and `routing` still exist on the wire, but their console entry points were removed — treat them as platform-managed and always leave them empty. Everything else (loop discipline, tool guidance, key-event policy, runtime env) is engine text you cannot override either.

Everything you want the agent to be and to do goes in **`persona`**, the identity prompt shown in the platform's full-screen editor:

- **Identity** — who the agent is, what product and market it serves, language policy.
- **Boundaries** — what it must never do, what needs identity verification, where it must escalate.
- **How to handle each kind of message** — when to search knowledge, query a data table, open a key event, hand off to a human. Write it as guidance, not as a dispatcher that must emit JSON.
- **Reply style** — length, tone, formatting, phrasing conventions.

Give it headed sections (`# Role`, `# Boundaries`, `# How to handle a message`, `# Reply style`) so a long persona stays navigable for whoever edits it next.

Writing rules (in addition to *Prompt quality for LLM-capable nodes* in SKILL.md):
- **Persona is shared with sub-agents.** Anything you write as "you are the customer's first contact" also lands inside a background sub-agent. Write role/boundaries/language, not turn-taking choreography.
- **Never reference per-turn-changing variables in `persona`.** It is the first segment of the model's stable cache prefix; a value that changes every turn (online duration, message count, timestamps) invalidates the prefix cache on every message → slower and materially more expensive.
- **Leaving `persona` empty is legal**, and the engine ships no built-in persona — an empty persona simply injects no identity section. It is not a validation error.
- **Tell the agent when to read deeply.** The `read_source_document` tool (full / grep read of a retrieved document) is under-triggered by default; a sentence in `persona` about reading the whole document when recall is thin measurably improves answers.
- Keep the prompt in a `prompts/` folder (`persona.md`) and load it with `load_prompts("prompts/")`, exactly like every other bot type in this skill.
- **Do not write into `style` or `routing`.** The wire still carries those keys and the engine still reads them, but the console removed their entry points, so any text there shapes behaviour no operator can review, edit or reset. The builder always emits them empty and the validator warns (`CLAW_PROMPT_NO_UI`) when it finds content. Everything they used to hold belongs in `persona`.

## 5. Wiring capabilities (satellite by satellite)

| capability | where it is configured | notes |
|---|---|---|
| Knowledge | `Dataset` satellite: `docGroupIds`, `matchDataLimit` (1–50, default 5), `docCorrelation` (0–1, default 0.8), `searchMode` (`mix`/`semantics`/`keyword`), `embeddingRate` (default 0.7), `rerankSwitch`/`rerankModelVersionId`, `graphEnable`/`graphHopLimit` (1–5), `metadataFilter[]` + `metadataFilterLogic` (`AND`/`OR`) | Tools `knowledge_search` + `read_source_document` appear **only if ≥1 knowledge base is bound**. `groupIds` is a hard boundary for the model; `topK`/`docCorrelation` are model-adjustable. Recall list needs bot-level `showDocCorrelation`; inline `[N]` citations additionally need `dataSourceShowType = CORNER_SHOW`. Retired keys (`customKnowledgeType`, `enhancementMessageSwitch`, `docCorrelationSwitch`, `noCorrelationResponse`) are read-tolerated — do not write them. |
| Data tables | `ClawDB` satellite: `tableIds` | Gives `query_data_table` (NL→SQL, the model never writes SQL) **and** `generate_chart`, which appear together. **Bot-level `databaseTableIds` is a no-op for LoopAgent** — a common mistake. `generate_chart` requires a successful `query_data_table` earlier *in the same turn*. |
| Tools / MCP | `ToolApi` satellite: `pluginIds` + bot-level `plugins[]` (authoritative once populated) | A leading `-` on an id marks "attached but disabled". Credentials never leave Java, so leave plugin auth blank. Requires bot-level `toolsEnable`. |
| Workflows | bot-level `workflowEnable` + `associatedWorkflows[]` | Each **published** workflow becomes a `wf_<name>` tool. Three silent preconditions — see `./loopagent-runtime.md` §Workflow. |
| Skills | `ClawSkill` satellite: `skillRefs[]` (≤10) `{skillId, enabled, source:"SYSTEM"\|"ORGANIZATION"}`, plus `privateSkills[]` at top level | LoopAgent-only capability. An unknown `source` value makes the whole row malformed and it is dropped. See §6. |
| Handoff | bot-level `humanConfig` (shared with FlowAgent) + `Human` satellite `{enabled}` | `humanConfig.enable` is authoritative and overwrites the satellite flag every turn. Off → `manual_service` is not registered at all, so you do **not** need prompt text saying "human service is unavailable". Trigger timing is `humanConfig.triggerTips`. |
| Key events | bot-level key-event config (recorder switch + type catalogue) | **Double gate**: the switch must be on *and* at least one event type must exist, otherwise none of `create/update/query_key_event` is registered. The satellite's `keyEventTypes` is no longer read. Only `enabled`, the type catalogue and `defaultSeverity` change behaviour. |
| Sub-agent | `ClawSubAgent` satellite: `{enabled, parallelCount 1–5, triggerPrompt}` | Ships **off** by default. `parallelCount` is a per-turn spawn cap, **not** real concurrency (execution is serial). `maxWaitMinutes` is a dead field. |

**Model capability gate:** if the selected brain model does not declare tool-calling support, Tools / Workflow / Database / Human are all disabled in the UI. Nothing in the file can work around that — pick a tool-capable model.

**Fields that look configurable but do nothing** (do not spend effort on them, and do not promise them to the user): `ClawKeyEvent.titleStrategy`, `.autoCreateOnSpawn`, `.autoResolveIdleDays`, `.slaHighMs`, `.slaNormalMs`, `.keyEventTypes`, `.triggerPrompt`; `ClawSubAgent.maxWaitMinutes`; `center.llm.fallbackModel` is persisted for UI parity and consumed only as a degradation fallback, never as load balancing.

## 6. Skills carried inside the `.bot`

- `privateSkills[]` (top level) carries **agent-private** skills in full: `{skillId, name, displayName, description{locale:text}, version, enable, securityLevel, skillMdContent, files[{path, content/url, size}]}`. On import they are rebuilt as new private skills of the target bot and `skillRefs` are remapped to the new ids (with `source` rewritten to `ORGANIZATION`).
- Organization / platform skills are **not** embedded — only their id survives in `skillRefs`, and the import drops refs the target org cannot see.
- Limits enforced by the import scanner: ≤50 private skills, ≤5 MB per file, ≤5 M characters of `SKILL.md`, name ≤500 chars, ≤20 description locales.
- A skill with a blank `skillMdContent` is silently dropped at runtime (`blank SKILL.md content — dropped`). Skill names are case-sensitive and de-duplicated first-wins.
- Unless the user explicitly asked to transfer skills, ship `privateSkills: []` and `skillRefs: []`.
- **Re-importing the same file creates another copy of each embedded skill.** Import-as-version appends a version snapshot when the source `skillId` already belongs to the target, and otherwise creates a *new* private skill. A generated `.bot` carries a synthetic `skillId` that never belongs to the target, so every re-import adds one more private skill (runtime de-duplicates by name, first-wins, so the agent still behaves — it is clutter, not breakage). When you iterate on a `.bot`, tell the user to delete the stale copies in the console, or take the `skillId` the target actually assigned from an export and reuse it so later imports append versions instead.

## 7. Generate with the builder

Do not hand-write the JSON. Use `../scripts/build_gptbots_loopagent.py`:

```python
from build_gptbots_loopagent import loopagent_config, save
from gptbots_prompts import load_prompt_store

P = load_prompt_store("prompts/")            # persona.md
cfg = loopagent_config(
    "Support LoopAgent",
    persona=P.require("persona"),
    max_turns=25, max_errors=5, max_budget_input_tokens=0,
    knowledge=True,                # keep the Dataset satellite on (ids bound after import)
    database=False, tools=True, subagent=False,
    handoff=True, key_event=True,
    message_mode="QUEUE", tool_trace_recent_rounds=1,
)
save(cfg, "support-loopagent.bot")           # writes the file and runs the validator
```

Run the builder with no arguments to print full usage, or `--demo <dir>` for a validated working example.

## 8. Quality check (mandatory)

```
python3 ../scripts/validate_gptbots_config.py <name>.bot
```
Exit code must be 0 before delivery. Fix per the reported `path` / `fix` and rerun.

## 9. Delivery

Place the `.bot` (and its `prompts/` folder and generation script) in the working directory and return the paths. Then tell the user:
- **Manual:** developer space → **Create Agent → Import** → select the file.
- **API (test-mode target only):** `python3 ../scripts/publish_gptbots.py <file> --api-key <key>` (add `--release` only if they explicitly want to go live).
- **Always say this:** importing/saving only updates the **Debug** version. Until the user clicks **Publish / Release**, every production channel (Open API, share page, widget, LiveChat, Telegram, LiveDesk…) keeps running the previous snapshot — and a LoopAgent that has never been published fails on those channels with `AGENT_WORKFLOW_PUBLISHED_NOT_EXIST`.
- Remind them to bind the environment-specific resources the import cleared: knowledge bases, data tables and plugins.
- **If the file's `llm.model` is blank, say so explicitly**: the agent has no brain model until someone picks one (设置页 → 智能体大脑 → 模型) and publishes again. Until then every message returns `50101`. This is the single most common way a correctly-imported LoopAgent is dead on arrival.

## References
- Runtime semantics, gating checklists, error codes: `./loopagent-runtime.md`
- Referenceable variables: `./variables-reference.md`
- Material → mechanism mapping: `./materials-mapping.md`
- Public API playbooks: `./call-gptbots-api.md`
