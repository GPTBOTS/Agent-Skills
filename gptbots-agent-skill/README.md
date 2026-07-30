# authoring-skills (GPTBots Skill source files)

Source content for the platform-level **GPTBots Skill**. This is a standalone, generic skill package: the target `.bot` / `.flow` config is **provided by the user** at use time (exported from the GPTBots platform), or created from scratch — the package bundles no per-agent `resources/`. In-doc relative paths (`../scripts/...`, `./<sibling>.md`) are correct as-is.

After external AI tools (Claude Code / Codex / Cursor / OpenClaw / Cline / Windsurf) install the generated `.skill`, they can optimize/create Agents & Workflows importable into the GPTBots platform, and drive existing ones via the public API.

## Structure

```
authoring-skills/
├── SKILL.md                              # the generic GPTBots Skill guide (copied to the bundle root; do not bind to a bot)
├── references/
│   ├── create-gptbots-agent.md           # QuestionAnswer Agent → .bot
│   ├── create-gptbots-flowagent.md       # FlowAgent (botType=Flow) → .bot
│   ├── create-gptbots-loopagent.md       # LoopAgent (botType=LoopAgent) → .bot (clawRule)
│   ├── loopagent-runtime.md              # LoopAgent runtime gating / save-vs-publish / error codes
│   ├── create-gptbots-audioagent.md      # Audio Agent (botType=Audio) → .bot (multiModal voice block)
│   ├── create-gptbots-workflow.md        # Workflow → .flow
│   ├── call-gptbots-api.md               # drive Agents via the public API (playbooks)
│   ├── organize-knowledge-base.md        # curate raw docs → import-ready Markdown / table / Q&A
│   ├── flowagent-components.md           # FlowAgent component spec
│   ├── workflow-nodes.md                 # Workflow 21-node spec
│   ├── variables-reference.md            # catalog of referenceable variables
│   └── materials-mapping.md              # material → mechanism mapping
└── scripts/
    ├── validate_gptbots_config.py        # .bot/.flow quality check (mandatory self-check)
    ├── build_gptbots_agent.py            # builder: QuestionAnswer .bot
    ├── build_gptbots_flowagent.py        # builder: FlowAgent .bot
    ├── build_gptbots_loopagent.py        # builder: LoopAgent .bot (center + 7 satellites)
    ├── build_gptbots_audioagent.py       # builder: Audio Agent .bot (voice engine block)
    ├── build_gptbots_workflow.py         # builder: Workflow .flow
    └── validate_knowledge_files.py       # knowledge-base file quality check (Document / Table / Q&A)
```

No per-agent files are bundled: users supply their own exported `.bot`/`.flow` for optimization tasks, and new configs are generated from scenario + requirements.

## Constraints (consistent with the plan)

- Use ONLY the public Open API (`https://api-${endpoint}.gptbots.ai` + `Authorization: Bearer <key>`); never use `/internal/*` or `/api/console/*`.
- Produce *plaintext* `.bot`/`.flow` (decryption-free, directly importable).
- After generation you *must* run `scripts/validate_gptbots_config.py` to self-check; do not deliver if it fails.
- Leave model id / cross-organization references / authentication blank (backfilled or cleared on import); when real ids are needed, query them via this organization's public API.

## Maintainability (sync when the schema drifts)

The rules in `validate_gptbots_config.py` are ported from the real backend/frontend validation. When the schema changes, re-sync against these sources and bump the `version` in `SKILL.md`:
- Backend `oversea-ailab-bot/.../service/workflow/component/utils/WorkflowRuntimeChecker.java`, `WorkflowNodeChecker.java`, `service/exportimport/BotTransferService.java`
- Frontend `ailab-d-developer-frontend/src/features/workflow/canvas/data/handle-node-error.ts`, `handle-connection-point.ts` (Workflow canvas); `src/features/flow-bot/canvas/data/handle-connection-point.ts` + `convert.ts` (FlowAgent canvas edge handles)
- LoopAgent: backend `oversea-ailab-bot/.../bean/entity/ClawFlow*.java`, `consts/ClawComponentTypes.java`, `helper/ClawDefaultsHelper.java` (default topology), `helper/ClawLoopControlValidator.java` (loop ranges, enforced on the import path too), `service/exportimport/ClawRuleTransferHelper.java` + `ImportSecurityScanner.java`; engine `ailab-claw-engine/packages/claw-engine/src/csagent/botFlowAdapter.ts` + `types/botFlow.ts`; frontend `src/features/claw-bot/data/claw-rule-codec.ts`
- Audio Agent: backend `oversea-ailab-bot/.../helper/audio/AudioConfigValidator.java`, `bean/entity/BotMultiModal.java` + `bean/entity/audio/*.java`, `oversea-ailab-common/.../enums/AudioEngineMode.java`; frontend `src/types/audio-agent.ts`
- API docs (authoritative source for call-gptbots-api): https://www.gptbots.ai/docs/api-reference/overview

The rules in `validate_knowledge_files.py` and `organize-knowledge-base.md` mirror the knowledge-base storage formats. When they drift, re-sync against:
- Backend `oversea-ailab-common/.../enums/BotDataSegmentType.java`, `BotDataPurposeType.java`; `oversea-ailab-bot/.../bean/entity/BotDataSplitRule.java` (headerType R1/R2/R3 | C1/C2/C3), `QuestionAnswer.java` (question/answer fields)
- Frontend `ailab-d-developer-frontend/src/features/knowledge-manage/components/localQaDocument.vue`, `localExelDocument.vue`, `src/features/set-creation/rowExcel.vue` (header-row picker)
- Knowledge-base docs: https://www.gptbots.ai/zh_CN/docs/tutorial/knowledge-base
