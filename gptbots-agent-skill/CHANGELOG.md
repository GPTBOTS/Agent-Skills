# Changelog

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
