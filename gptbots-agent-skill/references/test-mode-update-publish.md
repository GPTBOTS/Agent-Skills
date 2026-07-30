# Update & publish a test-mode Agent/Workflow via API

After generating and validating a `.bot`/`.flow`, you can push it straight into a
GPTBots target and take it live through the API — no manual console import. This is
the fastest delivery path when the target is in **test mode**.

> ⚠️ **Only a target created in "test mode" can be updated/published this way.** The
> mode is chosen at target creation and is immutable; a non-test target returns
> `403200`. The API key is the **target's own key** (Agent Key for `.bot`, Workflow
> Key for `.flow`) from that target's *Integration / API* channel — a mismatched key
> type returns `403204`. Never write the key into a file.

## The flow (what the builder script automates)

1. **Validate** the file offline (`validate_gptbots_config.py`) — never import a config
   that fails the checks.
2. **Import** (update): `POST /v1/{agent|workflow}/version/import` as `multipart/form-data`
   with `file=@config.bot` (+ optional `versionDesc`). The platform saves it as a new
   draft version, which also becomes the current version, and returns that `version`.
3. **Release** (publish, optional): `POST /v1/{agent|workflow}/version/release` with
   `{"version": "<from step 2>"}`. That version goes live; other versions return to draft.

Base URL: `https://api-{endpoint}.gptbots.ai` (`endpoint`: `sg` default / `jp` / `th`).
Version numbers are server-generated (latest segment +1, or `1.0.0` for the first).

| File | Import endpoint | Release endpoint | Key |
|---|---|---|---|
| `.bot` (Agent) | `/v1/agent/version/import` | `/v1/agent/version/release` | Agent Key |
| `.flow` (Workflow) | `/v1/workflow/version/import` | `/v1/workflow/version/release` | Workflow Key |

## Use the helper script

`scripts/publish_gptbots.py` does validate → import → (optional) release in one call:

```
# import only (saves a new current/draft version):
python3 scripts/publish_gptbots.py my-agent.bot --api-key <AGENT_KEY> --endpoint sg

# import AND publish live:
python3 scripts/publish_gptbots.py my-flow.flow --api-key <WORKFLOW_KEY> --release \
        --version-desc "Imported by AI tool"

# key via env (kept out of the command line):
GPTBOTS_API_KEY=<KEY> python3 scripts/publish_gptbots.py my-agent.bot --release
```

It auto-detects Agent vs Workflow from the extension, runs the validator first,
prints the returned `version`, and translates error codes. **Publishing is a
side-effectful, live action — only pass `--release` when the user has asked to go
live**; default (no `--release`) just saves the version for review in the console.

## Error codes (shared by import & release)

| Code | Meaning |
|---|---|
| 0 | success |
| 40348 | target does not exist |
| 403200 | not in test mode (only test-mode targets are updatable/publishable via API) |
| 403201 | imported file type ≠ target type (`.bot`↔Agent, `.flow`↔Workflow) |
| 403202 | the platform failed to parse the imported file |
| 403203 | the specified version does not exist |
| 403204 | API key type ≠ endpoint (Agent Key for `.bot`, Workflow Key for `.flow`) |
| 40353 | published count exceeds the plan limit (release) |

## Import-time data handling (so you know what is/isn't preserved)

- Knowledge bases (data groups) / database tables / docs: kept if they still belong to
  the target (by Agent/Workflow ID), else dropped.
- Associated workflows / tools (plugins): kept if still valid in the **organization**, else dropped.
- Agent top-level knowledge-base mounts are NOT carried by the `.bot`; the target keeps its own mounts.
- **Third-party credentials** are backfilled by matching component/node/plugin ID on the
  target, so already-authorized components stay usable — you don't re-enter secrets.
- **LoopAgent only — carry the target's brain model across.** `clawRule` is replaced wholesale
  and a blank `center.content.llm.model` is *not* backfilled, so importing a file whose model is
  empty clears the model the target had and every message then fails with `50101`. Before
  updating an existing LoopAgent, export it, copy `clawRule.components[center].content.llm.model`
  into the file you are about to import — or warn the user to re-pick the model and publish again.
- **LoopAgent only — repeated imports duplicate embedded private skills.** A `.bot` whose
  `privateSkills[]` carry a synthetic `skillId` gets a brand-new private skill created on every
  import (a snapshot is only appended when the id already belongs to the target). Iterating on a
  config therefore leaves stale copies behind; reuse the target-assigned `skillId` from an export,
  or have the user clean them up.
