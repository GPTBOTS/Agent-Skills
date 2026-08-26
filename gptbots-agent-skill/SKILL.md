---
name: gptbots-agent-skill
description: Create, read, update, and optimize GPTBots (https://www.gptbots.ai) Agent, FlowAgent, LoopAgent, Audio (voice) Agent, and Workflow configs (.bot / .flow), create Agents/Workflows/Tools/MCPs/Skills on the platform and look up model version IDs with account-level DevKey APIs, import & publish/roll back versions of an existing target via its API Key, drive published Agents/Workflows via the Open API (evaluation, RAG testing, scheduled triggering, data & knowledge-base management), diagnose live conversations via message-level LogTree traces, create knowledge bases, and curate raw documents (PDF, Word, Excel, web, FAQ) into import-ready knowledge files. Use whenever the user mentions GPTBots or a .bot/.flow file, or wants to build/optimize/publish/roll back/evaluate a GPTBots Agent, FlowAgent, LoopAgent, Audio/voice Agent, or Workflow, create a Tool/MCP/Skill or query platform model IDs, run ops diagnostics on a conversation, create or manage a knowledge base, or organize knowledge-base documents.
license: MIT
metadata:
  version: 2.0.0
  generatedBy: gptbots-agent-skill
---

# GPTBots Skill

A platform-level skill for working with **GPTBots** (https://www.gptbots.ai) Agents and Workflows.

**Five target types, one per reference.** Identify the type first (`botType` in the file, or from the user's scenario), then read only that type's reference — each one carries its own schema, invariants and builder:

| type | `botType` | build/optimize with | when |
|---|---|---|---|
| Agent | `QuestionAnswer` | `references/create-gptbots-agent.md` | direct FAQ / RAG Q&A — fast and predictable |
| FlowAgent | `Flow` | `references/create-gptbots-flowagent.md` | a reusable, deterministic business process you draw as a graph |
| **LoopAgent** | `LoopAgent` | `references/create-gptbots-loopagent.md` (+ `loopagent-runtime.md`) | open-ended, multi-step, tool-heavy support/automation — the model picks the path at runtime |
| **Audio Agent** | `Audio` | `references/create-gptbots-audioagent.md` | voice / telephony conversations (realtime or ASR→LLM→TTS) |
| Workflow | `Workflow` | `references/create-gptbots-workflow.md` | a standalone orchestrated pipeline (`.flow`) |

Use this skill to:
- **Read / update / optimize** an Agent or Workflow config from a **user-provided `.bot` or `.flow` file**.
- **Create a new** Agent or Workflow from scratch (scenario + requirements → importable `.bot` / `.flow`).
- **Create** a new Agent / Workflow / Tool / MCP / Skill on the platform, and **look up model version IDs**, with the account-level **DevKey/DevSecret** APIs — see `references/org-devkey-api.md`.
- **Update, publish and roll back** an existing Agent/Workflow's version via its own API Key (needs **version-management permission**, granted in the console) — see `references/version-manage-api.md`.
- **Drive** a published Agent/Workflow via the public Open API for evaluation, quality assessment, RAG testing, scheduled triggering, and data/knowledge-base management.
- **Organize** raw documents into import-ready knowledge-base files (Document / Table / Q&A) and advise on chunking, metadata, and retrieval tuning.

## Package layout

```
SKILL.md                      # this guide
references/                   # how-to specs (read the one matching the task)
  create-gptbots-agent.md         # QuestionAnswer Agent → .bot
  create-gptbots-flowagent.md     # FlowAgent (botType=Flow) → .bot
  create-gptbots-loopagent.md     # LoopAgent (botType=LoopAgent) → .bot (clawRule)
  loopagent-runtime.md            # LoopAgent runtime gating, save-vs-publish, error codes
  create-gptbots-audioagent.md    # Audio Agent (botType=Audio) → .bot (multiModal voice block)
  create-gptbots-workflow.md      # Workflow → .flow
  call-gptbots-api.md             # drive an Agent/Workflow via the public API (Bearer API Key)
  org-devkey-api.md               # account DevKey APIs: orgs, model version IDs, Tool/MCP/Skill, create Agent/Workflow
  version-manage-api.md           # update / publish / roll back an existing target's version
  organize-knowledge-base.md      # curate raw docs → import-ready Markdown / table / Q&A files
  variables-reference.md / materials-mapping.md / workflow-nodes.md / flowagent-components.md
scripts/
  validate_gptbots_config.py    # offline .bot/.flow quality check (mandatory self-check)
  validate_knowledge_files.py   # offline knowledge-file check (.md / .csv, --type qa|table|doc)
  build_gptbots_agent.py        # builder: QuestionAnswer .bot
  build_gptbots_flowagent.py    # builder: FlowAgent .bot (ids/handles/layout + message/memory/key-event helpers)
  build_gptbots_loopagent.py    # builder: LoopAgent .bot (center + 7 satellites, loop-control ranges)
  build_gptbots_audioagent.py   # builder: Audio Agent .bot (engine mode + VAD/output/call-control ranges)
  build_gptbots_workflow.py     # builder: Workflow .flow
  gptbots_prompts.py            # load_prompts() — node prompts from prompts.md, a prompts/ folder, or .json
  publish_gptbots.py            # validate → import → (optional) release / list versions / roll back an existing target
  gptbots_org_api.py            # account DevKey client: orgs, models, tools, MCPs, skills, create Agent/Workflow
  create_knowledge_base.py      # create a knowledge base via API → prints knowledge_base_id
```

## Generate via the builder scripts (one per target type)

Don't hand-write config JSON. Write a small Python generation script that imports the builder matching the target type — `build_gptbots_agent.py` (QuestionAnswer), `build_gptbots_flowagent.py` (FlowAgent), `build_gptbots_loopagent.py` (LoopAgent), `build_gptbots_audioagent.py` (Audio), or `build_gptbots_workflow.py` (Workflow). The FlowAgent/Workflow builders auto-generate the strict edge handles (`right{id}-{key}[_suffix]` / `left{id}-{key}`, key matched to component type), unique component/edge/branch ids, and canvas layout — the three places hand-written JSON reliably goes wrong (the FlowAgent builder even rejects the classic mistake of repeating the key inside the suffix, which the offline validator can't catch but distorts canvas lines). Factor repeated node shapes into small functions (`answer_node()`, `gather_node()`, …), then `save()` (which runs the validator) → fix → rerun. The generation script is the source you iterate on; the `.bot`/`.flow` is its regenerable build artifact — when revising a config you generated earlier, edit the script and regenerate rather than patching the JSON. Run any builder with no arguments to print full usage, or `--demo <dir>` for a validated working example.

Always keep the prompts **out of the build script**. The standard layout for every bot is a **`prompts/` folder with one `<key>.md` file per node** (the filename stem is the key) — this scales cleanly and avoids one giant unwieldy file even for large flows. Load it with `load_prompts("prompts/")` from `scripts/gptbots_prompts.py` (returns `{key: text}`).

**Convention: make each prompt file's name equal the component's `name`** in `b.add(type, name, …)`, so wiring reads `role(P[name])` and a renamed/missing prompt fails loudly rather than shipping a blank node. Use `load_prompt_store("prompts/").require(name)` for a fail-fast error listing available keys. Content lives with content, structure with structure. (`load_prompts()` still accepts a single `prompts.md` of `## key` sections, or a flat `.json`, for compatibility — but new bots should use the folder.)

## Where the target config comes from

This skill does not bundle any config. The target `.bot` / `.flow` is **provided by the user** (an attachment, a file path, or pasted JSON — exported from the GPTBots platform via Export). That file is the authoritative starting point for any optimization task. If the user wants to optimize an existing Agent/Workflow but has not provided the file, ask them to export it from the platform first (developer space → the Agent/Workflow → Export). For brand-new creation, no file is needed — start from the user's scenario and requirements.

## Workflow

### A. Optimize / update a user-provided Agent or Workflow
1. Read the user's `.bot` (or `.flow`) file to understand the current design. Identify its type from `botType` (`QuestionAnswer`/`Flow`/`LoopAgent`/`Audio`/`Workflow` — a legacy `Claw` means LoopAgent) and read the matching reference from the table above.
2. Clarify what the user wants to change and gather their materials (FAQ/docs, data, examples). Do not invent requirements.
3. Edit **only** the documented fields needed (see the matching `references/create-gptbots-*.md`). Keep model ids / plugin auth / cross-org references blank (the backend backfills or clears them on import) — **except a LoopAgent's `clawRule` model, which is never backfilled**: a blank one leaves the agent with no brain and wipes the target's, so carry the target's own id across or keep the builder's pinned default (see the LoopAgent reference §3).
4. **Strip fields that don't belong to this `botType`.** An older file often carries residue from another type — most commonly plain-Agent model/sampling fields (`chatModelVersionId`, `creativityLevel`, `maxRespTokens`, `reasoning*`, `modelDynamicParams`, `databaseTableIds`) sitting on a LoopAgent, where nothing reads them and `chatModelVersionId` actively greys out attachment upload on share pages. The validator flags them (`CLAW_PLAIN_AGENT_FIELD` for plain-Agent fields on a LoopAgent; `XTYPE_*` for a whole block — `clawRule`, `flowRule`, `privateSkills`, the Audio voice keys — sitting on the wrong type); delete them rather than carrying them forward.
5. For a **Workflow / FlowAgent**, generate an `overview.md` next to the output file containing a `## Flow (mermaid)` diagram of the new design, so the design intent stays reviewable.
6. Run the quality check, then deliver (sections below).

### B. Create a new Agent or Workflow
Pick the type from the table at the top, read **only that type's reference**, then quality-check and deliver. For a LoopAgent also read `references/loopagent-runtime.md` — its capabilities are silently gated, so a config that looks complete can still do nothing.

### C. Drive a published Agent/Workflow via the API
For evaluation / quality assessment / RAG testing / scheduled triggering / data & knowledge-base management (including **creating a knowledge base** via `POST /v1/bot/knowledge/base/create`), follow `references/call-gptbots-api.md` (public Open API only).

### C2. Ops diagnostics — trace a live conversation to find the failing component
When the user reports a bad / slow / failed reply and gives a **user ID, anonymous ID, or conversation ID**, follow the *Agent ops diagnostics* playbook in `references/call-gptbots-api.md`: locate the conversation (`GET /v1/bot/conversation/page`), enumerate its messages (`GET /v2/messages` → each `message_id`), pull the per-message execution trace (`GET /v1/bot/logtree/query?msgid=…`), and read the `treeData`/`summary` to pinpoint the failed node, misrouted Classifier, empty output, or latency/token spike — then loop back to the optimize-config workflow (A) to fix it.

### C3. Look up a model version ID before binding a model
Never hand-write a model name into a config. `GET /v1/model/list` (account DevKey auth) returns
`modelId` — the stable **model version ID** that `chatModelVersionId`, a FlowAgent/Workflow LLM
node, and a LoopAgent's `clawRule` `center.content.llm.model` all expect:
`python3 scripts/gptbots_org_api.py models --org <org_id> --agent-type AGENT|FLOW_AGENT|LOOP_AGENT|WORKFLOW`.
**A LoopAgent must use `--agent-type LOOP_AGENT`** — only that filter returns the AMH-gateway ids
its brain can route to; anything else answers `50101` at runtime. Check `capabilities` (e.g.
`pluginSupport`, `ImageRecognition`) against what the config needs, and confirm the pick with the
user. See `references/org-devkey-api.md` §3.

### D. Create a knowledge base
When the user wants a **new knowledge base**, create it via the API with `scripts/create_knowledge_base.py --name … --desc …` (POST `/v1/bot/knowledge/base/create` on the Agent bound to the API key) — it prints the new `knowledge_base_id`. Confirm the name/description and whether to enable the knowledge graph (`--graph-enable`) or access control (`--access-control`) first. Then populate it: curate the source material into import-ready files (workflow F) and add them with the doc-add endpoints, targeting the returned id. Full guidance: the *Create a knowledge base* section and *knowledge base management* playbook in `references/call-gptbots-api.md`.

### E. Create platform resources / publish through the API
Two credentials, two jobs — mixing them up is the usual failure:
- **Creating** something new (an Agent or Workflow from a `.bot`/`.flow`, a Tool, an MCP, a Skill)
  or listing orgs/models → account **DevKey + DevSecret**, Basic auth, `scripts/gptbots_org_api.py`
  (`references/org-devkey-api.md`). Always `precheck-agent`/`precheck-workflow` before importing;
  the returned `api_key` is shown **once**, so hand it to the user immediately.
- **Updating / publishing / rolling back** an existing target → that target's own **API Key with
  version-management permission**, `scripts/publish_gptbots.py`
  (`references/version-manage-api.md`). That permission is a console-only grant on
  **www.gptbots.ai** (target → Integration/API → create an API Key with **version management** enabled); the key
  the import API auto-creates does **not** have it, and neither does an ordinary chat key — both
  answer HTTP 403. Tell the user this explicitly rather than letting them hit the 403.
Ask for credentials at call time; never write a DevKey, DevSecret or API Key into a file. When the
user doesn't know where to find the developer credentials, link them to
**https://www.gptbots.ai/developer/profile** (Developer info).

### F. Organize / curate knowledge-base source documents
When the user wants to turn raw/messy material (PDF, Word, Excel, web export, FAQ, notes) into clean, import-ready knowledge-base files — and tune chunking / metadata / retrieval — follow `references/organize-knowledge-base.md`. It maps content to the platform's three storage formats (Document → `.md`, Table → `.csv`/`.xlsx`, Q&A → `question,answer` CSV), enforces the curation disciplines (process every row, merge duplicates, preserve original wording & images, put conflicts in a separate table), and self-checks with `scripts/validate_knowledge_files.py`.

## Prompt quality for LLM-capable nodes (critical)

Several nodes carry an LLM prompt: the top-level identity `prompt` of a QuestionAnswer agent, the LoopAgent's center `persona` — its single editable prompt, so tone and routing guidance both live there (the top-level `prompt` is dead on a LoopAgent), the Audio Agent's `multiModal.identityPrompt` (which must be written for *speech*, not reading), FlowAgent `LLM` components, the Classifier (`Branch`) — **which is LLM-driven: every category rule is a prompt the LLM executes to route each message** — and `Condition` components (also LLM-judged), `ChatGather` (LLM-driven collection: its prompt's field definitions + SOP drive both asking and extraction, and it monopolizes the conversation while collecting — see the FlowAgent reference), and Workflow `LLM` / `INTENT` nodes. These prompts — the identity (system) prompt above all — determine the Agent's runtime quality and efficiency more than any other field, so invest more effort here than anywhere else in the config:

- **Clear, concise, executable.** State the role/identity, goal, boundaries, and expected output format in short imperative sentences. Every sentence should change model behavior; cut filler and vague adjectives — verbose prompts cost tokens on every turn and dilute the instructions that matter.
- **One node, one job.** Scope each prompt to that node's single responsibility; don't restate global rules in every node — put shared identity/boundaries once in the identity prompt.
- **Classifier branch rules are prompts too.** Each `Branch` category rule and `INTENT` intent description deserves the same care as a system prompt: the rules must be **mutually exclusive and unambiguous**, written as concrete descriptions of what belongs in that category (add examples for easily-confused intents), with everything else falling to the `Other`/fallback branch. Routing accuracy — and therefore the whole flow's quality — is capped by the weakest branch rule. Classification must consider conversation context, not just the last message: enable short-term memory and instruct the rules to route fragmentary or emotion-only follow-ups about an unresolved issue to that issue's branch, not the fallback; for cross-session continuity, LLM-driven components also support key events (see the FlowAgent reference).
- **No conflicts.** Before delivery, re-read all prompts in the config **as a set** (identity prompt + every LLM/classifier/condition prompt) and resolve any contradiction in goals, tone, boundaries, or output format. Conflicting prompts make the model behave inconsistently at runtime, which no amount of flow design can fix.

## Import-fatal schema invariants (the builders enforce these; the validator catches them)

These mistakes pass casual inspection but break import or the imported bot. The builder scripts emit
all of them correctly — hand-editing the JSON is where they regress. Each has a validator code.
The first two apply to every type, the rest to FlowAgent/Workflow; **LoopAgent (`clawRule`) and
Audio (`multiModal`) invariants live in their own references** (§3 and §4 respectively).

- **Strong-typed integers must be bare integers**, never quoted strings or `vueflow__…` ids. The backend parses `exportTime` (epoch **milliseconds** Long), `components[].id`, `x`, `y`, and `nextComponents[].id`/`nextComponentId`/`sort` with strict Jackson typing — any string (even `"1"`) fails with `value X is not allowed for field "…"`. Edge ids are unique integers (e.g. `100000+seq`). Unknown/extra fields are tolerated; only wrong *types* kill the import. (`L0_EXPORT_TIME`, `FLOW_COMP_ID_NOT_INT`, `FLOW_COMP_XY_NOT_INT`, `EDGE_ID_NOT_LONG`, `EDGE_INT_FIELD`, `EDGE_ID_DUP`)
- **Top-level `multiModal` must be present AND complete on every BOT.** Without a non-null `multiModal.multiModalInput` the console auto-save NPEs (HTTP 500 on every save); and without an integer `multiModalInput.fileLimit` the Open API v2 chat endpoint unboxes a null and answers `50000 NullPointerException` on **every** message — the import and the console both look fine, so a bare `{"multiModalInput": {}}` ships an agent that is dead on the API. The builders emit a known-good block; don't guess the enum values. (`L0_MULTIMODAL_AUTOSAVE_NPE`, `L0_MULTIMODAL_FILE_LIMIT`)
- **Prompt messages use `text`, not `content`** — a `content` key imports as a BLANK prompt. Each LLM-capable node's `messages[]` is `[Role, LongMemory, ShortMemory, Plugin, (Condition), Input]`; the `Input` message's `upstream` points to the feeding node; KB injection is `dataEnable`+`datasetMessages` (builder `reads_kb=True`), not a message. (`MSG_NONCANONICAL`, `MSG_ROLE_EMPTY`)
- **Classifier (`Branch`) rules live in the edge's `condition` as natural-language text**, with sequential handles `branch_1`/`branch_2`/`branch_other` — never a numeric id in `condition` or a timestamp in the handle (the UI then shows the id, not the rule). (`BRANCH_RULE_IS_ID`)
- **Platform variables need double braces `{{var}}`** — never run `str.format()`/f-strings over a prompt containing `{{…}}` (it collapses to single braces and the variable stops working); substitute with `.replace()`. (`MSG_SINGLE_BRACE_VAR`, warning)
- **Variable assignments** are `{variableName, operation, value}` with `operation` ∈ `Cover`/`Clear`/`Append` (capitalized). (`COMP_ENUM_VARIABLE_OPERATION`)

## Quality check (mandatory — never deliver a config that fails)
After producing or editing any `.bot`/`.flow`, run:
```
python3 scripts/validate_gptbots_config.py <path/to/output>.bot
```
On a non-zero exit code, fix the JSON per the reported `path`/`fix`, rerun, and only deliver once it passes (exit code 0).

## Delivery
1. Place the new/updated `.bot` / `.flow` file (and `overview.md` with its mermaid diagram, for Workflow/FlowAgent) in the current working directory, and return their local paths. Never overwrite the user's original file unless they explicitly ask — deliver an updated copy alongside it.
2. Tell the user how to apply it — three paths, pick by what they have:
   - **Manual:** on **www.gptbots.ai** (developer space), **Create Agent / Workflow → Import**, then select the file.
   - **API — create a new target:** `python3 scripts/gptbots_org_api.py import-agent <file> --org <org_id>` (or `import-workflow`) with the account's DevKey/DevSecret. It prechecks first, then prints the new id and the **one-time** `api_key`. Note for the user that this key cannot publish.
   - **API — update an existing target:** `python3 scripts/publish_gptbots.py <file> --api-key <target key>` imports the file as a new version (add `--release` to publish it live, `--list-versions` to inspect history, `--rollback <version>` to revert). It validates first and translates the error codes. The key must have **version-management permission** (console-only grant); without it every call answers 403. See `references/version-manage-api.md`. **Only pass `--release` when the user explicitly wants to go live** (it's a live, side-effectful publish); without it, the version is saved for review.

## API
- Docs (authoritative): https://www.gptbots.ai/docs/api-reference/overview
- Base URL by region: `https://api-${endpoint}.gptbots.ai/` — `sg`=Singapore (default), `jp`=Japan, `th`=Thailand.
- **Two credentials, never interchangeable:**
  | | header | scope | ask the user for | reference |
  |---|---|---|---|---|
  | Agent / Workflow API Key | `Authorization: Bearer <key>` | one target: chat, runs, knowledge, database, analytics, diagnostics — plus its version import/release/rollback **when the key has version-management permission** | that target's key (Integration → API) | `references/call-gptbots-api.md`, `references/version-manage-api.md` |
  | Account DevKey + DevSecret | `Authorization: Basic base64(DevKey:DevSecret)` | the account/org: list orgs, **model version IDs**, Tool/MCP/Skill CRUD, create Agents & Workflows from a file | both values from https://www.gptbots.ai/developer/profile (Developer info) | `references/org-devkey-api.md` |
- Never write a real key, DevKey or DevSecret into any file (Base64 is encoding, not encryption). Ask for them at call time and pass them via env.
- Playbooks: `references/call-gptbots-api.md`.
