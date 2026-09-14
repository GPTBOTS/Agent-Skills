# Latest `.bot` Configuration Support Design

**Date**: 2026-09-14
**Author**: Codex
**Status**: Approved in conversation

---

## 1. Goal

Extend `gptbots-agent-skill` so agents can safely read, update, and generate `.bot` configurations for human-service tips, localized service-status messages, custom variables/conversation properties, and user properties.

## 2. Out of Scope

- No changes to the GPTBots backend, frontend, database schema, or production data.
- No change to `.bot` `formatVersion`; the backend still exports `1.0`.
- No from-scratch generation of `LoopAgent.clawRule`; existing LoopAgent exports may be updated in pass-through mode only.
- No GitHub release creation. This change publishes source to a feature branch; release assets remain a separate operation.

## 3. Confirmed Backend Contract

The backend already exports and imports these fields:

| Capability | `.bot` path | Contract |
|---|---|---|
| Send service tips | `humanConfig.sendHumanTipSwitch` | Optional boolean. Missing values intentionally have different runtime defaults by path. |
| Localized service-status messages | `humanConfig.multiLanguages.<language>[]` | Map of language keys to `{code, text}` entries. |
| Custom-variable definitions and conversation-property defaults | `customVariables[]` | Definitions are exported; per-conversation values are runtime data and are not exported. |
| User-property definitions | `userProperties[]` | Definitions are exported; per-user values are explicitly excluded. |

Canonical service-status codes are `29`, `30`, `31`, `33`, `34`, `35`, `36`, `37`, `38`, and `84`.

`sendHumanTipSwitch` must not be assigned a single implicit default:

- Flow Human + LiveDesk transfer-failure message (`code=84`): missing/null means enabled.
- LoopAgent + LiveChat in-channel handoff message (`code=36`): missing/null means disabled.
- When the user does not explicitly request a value, preserve an existing field or omit it in a new configuration.

## 4. Affected Files

- **Create**: `gptbots-agent-skill/references/bot-config-fields.md` - authoritative progressive-disclosure reference for the new `.bot` fields, examples, defaults, and privacy boundaries.
- **Modify**: `gptbots-agent-skill/SKILL.md` - route relevant `.bot` tasks to the new reference and bump the skill version from `1.3.2` to `1.4.0`.
- **Modify**: `gptbots-agent-skill/README.md` - document the new reference and backend sources used to keep it synchronized.
- **Modify**: `gptbots-agent-skill/references/create-gptbots-agent.md` - require the new reference when authoring human-service or variable/property settings.
- **Modify**: `gptbots-agent-skill/references/create-gptbots-flowagent.md` - cover component-level Human configuration and conversation-property assignment semantics.
- **Modify**: `gptbots-agent-skill/references/flowagent-components.md` - document Human and Variable component behavior without duplicating the full field catalog.
- **Modify**: `gptbots-agent-skill/references/variables-reference.md` - distinguish definitions, defaults, conversation-scoped values, and user-scoped values.
- **Modify**: `gptbots-agent-skill/references/call-gptbots-api.md` - clarify that `conversation_config.custom_variables` supplies defined conversation-property values and persists them for that conversation.
- **Refactor**: `gptbots-agent-skill/scripts/validate_gptbots_config.py` - retain the CLI entry point while moving cohesive validation responsibilities into modules under `scripts/gptbots_config_validator/`.
- **Create**: `gptbots-agent-skill/scripts/gptbots_config_validator/` - shared report/helpers plus workflow, FlowAgent, and bot-field validation modules, each kept below 250 pure LOC.
- **Create**: `tests/test_gptbots_config_validator.py` - subprocess-level tests for the real validator CLI.
- **Create**: `tests/fixtures/` `.bot` samples only when a fixture improves readability over inline test data.

## 5. Core Flow

```text
User request or existing .bot
  -> SKILL.md routes to the matching Agent/FlowAgent guide
  -> guide loads bot-config-fields.md when human-service or property fields are involved
  -> agent preserves existing unknown fields and writes only documented fields
  -> validate_gptbots_config.py parses the whole file
  -> bot-field validator checks humanConfig/customVariables/userProperties
  -> FlowAgent validator checks component-level humanConfig as well
  -> package is delivered only after validation succeeds
```

For existing LoopAgent files, the skill preserves `clawRule` and all unrelated fields byte-for-byte where practical, edits only the requested documented fields, and validates the shared top-level fields. It does not synthesize a new `clawRule`.

## 6. Validation Rules

### Human-service configuration

- `sendHumanTipSwitch`, when present, must be a JSON boolean.
- `multiLanguages`, when present, must be an object whose values are arrays.
- Every message item must be an object with integer `code` and string `text`.
- Duplicate codes within one language are errors.
- Unknown integer codes are warnings rather than errors so future backend additions remain forward-compatible.
- Apply the same rules to top-level `humanConfig` and every Flow Human component's `humanConfig`.
- A Flow Human component without component-level `humanConfig` remains a warning because the backend currently backfills from the top level.

### Custom variables and conversation properties

- `customVariables`, when present, must be an array of objects.
- Each item requires non-empty `name` and a valid backend `BotCustomVariableType`.
- Allowed backend types: `STRING`, `INTEGER`, `NUMBER`, `BOOLEAN`, `DATETIME`, `OBJECT`, `ARRAY_STRING`, `ARRAY_INTEGER`, `ARRAY_NUMBER`, `ARRAY_BOOLEAN`, `ARRAY_OBJECT`, `FILE`, `ARRAY_FILE`.
- Duplicate names are errors.
- The skill generates the editable UI subset by default (`STRING`, `INTEGER`, `NUMBER`) and preserves other valid backend types from exported files.
- A missing `var_` prefix is a compatibility warning, not a blocking error, because legacy exports may already contain such names.
- The reference explicitly states that `customVariables[]` holds definitions/defaults while runtime conversation values are not part of `.bot`.

### User properties

- `userProperties`, when present, must be an array of objects.
- Each generated item includes `name`, `showName`, `type`, `value`, `desc`, `chatUpdate`, and `chatQuery`.
- Allowed `type` values: `string`, `number`, `datetime`, `bool`, `list`.
- `chatUpdate` and `chatQuery`, when present, must be booleans.
- Duplicate user-property names and collisions with `customVariables` are errors because variable replacement uses one flat namespace.
- Runtime fields such as `accountId` and nested per-user `userProperties` must not be generated; their presence is a privacy error.

All new top-level fields remain optional so older `.bot` files continue to validate.

## 7. Error Handling

| Error condition | Handling | User-visible effect |
|---|---|---|
| Wrong JSON type or invalid enum | Validator error with exact JSON path and fix | File is not delivered until fixed. |
| Duplicate variable/property name | Validator error | Prevents silent variable shadowing. |
| Per-user runtime data in `.bot` | Validator error | Prevents accidental personal-data export. |
| Unknown service-status code | Validator warning | Preserves forward compatibility while flagging schema drift. |
| Missing optional new fields | Accepted | Existing `.bot` files remain compatible. |
| Unsupported LoopAgent synthesis | Skill requires an existing exported `.bot` | Existing config can be patched without inventing `clawRule`. |

## 8. Approach Alternatives

**Option A (recommended): one shared reference plus deterministic validator modules.** Keeps field truth in one place, avoids Agent/FlowAgent documentation drift, and preserves the existing validator command. It adds a small internal refactor because the current validator is already oversized.

**Option B: duplicate field documentation in each Agent guide.** Fewer new files, but the opposing switch defaults and shared variable semantics are likely to drift. Rejected.

**Option C: documentation-only update.** Fastest, but malformed or privacy-unsafe `.bot` files would still pass the mandatory offline check. Rejected.

## 9. Implementation Plan

- [ ] Add failing CLI tests for valid new fields, malformed human messages, invalid variable/property definitions, privacy fields, old-file compatibility, and Flow component-level validation.
- [ ] Run the focused tests and verify they fail because the behavior is absent.
- [ ] Split the validator by responsibility while preserving CLI output and exit codes.
- [ ] Implement the minimum validation needed for the failing tests.
- [ ] Add `bot-config-fields.md` and route all relevant Skill references to it.
- [ ] Add three reference-skill evaluation prompts and expected-behavior rubrics for human tips, conversation properties, and user properties.
- [ ] Run the evaluations without the updated Skill to record the current gaps, then rerun against the updated Skill and record compliance.
- [ ] Bump the Skill version to `1.4.0` and update maintainability documentation.
- [ ] Run focused tests, full tests, Skill validation, packaging, and sample CLI validation.
- [ ] Review the complete diff, commit atomically, and push `feat/support-latest-bot-config` to `origin`.

## 10. Verification Plan

- Unit/CLI tests: `python -m pytest tests/test_gptbots_config_validator.py -q`.
- Full tests: `python -m pytest -q`.
- Skill structure: `python -m skillpack.cli validate`.
- Packaging: `python -m skillpack.cli package`.
- Manual CLI gate: validate one known-good `.bot` containing all new fields and one intentionally invalid file.
- Product gate: import the known-good file in the GPTBots development environment, inspect the saved settings, export it again, and compare the normalized supported fields. This requires a logged-in development environment and is not replaced by offline tests.

Use Python 3.11 or newer. The current machine's default `python3` is 3.9; implementation and verification must use `/Users/lerp/.local/bin/python3.12` in a project virtual environment.

## 11. System Constraints

- **Version availability**: Agent-Skills declares Python `>=3.11`; the implementation uses only that locked baseline and standard-library-compatible syntax. No new runtime dependency is required.
- **Multi-site/config synchronization**: no new MongoDB/MySQL configuration is introduced. Before publishing, confirm the existing backend fields are deployed consistently to Singapore, Japan, and Thailand; an older backend may silently ignore unknown optional fields.
- **Performance/full scan**: the Skill validator runs locally in linear time over one bounded configuration file. No production DB/Redis/ES access, request-path I/O, N+1 query, or full-table scan is introduced.

## 12. Rollout / Rollback

- Rollout: push the feature branch, review it, merge to `main`, then create release assets only through the repository's existing release process.
- Rollback: revert the Skill commit. No product data or backend schema is changed.
- Compatibility: old `.bot` files remain valid because every new field is optional; unknown service codes are warnings.

## 13. Change Impact Boundary

最坏影响：🔴 校验规则或默认语义写错会让生成的 `.bot` 无法导入，或让转人工提示行为与用户配置相反。

必须一起改：共享字段参考、Agent/FlowAgent 路由文档、变量/API 语义、校验器、CLI 测试、Skill 版本和打包验证。

明确不改：GPTBots 后端与前端、数据库结构、存量数据、运行时提示逻辑、`.bot formatVersion`、GitHub Release。

不改但有风险：各生产区域的后端部署版本尚未运行时核实；合并前需确认新加坡、日本、泰国均已支持这些字段。

迁移/刷数专项：不适用；不改字段名、不迁移结构、不刷草稿或发布数据。
