# Changelog

## 2026-08-26 (2.0.0)

Platform API update: the account-level (DevKey) resource APIs, Agent/Workflow version
publish & rollback, and a model-version-list that now covers LoopAgent. Sources:
`API Reference/{Account API, Agent API, Workflow API, Model API}` in the docs repo.

Major version: the skill now spans **two credentials** instead of one, and two pieces of
1.19.0 guidance are reversed rather than extended.

### Breaking / migration

- **`references/test-mode-update-publish.md` is gone** — replaced by
  `references/version-manage-api.md`. Anything (a prompt, a note, another skill) that
  pointed at the old filename must be repointed.
- **"Target must be in test mode" is no longer the rule for publishing.** The documented
  requirement is an API Key with **version-management permission**, granted only in the
  console. Workflows that assumed a test-mode target should now check the key instead;
  `403200` survives as a legacy row in the error table, not the headline.
- **"Don't look up a LoopAgent model id" is reversed.** `GET /v1/model/list` covers the AMH
  gateway behind `agent_type=LOOP_AGENT`; querying is now the expected path and the pinned
  `DEFAULT_CLAW_MODEL` is the fallback of last resort. The constant itself is unchanged, so
  existing configs keep working.
- **`publish_gptbots.py` gained modes.** The file argument is now optional because
  `--list-versions` and `--rollback` take its place; exactly one mode per call. Existing
  `publish_gptbots.py <file> --api-key … [--release]` invocations are unaffected.
- **New credential in play.** Creating anything on the platform needs an account
  DevKey/DevSecret pair, which earlier versions never asked for. Ask for it at call time —
  it is not interchangeable with an Agent API Key.

### Added

- **`references/org-devkey-api.md` — the account-level API family (new).** These use
  `Authorization: Basic base64(DevKey:DevSecret)`, an account credential distinct from the
  Agent/Workflow API Key, and are the only way to *create* things on the platform:
  `GET /v1/org/list`, `GET /v1/model/list`, Tool CRUD (`/v1/org/tool/{create,update,list,delete}`),
  MCP (`/v1/org/mcp/{create,refresh,delete}`), Skill
  (`/v1/org/skill/{create,import,import/url,list,delete}`), and Agent/Workflow creation from a
  file (`/v1/org/{agent,workflow}/import` + `/import/precheck`). Credentials are at
  https://www.gptbots.ai/developer/profile (Developer info) — link the user there rather than
  describing the navigation.

- **`scripts/gptbots_org_api.py` (new)** — stdlib-only client for all of the above:
  `orgs`, `models`, `tools`, `skills`, `create-tool`, `update-tool`, `create-mcp`,
  `refresh-mcp`, `create-skill`, `import-skill`, `import-skill-url`, `precheck-agent`,
  `import-agent`, `precheck-workflow`, `import-workflow`, and guarded `delete-*`
  (refuses without `--yes`). Credentials come from `GPTBOTS_DEV_KEY` / `GPTBOTS_DEV_SECRET`
  so they stay out of argv and shell history. `import-agent`/`import-workflow` run the
  precheck first and refuse an invalid file, print the one-time `api_key`, and warn that
  the key cannot publish.

- **Model version IDs are queryable, and workflow C3 in `SKILL.md` says to query them.**
  `GET /v1/model/list?org_id=…&agent_type=…` returns `modelId`, the stable model *version*
  ID that `chatModelVersionId`, FlowAgent/Workflow LLM nodes, and a LoopAgent's `clawRule`
  model all bind to (`aiModelVersion` is a display name and moves between releases).
  `agent_type` ∈ `AGENT` / `FLOW_AGENT` / `LOOP_AGENT` / `WORKFLOW`; `MULTI_AGENT` is not
  supported. `org_id` additionally returns the org's own configured models.

- **Version rollback and history in `publish_gptbots.py`:** `--list-versions` prints
  `version` / `version_status` / created / released / creator / desc from
  `/v1/{agent,workflow}/version/list`, and `--rollback <version>` calls
  `/v1/{agent,workflow}/version/rollback` (with `--new-version`, `--release`). Rollback
  **copies** the source version into a new one rather than moving a pointer, so history
  stays append-only and a revert is itself revertible. Import now surfaces the platform's
  `warning` field and says explicitly when a version was saved but not published.

- **`GET /v1/workflow/run/logs`** (workflow run list, keyed by the API key) added to the
  API catalog and the data-query playbook, including the traps: `input`/`output` come back
  as JSON *strings*, and `DEBUG` test runs are never returned.

### Changed

- **"Test mode" is no longer the gate on publishing — version-management permission is.**
  `references/test-mode-update-publish.md` → **`references/version-manage-api.md`**, rewritten
  around the documented requirement: `/v1/{agent,workflow}/version/{import,release,list,rollback}`
  authenticate with the target's own API Key and work **only if that key has version-management
  permission**, which can only be granted in the console (target → Integration/API → create an
  API Key with version management enabled). Two traps are now called out everywhere they matter: the key
  auto-created by the org import API comes back `version_manage_enabled: false`, and an
  ordinary chat key has no management permission either — both answer HTTP `403`. `403` is
  now the first row of the error table, and `403200` is documented as the legacy mode gate
  rather than the headline rule. `SKILL.md`, `publish_gptbots.py`, `loopagent-runtime.md`,
  `create-gptbots-loopagent.md` §9 and `create-gptbots-audioagent.md` updated to match.

- **LoopAgent model ids are now looked up, not guessed.** 1.19.0 said the model-version-list
  API does not cover the AMH gateway and told you not to try. It does now, behind
  `agent_type=LOOP_AGENT` — and that filter is *mandatory*: an id from an unfiltered listing
  or another `agent_type` is not routable and still produces `50101`. Preference order is now
  (1) the target's own id from its export, (2) a queried id, (3) the pinned
  `DEFAULT_CLAW_MODEL` fallback when there are no account credentials. Updated in
  `create-gptbots-loopagent.md` §3/§7/§9, `loopagent-runtime.md` (50101 row),
  `version-manage-api.md` §5, `build_gptbots_loopagent.py` (comment + both runtime notes),
  `validate_gptbots_config.py` (`CLAW_MODEL_EMPTY` / `CLAW_MODEL_NAME_AS_ID` fix text) and
  `README.md`. The pinned default and its constants are unchanged.

- **`call-gptbots-api.md` now opens with "which credential?"** and its Account API table
  carries the full DevKey family (flagged as Basic auth, unlike every other table in the
  file), plus the eight Agent/Workflow version endpoints. `SKILL.md`'s API section is a
  two-row credential table instead of a single Bearer line.

- **The package is now English-only.** Every CJK string was removed from `SKILL.md`,
  `README.md`, `CHANGELOG.md` and all `references/`: console paths are named in English
  (`Profile -> Account -> Developer info`, `target Settings -> Agent Brain -> Model`,
  "create an API Key with version management enabled"), and the illustrative Chinese user
  utterances in `create-gptbots-flowagent.md` were replaced with English equivalents.
  Two places carry CJK **as data, not prose** — the Audio Agent's seeded TTS symbol filter
  (fullwidth `=`/`+` and the CJK bracket pairs) and `validate_knowledge_files.py`'s
  image-placeholder labels. Those are now written as `\uXXXX` escapes, so the source is
  ASCII while the emitted config and the regex are byte-identical to 1.19.0 (verified by
  diffing both against the previous release).

- **`SKILL.md` workflow gained C3 (look up a model version ID) and E (create platform
  resources / publish through the API)**; the knowledge-curation workflow moved E → F. The
  delivery step now offers three paths — manual import, create-new via the account API, and
  update-existing via the version API — instead of "manual or test-mode".

## 2026-07-31 (1.19.0)

### Fixed

- **LoopAgent: plain-Agent residual fields can no longer reach the config.** Removing
  `chatModelVersionId` from the emitted dict (1.18.x) closed only the default path —
  `loopagent_config(**kwargs)` still passed *any* key through verbatim, and its own
  docstring advertised `reasoningEffort` as a legal pass-through. A generation script
  could therefore put the whole QuestionAnswer model block back onto a LoopAgent, where
  nothing reads it and `chatModelVersionId` actively greys out attachment upload on
  share pages (the Agent detail API derived `supportImageRecognition` from it).
  `build_gptbots_loopagent.py` now rejects `PLAIN_AGENT_ONLY_FIELDS` —
  `chatModelVersionId`, `modelDynamicParams`, `creativityLevel`, `maxRespTokens`,
  `reasoningEffort`, `reasoningEnabled`, `showReasoning`, `databaseTableIds` — with a
  message naming the `clawRule` field that replaces each one.

- **`CLAW_MODEL_EMPTY` promoted from warning to error.** A blank `clawRule` center
  `llm.model` is never backfilled: the agent answers `50101` on its first message, and
  importing into an existing LoopAgent wipes that target's model. With a pinned default
  available there is no case where shipping a blank model is correct.

### Added

- **Pinned LoopAgent brain model: `0ec52e3e7dfc000f9470eb15` (GPT-5.6-Luna).** LoopAgent
  models are served by the **new AMH LLM gateway**, which the model-version-list API does
  not expose — that endpoint still serves QuestionAnswer and FlowAgent, so the "query the
  id" habit silently carries over and finds nothing. `claw_center()` now defaults to
  `DEFAULT_CLAW_MODEL` and never emits a blank model; pass `model=<id from the target's
  export>` when updating an existing LoopAgent. Documented in
  `references/create-gptbots-loopagent.md` §3/§7/§9, `loopagent-runtime.md` (50101 row),
  `test-mode-update-publish.md` and `README.md` (re-pin when the platform default moves).

- **`CLAW_PLAIN_AGENT_FIELD` validator check** (`validate_gptbots_config.py`): errors on
  `chatModelVersionId` on a `botType=LoopAgent` (concrete, reproduced breakage), warns on
  the other seven. This is what catches residue in a **user-provided** `.bot` — the
  builder guard only covers files this skill generates.

### Fixed (found reviewing the above)

- **LoopAgent top-level checks no longer hide behind the topology walk.** `CLAW_PLAIN_AGENT_FIELD`,
  `CLAW_TOP_LEVEL_PROMPT`, `CLAW_TOOL_TRACE_ROUNDS`, `CLAW_MESSAGE_MODE` and the `privateSkills`
  checks sat after the `return`s for a missing/malformed `clawRule`, so a QuestionAnswer bot
  relabelled `LoopAgent` — the population most likely to carry residue — reported only
  `CLAW_RULE_MISSING`. They now run first, in `check_claw_top_level()`.
- **`botType: "Claw"` is validated as a LoopAgent** instead of skipping every LoopAgent check.
  The legacy alias still errors (`L0_BOT_TYPE`, rename it), but the file is now checked.
- **`CLAW_MODEL_EMPTY` catches non-string models.** The blank test used `_is_blank()`, so
  `"model": 0` / `[]` / `{}` / `false` passed clean while failing at runtime exactly like `""`.
- **`persona=` is no longer silently dropped when `rule=` is passed** (`build_gptbots_loopagent.py`):
  `persona` is a named parameter, so it never reached the either/or guard — the bot shipped with
  an empty identity prompt and only a warning.
- **`multi_modal={"multiModalInput": None}`** raises the documented `ValueError` instead of a
  bare `TypeError`.

### Docs

- Corrected validator codes that do not exist: `MSG_CONTENT_FIELD` → `MSG_NONCANONICAL`
  (`SKILL.md`, `create-gptbots-flowagent.md`, `flowagent-components.md`), `EDGE_DUP_LINE` →
  `EDGE_DUP_HANDLE` (`flowagent-components.md`), `AUDIO_CONFIG_PARAM_RANGE` →
  `AUDIO_CONFIG_RANGE` (`create-gptbots-audioagent.md`).
- `create-gptbots-agent.md` / `create-gptbots-flowagent.md` / `create-gptbots-loopagent.md` no
  longer show `"multiModal": {"multiModalInput": {}}` as the thing to emit — that shape fails
  the mandatory quality check (`L0_MULTIMODAL_FILE_LIMIT`) and dies on the chat API, which
  `SKILL.md` already said and these three contradicted.
- `create-gptbots-loopagent.md` topology table said the center carries "the 3 editable prompts",
  contradicting §4 and the 1.18.2 change — only `persona` is editable.

- `SKILL.md` (1.18.2 → 1.19.0): workflow A gains an explicit "strip fields that don't
  belong to this `botType`" step, and the "keep model ids blank" rule now carries its
  LoopAgent exception instead of quietly mis-advising.


## 2026-07-29 (1.18.2)

### Changed

- **LoopAgent: `persona` is the only editable prompt.** The console entry points for
  the center's `style` and `routing` prompts have been removed from the product, so
  text written there would shape runtime behaviour that no operator can review, edit
  or reset. `build_gptbots_loopagent.py` no longer accepts `style=` / `routing=` and
  always emits them as empty strings (the keys stay on the wire for parity with a
  platform-seeded bot); the reference now folds tone and message-handling guidance
  into the persona, with headed sections so a longer persona stays navigable.
  New `CLAW_PROMPT_NO_UI` warning fires when `style` / `routing` / the legacy
  `router` alias carry content.


## 2026-07-29 (1.18.1)

Both fixes below came out of publishing a real LoopAgent to the platform and finding it
imported cleanly, saved cleanly, and was dead on arrival.

### Fixed

- **`multiModal.multiModalInput` must carry `fileLimit`.** `BotChatOpenAPIVersion2Data\
  PrePreparationService` unboxes `getFileLimit()` into an `int` with no null check, so a
  `.bot` emitted with a bare `{"multiModalInput": {}}` imports fine, auto-saves fine, and
  then answers **every** `POST /v2/conversation/message` with
  `50000 NullPointerException - Cannot invoke "java.lang.Integer.intValue()"`.
  `build_gptbots_agent.py` and `build_gptbots_loopagent.py` now emit the same complete
  known-good block the FlowAgent builder already used, and the validator rejects a
  missing/non-integer `fileLimit` (`L0_MULTIMODAL_FILE_LIMIT`).

### Added

- **`CLAW_MODEL_EMPTY` warning.** `fixLoopAgentCenterModel` returns *early* when
  `clawRule` center `llm.model` is blank — only a **stale** id is re-checked against the
  gateway catalogue and replaced. So a blank model is never backfilled: the imported
  agent fails its first frame with `50101 No LLM credentials`, and importing into an
  existing LoopAgent silently wipes the model that target already had. Documented in
  `references/create-gptbots-loopagent.md` §3 + its delivery checklist, and in
  `references/test-mode-update-publish.md` (carry the target's model across before
  updating an existing LoopAgent).


## 2026-07-29

### Added

- **LoopAgent support (`botType=LoopAgent`).** New `references/create-gptbots-loopagent.md`
  (clawRule topology, import-fatal invariants, the three center prompts, capability
  wiring) and `references/loopagent-runtime.md` (stateless-engine model, save-vs-publish,
  the silent capability gates, memory/burst-message semantics, error codes, symptom
  table). New `scripts/build_gptbots_loopagent.py` emits the exact platform topology —
  1 `ClawCenter` + 7 satellites with contractual ids and `center->{id}` edges — and
  refuses out-of-range loop control, bad skill refs and SSRF-prone `baseUrl` values.

- **Audio Agent support (`botType=Audio`).** New `references/create-gptbots-audioagent.md`
  (engine modes and their model wiring, the voice-only `identityPrompt`, the full
  `multiModal` block with server-enforced ranges) and
  `scripts/build_gptbots_audioagent.py`.

- **Validator: LoopAgent + Audio checks** (`validate_gptbots_config.py`). `botType` now
  accepts `LoopAgent` / `Audio`. New codes:
  `CLAW_RULE_MISSING`, `CLAW_CENTER_MISSING` / `_DUPLICATE` / `_DISABLED`,
  `CLAW_LOOP_RANGE`, `CLAW_TOO_MANY_COMPONENTS`, `CLAW_COMP_ID_NOT_STRING`,
  `CLAW_BASEURL_SSRF`, `CLAW_MODEL_NAME_AS_ID`, `CLAW_KB_RANGE` / `_SEARCH_MODE`,
  `CLAW_RETIRED_KNOWLEDGE_KEY`, `CLAW_SKILL_REF_*`, `CLAW_ENV_REFS`,
  `CLAW_TOP_LEVEL_PROMPT`, `CLAW_TOOL_TRACE_ROUNDS`, `CLAW_MESSAGE_MODE`,
  `CLAW_SUBAGENT_RANGE`, `CLAW_INERT_FIELD`, `CLAW_PRIVATE_SKILL_*`,
  `AUDIO_ENGINE_MODE`, `AUDIO_SOURCE_LANG`, `AUDIO_CONFIG_RANGE`, `AUDIO_VOICE`,
  `AUDIO_QUALITY`, `AUDIO_OUTPUT_MODE`, `AUDIO_MAX_RESP_TOKENS`, `AUDIO_URL`,
  `AUDIO_IDENTITY_PROMPT_EMPTY`, plus cross-type placement warnings (`XTYPE_*`) that
  catch a `clawRule` / voice block sitting on the wrong `botType`.

### Docs

- `SKILL.md` (1.17.0 → 1.18.0): added a five-row type-routing table at the top so the
  right reference is picked before any work starts, and kept the file short by leaving
  every LoopAgent/Audio specific rule in its own reference rather than inlining it here.


## 2026-07-15

### Fixed

- **Variable node: success branch handle.** The success edge now emits
  `right{id}-variable_true` + `name:"_true"` instead of the bare
  `right{id}-variable` + `name:null`. The bare handle does not anchor to the
  canvas "assignment successful" port, so the line rendered detached/floating
  and the port greyed out. `connect(var, dst)` now produces the correct handle
  automatically. (`build_gptbots_flowagent.py`)

- **`EDGE_DUP_HANDLE`: false positives on fan-out.** The check errored on any
  repeated `sourceHandle`, wrongly flagging legitimate parallel fan-out.
  FlowAgent explicitly supports one output port driving several edges to
  *different* targets. It now errors only on a genuinely duplicated edge — the
  same `sourceHandle` → same target. (`validate_gptbots_config.py`)

- **`BRANCH_EXCEPTION_EDGE`: false error.** A classifier's wired
  `branch_exception` edge was rejected outright. Real platform exports contain
  it (`name:"_exception"`, with `exceptionSwitch:true`), structurally identical
  to the LLM/Condition wired exception. It now only warns when the edge exists
  but `exceptionSwitch` is off, and the builder no longer blocks wiring it.
  (`validate_gptbots_config.py`, `build_gptbots_flowagent.py`)

### Added

- **`VAR_SUCCESS_HANDLE` check.** Catches the bare `variable` success handle.
  The handle parser drops the `_true` suffix, so the generic source-key check
  could not distinguish `variable` from `variable_true`.
  (`validate_gptbots_config.py`)

### Docs

- `references/flowagent-components.md`: documented the Variable node's
  Success/Failure handles at the node; corrected the "exactly one edge per
  output handle" and "the classifier has no `branch_exception` edge" claims.
  `SKILL.md` intentionally unchanged — node-level detail belongs in the
  component reference.
