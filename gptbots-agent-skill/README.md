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
│   ├── create-gptbots-workflow.md        # Workflow → .flow
│   ├── call-gptbots-api.md               # drive Agents via the public API (playbooks)
│   ├── organize-knowledge-base.md        # curate raw docs → import-ready Markdown / table / Q&A
│   ├── flowagent-components.md           # FlowAgent component spec
│   ├── workflow-nodes.md                 # Workflow 21-node spec
│   ├── variables-reference.md            # catalog of referenceable variables
│   └── materials-mapping.md              # material → mechanism mapping
└── scripts/
    ├── validate_gptbots_config.py        # .bot/.flow quality check (mandatory self-check)
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
- API docs (authoritative source for call-gptbots-api): https://www.gptbots.ai/docs/api-reference/overview

The rules in `validate_knowledge_files.py` and `organize-knowledge-base.md` mirror the knowledge-base storage formats. When they drift, re-sync against:
- Backend `oversea-ailab-common/.../enums/BotDataSegmentType.java`, `BotDataPurposeType.java`; `oversea-ailab-bot/.../bean/entity/BotDataSplitRule.java` (headerType R1/R2/R3 | C1/C2/C3), `QuestionAnswer.java` (question/answer fields)
- Frontend `ailab-d-developer-frontend/src/features/knowledge-manage/components/localQaDocument.vue`, `localExelDocument.vue`, `src/features/set-creation/rowExcel.vue` (header-row picker)
- Knowledge-base docs: https://www.gptbots.ai/zh_CN/docs/tutorial/knowledge-base
