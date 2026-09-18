# Inspect / update an exported GPTBots LoopAgent (.bot)

> Reference for an existing platform-exported **LoopAgent** (`botType=LoopAgent`, formerly `Claw`). This skill preserves `clawRule` and unrelated fields, and edits only requested, documented shared fields such as `humanConfig`, `customVariables` and `userProperties`. See `./bot-config-fields.md`.
> Do not synthesize a new `clawRule`, call `loopagent_config()` to replace it, or substitute a builder's default model. Without an existing export, ask the user to create/configure the LoopAgent in the platform and export it first.
> Sections 1–6 explain the existing schema and runtime for inspection; they do not authorize rewriting the rule during a shared-field update. Runtime behaviour, gating rules and error codes live in `./loopagent-runtime.md`.

## 1. What a LoopAgent is (and how that changes the config)

| | QuestionAnswer | FlowAgent | **LoopAgent** |
|---|---|---|---|
| Who picks the execution path | platform (retrieve → answer) | the builder (a fixed graph) | **the model, per message** |
| Execution | single-pass RAG | deterministic flow | **multi-round tool loop** (reason → act → observe) |
| Config lives in | flat bot fields | `flowRule` | **`clawRule`** |

You are **not drawing a flow**. You are giving the agent: an **identity** (persona) + a **set of capabilities** (knowledge / tools / tables / skills / handoff / sub-agent) + **guardrails** (loop limits). The model then decides, on every message, which of those to use and how many times.

Consequences for inspecting an export:
- There are no nodes, edges, branches or handles to design. The topology is **fixed**: 1 `ClawCenter` + 7 satellites, always the same ids.
- Almost all of the leverage sits in **one field** — the center's `persona` prompt — plus **which capabilities you switch on**.
- A capability missing its resource (no knowledge base bound, no table picked, no webhook) may be unavailable or fail at runtime. Report that condition; do not toggle unrelated satellites in the exported rule.

## 2. File shape

```jsonc
{
  "formatVersion": "1.0",
  "exportType": "BOT",
  "exportTime": 1765077600000,          // epoch MILLISECONDS, bare integer (Long)
  "name": "…", "botType": "LoopAgent",
  "logo": "/developer/static/images/avatar/default_avatar_202506131619.png",
  "prompt": "",                          // MUST stay empty — identity lives in clawRule (see §4)
  // NO chatModelVersionId (nor modelDynamicParams / creativityLevel / maxRespTokens /
  // reasoningEffort / showReasoning / reasoningEnabled / databaseTableIds): those belong
  // to the plain-Agent schema. A LoopAgent's model and sampling params live in clawRule's
  // ClawCenter content.llm, and the backend neither reads nor backfills the bot-level
  // copies on import. Writing "" into chatModelVersionId is what made share pages grey
  // out attachment upload — the detail API derived supportImageRecognition from it.
  // Backend exports omit all of them entirely. (`CLAW_PLAIN_AGENT_FIELD` — see §3)
  "multiModal": {                        // mandatory AND complete — a bare {"multiModalInput": {}}
    "multiModalInput": {                 // imports fine and then 500s/50000s at runtime
      "fileLimit": 1, "messageMode": "QUEUE"  /* + the rest of the known-good block */
    }
  },                                     // preserve the exported block and enum values
  "shortTermMemory": true, "shortTermMemoryRound": 30,
  "longTermMemory": false, "memoryEnable": true,   // both meaningless for LoopAgent — keep the defaults
  "toolsEnable": true, "workflowEnable": false,
  "clawToolTraceRecentRounds": 1,        // [0,5]; full tool traces for the last N user rounds
  "clawRule": { "components": [ … ], "comments": [], "thumbnail": null },
  "privateSkills": []                    // agent-private skills carried inside the file (see §6)
}
```

`clawRule` is a `ClawFlow`: `{thumbnail, components[], comments[]}`. Each component is
`{type, id, name?, title?, x?, y?, content{}, nextComponents?[]}` — **`id` and `nextComponentId` are STRINGS here**, unlike FlowAgent where they are strict integers. The platform uses a radial layout; preserve the exported representation, including any optional fields.

### The fixed topology (ids are contractual — do not rename)

| # | id | type | purpose |
|---|---|---|---|
| — | `center` | `ClawCenter` | model + loop limits + the persona prompt (the only editable one — see §4). **Mandatory.** |
| 0 | `keyEvent-1` | `ClawKeyEvent` | key-event (cross-session memory / ticket) switch |
| 1 | `handoff-1` | `Human` | human-handoff kill switch (real config is bot-level `humanConfig`) |
| 2 | `knowledge-1` | `Dataset` | knowledge bases + recall tuning |
| 3 | `skills-1` | `ClawSkill` | attached skills (`skillRefs`) |
| 4 | `tools-1` | `ToolApi` | plugin / MCP ids |
| 5 | `database-1` | `ClawDB` | data-table ids |
| 6 | `subagent-1` | `ClawSubAgent` | `spawn_subagent` switch + params |

Only the center carries `nextComponents` — seven edges, `id = "center->{satelliteId}"`, `nextComponentId = satelliteId`, `sort = 0…6` (integers, in the order above). Satellites must **omit** `nextComponents` entirely (the platform serializer drops empty lists; an empty `[]` is tolerated but off-contract).

## 3. Import invariants (inspect; do not reconstruct the rule)

- **`ClawCenter` is mandatory.** The engine's `fromBotFlow` throws `center node required` → runtime `40001 botRule invalid`. On import a rule without a center is silently replaced by the platform default topology, so your whole config is lost without an error. (`CLAW_CENTER_MISSING`)
- **Loop Control ranges are enforced on import**, not just in the UI — `ClawLoopControlValidator` runs on the import path and rejects the file with `PARAMETER_ERROR (40000)`: `maxTurns ∈ [1,100]`, `maxErrors ∈ [0,50]`, `maxBudgetInputTokens ≥ 0`, all **integers** (a float or a numeric string fails). (`CLAW_LOOP_RANGE`)
- **`clawRule.components` ≤ 64** — `ImportSecurityScanner` rejects larger files. The legal topology is 8. (`CLAW_TOO_MANY_COMPONENTS`)
- **`center.content.llm.baseUrl` must be `null` or a public `http(s)` URL.** Internal / loopback / link-local / cloud-metadata addresses are rejected as SSRF, and a non-http scheme is rejected too. Normally leave it `null`. (`CLAW_BASEURL_SSRF`)
- **`center.content.llm.model` is an AMH-gateway `model_version_id`** (24-hex opaque), *not* a readable model name — writing `"claude-sonnet-4-6"` produces a bot that cannot call the gateway, and LoopAgent does **not** support BYOK models. (`CLAW_MODEL_NAME_AS_ID`, warning)
- **A blank model is not backfilled — it is the one value you can never ship.** `fixLoopAgentCenterModel` returns *early* when the id is blank (it only re-checks and replaces a **stale** id against the gateway catalogue), so an empty `llm.model` survives the import intact: the agent then fails the first frame with `50101 No LLM credentials`, and when you import into an **existing** LoopAgent it silently **wipes the model that target already had**. (`CLAW_MODEL_EMPTY`, error)
- **Model lookup uses `agent_type=LOOP_AGENT`.** LoopAgent models are served by the **AMH LLM gateway**, and `GET /v1/model/list?org_id=…&agent_type=LOOP_AGENT` (account-level DevKey auth) returns gateway ids. An id from another agent type can be unreachable by that gateway. LoopAgent does not support BYOK models. For this update workflow:
  - **Shared-field update** → preserve the complete exported `clawRule`, including `center.content.llm.model`. No builder call or model fallback is needed.
  - **Missing/blank model or invalid rule** → report the validation failure and obtain a corrected platform export. Do not invent a replacement rule or model ID. Model lookup details are in `./org-devkey-api.md` §3.
- **No plain-Agent top-level fields.** `chatModelVersionId`, `modelDynamicParams`, `creativityLevel`, `maxRespTokens`, `reasoningEffort`, `reasoningEnabled`, `showReasoning` and `databaseTableIds` belong to the QuestionAnswer schema. The validator reports `CLAW_PLAIN_AGENT_FIELD` for these. If an existing file contains unrelated invalid fields, report them and obtain a corrected export rather than silently deleting them during a shared-field update.
- **Environment-bound ids are cleared or filtered on import.** `Dataset.docGroupIds` and `ClawDB.tableIds` are emptied when importing as a new Agent; `ToolApi.pluginIds` is filtered to plugins that exist and belong to the target org; unresolved `skillRefs` are dropped. Preserve these fields in the source rule and tell the user which bindings need checking after import. (`CLAW_ENV_REFS`, warning)
- **`prompt` (top level) must be empty.** The identity that actually runs is `clawRule` → `center.content.prompts.persona`. A top-level prompt on a LoopAgent is dead text that misleads whoever reads the file next. (`CLAW_TOP_LEVEL_PROMPT`, warning)
- **Empty prompt string means "use the engine default".** `null` / `""` / whitespace → the engine falls back to its built-in text. Never paste an engine default back into the field: it freezes today's wording into the bot and blocks future platform improvements.
- **`multiModal.multiModalInput` must be present** (shared auto-save NPE guard). For LoopAgent also set `messageMode` — `QUEUE` (default: queued messages merge into one reply at the turn boundary) or `APPEND` (steering: queued text is absorbed at the next round). (`L0_MULTIMODAL_AUTOSAVE_NPE`, `CLAW_MESSAGE_MODE`)
- **`clawToolTraceRecentRounds ∈ [0,5]`**, default `1`. It is counted in *user rounds*, independent of `shortTermMemoryRound`. `0` = older rounds keep only the plain Q/A text (the model can no longer see which tool it called or with what arguments). (`CLAW_TOOL_TRACE_ROUNDS`)

## 4. The persona prompt (inspection only in this workflow)

`center.content.prompts.persona` is the prompt exposed by the LoopAgent editor. Sibling keys `style` and `routing` can still exist on the wire without console entry points. Preserve all three as part of the original `clawRule` during a shared-field update. A request to change the persona or other rule content requires a platform edit and a fresh export for this workflow.

When inspecting a persona in the platform's full-screen editor, identify:

- **Identity** — who the agent is, what product and market it serves, language policy.
- **Boundaries** — what it must never do, what needs identity verification, where it must escalate.
- **How to handle each kind of message** — when to search knowledge, query a data table, open a key event or hand off to a human.
- **Reply style** — length, tone, formatting, phrasing conventions.

Runtime considerations when reading the existing persona:
- **Persona is shared with sub-agents.** Instructions addressed to the customer's first contact also reach background sub-agents, which matters when diagnosing their behaviour.
- **Per-turn-changing variables affect the persona cache.** The persona is the first segment of the model's stable cache prefix; changing timestamps or counters can invalidate that prefix on each message.
- **Leaving `persona` empty is legal**, and the engine ships no built-in persona — an empty persona simply injects no identity section. It is not a validation error.
- Keep the original export and a separate updated file as a revision trail. Validate that `clawRule`, including all prompt fields, is unchanged before delivery.
- The validator warns (`CLAW_PROMPT_NO_UI`) if `style` or `routing` contains text. Report the warning without clearing these unrelated fields.

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

**Model capability gate:** if the selected brain model does not declare tool-calling support, Tools / Workflow / Database / Human are all disabled in the UI. Report that limitation; a shared-field update does not replace the model.

**Fields that look configurable but do nothing** (do not spend effort on them, and do not promise them to the user): `ClawKeyEvent.titleStrategy`, `.autoCreateOnSpawn`, `.autoResolveIdleDays`, `.slaHighMs`, `.slaNormalMs`, `.keyEventTypes`, `.triggerPrompt`; `ClawSubAgent.maxWaitMinutes`; `center.llm.fallbackModel` is persisted for UI parity and consumed only as a degradation fallback, never as load balancing.

## 6. Skills carried inside the `.bot`

- `privateSkills[]` (top level) carries **agent-private** skills in full: `{skillId, name, displayName, description{locale:text}, version, enable, securityLevel, skillMdContent, files[{path, content/url, size}]}`. On import they are rebuilt as new private skills of the target bot and `skillRefs` are remapped to the new ids (with `source` rewritten to `ORGANIZATION`).
- Organization / platform skills are **not** embedded — only their id survives in `skillRefs`, and the import drops refs the target org cannot see.
- Limits enforced by the import scanner: ≤50 private skills, ≤5 MB per file, ≤5 M characters of `SKILL.md`, name ≤500 chars, ≤20 description locales.
- A skill with a blank `skillMdContent` is silently dropped at runtime (`blank SKILL.md content — dropped`). Skill names are case-sensitive and de-duplicated first-wins.
- Preserve `privateSkills` and `skillRefs` during shared-field updates. Do not clear existing skills or add new ones as a side effect.
- **Preferred way to give an existing LoopAgent a private skill: the API, not `privateSkills[]`.** `POST /v1/agent/skill/create` (that Agent's API Key with version-management permission, `../scripts/gptbots_agent_skill.py create <pkg>`) stores the skill once and returns a stable `skill_id`; reference it in `skillRefs[]` as `{skillId, enabled: true, source: "ORGANIZATION"}` and import the `.bot` as a new version. Later content changes go through `POST /v1/agent/skill/update --skill-id …` and reach the mounted skill without another Agent version — no duplicate copies. See `version-manage-api.md` §7.
- **Re-importing the same file creates another copy of each embedded skill.** Import-as-version appends a version snapshot when the source `skillId` already belongs to the target, and otherwise creates a *new* private skill. A generated `.bot` carries a synthetic `skillId` that never belongs to the target, so every re-import adds one more private skill (runtime de-duplicates by name, first-wins, so the agent still behaves — it is clutter, not breakage). When you iterate on a `.bot`, tell the user to delete the stale copies in the console, or take the `skillId` the target actually assigned from an export and reuse it so later imports append versions instead.

## 7. Update shared fields in an existing export

Start with the actual exported file and write to a separate output. For example, if the user explicitly asks to disable handoff tips:

```bash
jq 'if .botType == "LoopAgent" and (.clawRule | type) == "object"
    then .humanConfig.sendHumanTipSwitch = false
    else error("An existing platform-exported LoopAgent is required")
    end' existing-loopagent.bot > loopagent-updated.bot

cmp <(jq -S '.clawRule' existing-loopagent.bot) \
    <(jq -S '.clawRule' loopagent-updated.bot)
```

The comparison must succeed. Inspect the complete diff to confirm only the requested shared fields changed, then run the validator. Preserve an omitted `sendHumanTipSwitch` unless the user requested a value; a missing switch has different defaults on different handoff paths. Do not invoke the legacy LoopAgent builder or `--demo` to fill in a missing rule or model.

## 8. Quality check (mandatory)

```
python3 ../scripts/validate_gptbots_config.py <name>.bot
```
Exit code must be 0 before delivery. Fix reported fields within the requested scope and rerun; for unrelated rule failures, obtain a corrected platform export without rebuilding `clawRule`.

## 9. Delivery

Place the updated `.bot` beside the original export and return its path and the shared-field diff. Then tell the user:
- **Manual:** developer space → **Create Agent → Import** → select the file.
- **API (existing target):** `python3 ../scripts/publish_gptbots.py <file> --api-key <key>` — the key must be an API Key with **version-management permission**, created manually in the console (add `--release` only if they explicitly want to go live). See `./version-manage-api.md`.
- **API (brand-new Agent):** `python3 ../scripts/gptbots_org_api.py import-agent <file> --org <org_id>` with the account's DevKey/DevSecret — see `./org-devkey-api.md`.
- **Always say this:** importing/saving only updates the **Debug** version. Until the user clicks **Publish / Release**, every production channel (Open API, share page, widget, LiveChat, Telegram, LiveDesk…) keeps running the previous snapshot — and a LoopAgent that has never been published fails on those channels with `AGENT_WORKFLOW_PUBLISHED_NOT_EXIST`.
- Remind them to bind the environment-specific resources the import cleared: knowledge bases, data tables and plugins.
- State that the exported brain model and complete `clawRule` were preserved. If validation finds an invalid or blank model, do not deliver a supposedly working replacement; request a corrected platform export.

## References
- Runtime semantics, gating checklists, error codes: `./loopagent-runtime.md`
- Referenceable variables: `./variables-reference.md`
- Material → mechanism mapping: `./materials-mapping.md`
- Public API playbooks: `./call-gptbots-api.md`
- Model version ids, org resources, creating an Agent from a file: `./org-devkey-api.md`
- Updating / publishing / rolling back an existing Agent: `./version-manage-api.md`
