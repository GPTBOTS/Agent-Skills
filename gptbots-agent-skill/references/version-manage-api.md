# Version management via API — update, publish, roll back

> After generating and validating a `.bot`/`.flow`, you can push it into an **existing**
> GPTBots target, take it live, and roll it back — all through that target's own API Key,
> no console import. Creating a *new* Agent/Workflow from a file is a different endpoint
> family (account-level DevKey) — see `org-devkey-api.md`.

## 1. The gate: an API Key with version-management permission

Every endpoint in this file authenticates with the **target's own key** (Agent Key for
`.bot`, Workflow Key for `.flow`) and works **only if that key has version-management
permission enabled**. Without it, every call answers `403` — the config is fine, the key
isn't.

That permission is a **console-only action the API cannot grant**:

> On **gptbots.ai**, open the target → **Integration / API** → create an API Key with
> management (version management) permission enabled, and use that key here.

Two traps worth stating to the user up front:

- A key auto-created by `POST /v1/org/agent|workflow/import` comes back with
  `version_manage_enabled: false`. It can chat or run the target; it can never publish.
- An ordinary chat key made earlier has no management permission either. "It works for
  messages" is not evidence it will publish.

Never write the key into a file. Ask for it at call time, or pass `GPTBOTS_API_KEY` in the
environment.

Base URL: `https://api-{endpoint}.gptbots.ai` (`sg` default / `jp` / `th`).

## 2. The four endpoints

| Action | Method | Agent path | Workflow path |
|---|---|---|---|
| Import a file as a new version | POST | `/v1/agent/version/import` | `/v1/workflow/version/import` |
| Publish a version live | POST | `/v1/agent/version/release` | `/v1/workflow/version/release` |
| List version history | GET | `/v1/agent/version/list` | `/v1/workflow/version/list` |
| Roll back to an earlier version | POST | `/v1/agent/version/rollback` | `/v1/workflow/version/rollback` |

**Import** — `multipart/form-data` with `file=@config.bot` and optional `versionDesc`. The
upload **replaces the target's current configuration** and is saved as a new version, which
also becomes the current (draft) version. Returns `{botId, botType, version, warning}` —
always read `warning`, it is where "we dropped something" is reported.

**Release** — JSON `{"version": "v2"}`. That version goes live; the previously live one
returns to draft. Returns `{version, previous_version}` (`previous_version` is empty on a
first publish). This is a **live, side-effectful action** — only call it when the user has
asked to go live.

**List** — no parameters. Returns the history, newest work first: `id`, `bot_id`,
`version`, `version_desc`, `version_status` (e.g. `PUBLISHED`), `create_time` /
`release_time` (epoch **ms**, `release_time` empty while unpublished), `creator_email`.
Call it before rolling back, so you name a version that exists and can tell the user what
they are reverting to.

**Rollback** — JSON `{"version": "<source>", "new_version": "…", "release": true|false,
"version_desc": "…"}`. It does **not** move a pointer: it copies the source version's
configuration into a **brand-new version** (auto-numbered when `new_version` is omitted)
and optionally publishes that. Returns `{source_version, new_version, created, released,
warnings[]}`. So history is append-only — a rollback is auditable and itself reversible,
and `release: false` lets you stage the revert and inspect it before going live.

## 3. Use the helper script

`scripts/publish_gptbots.py` does validate → import → (optional) release in one call, and
also fronts the list/rollback endpoints. It auto-detects Agent vs Workflow from the file
extension and translates the error codes:

```bash
# import only — saves a new current/draft version, nothing goes live:
python3 scripts/publish_gptbots.py my-agent.bot --api-key <AGENT_KEY> --endpoint sg

# import AND publish live:
python3 scripts/publish_gptbots.py my-flow.flow --api-key <WORKFLOW_KEY> --release \
        --version-desc "Imported by AI tool"

# inspect history before touching anything:
python3 scripts/publish_gptbots.py --list-versions --kind agent --api-key <KEY>

# revert: copy v1 into a new version and publish it
python3 scripts/publish_gptbots.py --rollback v1 --kind agent --release --api-key <KEY>

# key via env (kept out of the command line and shell history):
GPTBOTS_API_KEY=<KEY> python3 scripts/publish_gptbots.py my-agent.bot --release
```

`--release` on either the import or the rollback path is the live publish — **only pass it
when the user explicitly asked to go live.** Without it the version is saved for review in
the console.

## 4. Error codes

| Code | Meaning |
|---|---|
| 0 | success |
| **403** (HTTP) | insufficient permission — **almost always: this API Key has no version-management permission** (§1) |
| 40348 | target does not exist |
| 403200 | target not in a mode that accepts API updates (legacy gate; still emitted by some targets) |
| 403201 | imported file type ≠ target type (`.bot`↔Agent, `.flow`↔Workflow) |
| 403202 | the platform failed to parse the imported file |
| 403203 | the specified version does not exist — run `--list-versions` first |
| 403204 | API key type ≠ endpoint (Agent Key for `.bot`, Workflow Key for `.flow`) |
| 40353 | published count exceeds the plan limit (release) |
| 400 / 401 / 429 / 500 | bad params · unauthorized · rate-limited · server error |

## 5. Import-time data handling (what is and isn't preserved)

- Knowledge bases (data groups) / database tables / docs: kept if they still belong to the
  target (by Agent/Workflow ID), else dropped.
- Associated workflows / tools (plugins): kept if still valid in the **organization**, else
  dropped. Create missing ones first via `org-devkey-api.md` §5.
- Agent top-level knowledge-base mounts are NOT carried by the `.bot`; the target keeps its
  own mounts.
- **Third-party credentials** are backfilled by matching component/node/plugin ID on the
  target, so already-authorized components stay usable — you don't re-enter secrets.
- **LoopAgent only — the brain model is never backfilled.** `clawRule` is replaced
  wholesale, so importing a file with a blank `center.content.llm.model` clears the model
  the target had and every message then fails with `50101`. Bind a real model version ID
  before importing: either carry the target's own id across from its export, or look one up
  with `GET /v1/model/list?org_id=…&agent_type=LOOP_AGENT` (`gptbots_org_api.py models
  --agent-type LOOP_AGENT` — the AMH-gateway catalogue, the only valid source for
  LoopAgent). If you fall back to the builder's pinned default, it **replaces** whatever
  model the target was on — say so when you deliver.
- **LoopAgent only — repeated imports duplicate embedded private skills.** A `.bot` whose
  `privateSkills[]` carry a synthetic `skillId` gets a brand-new private skill created on
  every import (a snapshot is only appended when the id already belongs to the target).
  Iterating on a config therefore leaves stale copies behind; reuse the target-assigned
  `skillId` from an export, or have the user clean them up.

## 6. Safe update loop

1. Export the current target from the console (or keep the generation script that built it).
2. `--list-versions` → note the live version, so you can name a rollback target later.
3. Edit the generation script → regenerate → `validate_gptbots_config.py` (exit 0 required).
4. Import **without** `--release`; the new version becomes current/draft.
5. Have the user review it in the console preview / debug environment.
6. Release only on their explicit go-ahead.
7. If it misbehaves in production: `--rollback <last good version> --release`, which lands
   as a new version rather than erasing history.
