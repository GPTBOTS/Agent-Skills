# Account-level (DevKey) API — create & manage org resources

> Reference for the `GPTBots Skill` when the user wants to **create things on the platform**
> rather than talk to one already-published Agent: create an Agent or Workflow from a
> generated `.bot`/`.flow`, create Tools / MCPs / Skills in an organization, or look up a
> **model version ID** to write into a config. These endpoints are account-scoped and use
> **DevKey / DevSecret Basic auth** — a different credential from the Agent API Key.

## 1. Two credentials, two scopes — never mix them

The platform has exactly two auth schemes, and picking the wrong one is the most common
failure when driving GPTBots from a script.

| | **DevKey / DevSecret** (this file) | **Agent / Workflow API Key** |
|---|---|---|
| Header | `Authorization: Basic base64(DevKey:DevSecret)` | `Authorization: Bearer <API Key>` |
| Scope | the **account**, then an org via `org_id` | **one** Agent or Workflow |
| Gets you | orgs, model version IDs, Tool/MCP/Skill CRUD, **creating** Agents & Workflows from a file | chat, workflow runs, knowledge/database/analytics, and that target's **version import / release / rollback** |
| Where from | https://www.gptbots.ai/developer/profile — Profile → Account → Developer info (**DevKey** + **API DevSecret**) | that target's Integration → API channel → create API Key |
| Reference | this file | `call-gptbots-api.md`, `version-manage-api.md` |

Build the Basic token as `base64("<DevKey>:<DevSecret>")` and prefix `Basic ` (with the
space). Base64 is encoding, not encryption — treat the result exactly like the plaintext
secret: **never write it into a file, a commit, or a delivered script.** Ask the user for
the pair at call time and pass it via env (`GPTBOTS_DEV_KEY` / `GPTBOTS_DEV_SECRET`).

When the user doesn't know where to find them, send them straight to
**https://www.gptbots.ai/developer/profile** (Developer info), where the **DevKey** can be
copied and the **API DevSecret** can be revealed or reset. Give them that link rather than a
description of the navigation path.

Base URL: `https://api-{endpoint}.gptbots.ai` — `sg` (default) / `jp` / `th`, matching the
organization's data center. (Docs write it as `https://api.${endpoint}`; the real host is
the `api-{endpoint}.gptbots.ai` form used everywhere else in this skill.)

## 2. Endpoint catalog

All paths relative to the regional host. Every one takes the Basic header.

| Name | Method | Path | Notes |
|---|---|---|---|
| List organizations | GET | `/v1/org/list` | → `org_id` for every other call. **Start here.** |
| List models | GET | `/v1/model/list` | `org_id`, `agent_type` optional → `modelId` (model **version** ID) |
| Create Tool | POST | `/v1/org/tool/create` | optional `api_schema` generates actions |
| Update Tool | PUT | `/v1/org/tool/update` | also carries the auth block |
| List Tools / MCPs | GET | `/v1/org/tool/list` | `plugin_type` `TOOL` / `MCP` |
| Delete Tool | POST | `/v1/org/tool/delete` | `id` |
| Create MCP | POST | `/v1/org/mcp/create` | pulls the server's tools on create |
| Refresh MCP tools | POST | `/v1/org/mcp/refresh` | re-pull `actions` |
| Delete MCP | POST | `/v1/org/mcp/delete` | `id` |
| Create Skill | POST | `/v1/org/skill/create` | empty shell, org-level or Agent-private |
| Import Skill package (file) | POST | `/v1/org/skill/import` | multipart, `.zip` / `.skill` |
| Import Skill package (URL) | POST | `/v1/org/skill/import/url` | host must be on the server allow-list |
| List Skills | GET | `/v1/org/skill/list` | filter by owner/category/enable |
| Delete Skill | POST | `/v1/org/skill/delete` | cascades drafts + version snapshots |
| Precheck Agent file | POST | `/v1/org/agent/import/precheck` | parse + security scan only, writes nothing |
| **Create Agent from file** | POST | `/v1/org/agent/import` | multipart `.bot` → new Agent |
| Precheck Workflow file | POST | `/v1/org/workflow/import/precheck` | writes nothing |
| **Create Workflow from file** | POST | `/v1/org/workflow/import` | multipart `.flow` → new Workflow |

Status codes are uniform: `200` ok · `400` bad params · `401` unauthorized · `403`
insufficient permission · `429` rate-limited · `500` server error. Success bodies are
`{"code":0,"message":"OK","data":{…}}`; delete/update return `affect_count` instead of
`data`. `/v1/model/list` is rate-limited to **60 req/min per account** — cache it.

## 3. Model version IDs — the reason you'll call this most often

`GET /v1/model/list` is how a `.bot`/`.flow` gets a real model bound to it. The returned
`modelId` **is** the *model version ID* that config fields expect (`chatModelVersionId` on
a QuestionAnswer Agent, LLM node model fields on a FlowAgent/Workflow, and
`clawRule.components[center].content.llm.model` on a LoopAgent). `aiModelVersion` is the
display name and can change between releases — **only `modelId` is stable**, so never
write a readable name like `"claude-sonnet-4-6"` into a model field.

```bash
curl -s -X GET 'https://api-sg.gptbots.ai/v1/model/list?org_id=p-xxxx&agent_type=LOOP_AGENT' \
  -H "Authorization: Basic $(printf '%s:%s' "$GPTBOTS_DEV_KEY" "$GPTBOTS_DEV_SECRET" | base64)"
```

| Parameter | Effect |
|---|---|
| *(none)* | the whole platform catalogue |
| `org_id` | validates org membership and returns **that org's actually usable models**, including its own BYOK/self-configured ones — pass it whenever you know the org |
| `agent_type` | `AGENT` · `FLOW_AGENT` · `LOOP_AGENT` · `WORKFLOW` — filters to what that target type may bind. `MULTI_AGENT` is not supported |

Response is grouped two levels deep — **capability → vendor → models**:

```
data
 └── CHAT | EMBEDDING | RERANK | SPEECH2TEXT | TEXT2SPEECH | MODERATION | ANONYMIZATION
      └── OPEN_AI | ANTHROPIC_CLAUDE | GEMINI | …          (vendor keys vary; don't hardcode)
           └── [ { model_name, aiModelVersion, modelId, capabilities[] }, … ]
```

A capability with no models is `{}`, not absent — check before iterating. Ordering is a
display preference, **not** "first = default"; never pick a model by position. Read
`capabilities` (e.g. `pluginSupport`, `ImageRecognition`, `jsonSchema`) to confirm the
model can do what the config needs — an Agent with tools needs `pluginSupport`, one that
takes image input needs `ImageRecognition`.

**LoopAgent: `agent_type=LOOP_AGENT` is mandatory, and its result is the only valid
source.** LoopAgent models are served by the **AMH LLM gateway**; only that filter returns
gateway model version IDs. An id taken from an unfiltered listing, or from another
`agent_type`, produces a bot that cannot reach the gateway and answers `50101` on the first
message. LoopAgent also does **not** support BYOK models. See
`create-gptbots-loopagent.md` §3.

## 4. Creating an Agent / Workflow from a generated file

This is the *create* path (a brand-new target). Updating an existing one is a different
endpoint with a different credential — see `version-manage-api.md`.

**Always precheck first.** Precheck parses and security-scans the file and writes nothing —
no Agent, no API Key, no skills, no data groups, no plugin links. It is free insurance
against a half-created target:

```bash
curl -s -X POST "$BASE/v1/org/agent/import/precheck" \
  -H "Authorization: Basic $BASIC" -F 'file=@my-agent.bot' -F "org_id=$ORG"
# → { "valid": true, "error_message": null, "export_type": "BOT",
#     "bot_type": "Agent", "name": "…", "logo": "…", "introduction": "…",
#     "format_version": "1.0" }
```

Then import:

| | Agent | Workflow |
|---|---|---|
| Endpoint | `POST /v1/org/agent/import` | `POST /v1/org/workflow/import` |
| File | `.bot` (**MultiAgent files are rejected**) | `.flow` |
| Form fields | `org_id`*, `custom_name`, `enable_api` (default `true`), `group_id` | `org_id`*, `custom_name`, `enable_api` (default `true`) |
| Returns | `agent_id`, `name`, `bot_type`, `api_key`, `api_enabled`, `version_manage_enabled`, `warning` | `workflow_id`, `name`, `api_key`, `api_enabled`, `version_manage_enabled`, `warning` |

Three consequences worth telling the user about, every time:

1. **`api_key` is returned exactly once.** Capture it from the response or it's gone; the
   user then has to create a new key in the console. Print it to the user, never to a file.
2. **That auto-created key cannot publish.** Import sets `version_manage_enabled: false`,
   so the key can chat/run but every version endpoint answers `403`. To release or roll
   back through the API the user must **manually create an API Key with version-management
   permission on gptbots.ai** (target → Integration/API → create key, enable version management).
   Say this at delivery — it is a console step nothing in the API can do for them.
3. **`api_enabled` may come back `false`** while the import still succeeds: the org's plan
   doesn't include API. Import is fine; API access isn't. Read the field, don't assume.

Also read `warning` on every import — a non-null value means something in the file was
dropped or degraded (see the data-handling rules in `version-manage-api.md` §5, which apply
to this path too).

## 5. Tools, MCPs and Skills

Create these **before** importing an Agent that expects them, so the import can bind them
inside the organization.

**Tool** — `POST /v1/org/tool/create`, JSON body. Required: `org_id`, `name` (≤20 chars),
`description` (≤100), `logo` (URL), `url` (public http/https base), `show_request` (bool).
Optional `display_name` (≤50) and `api_schema` — an OpenAPI 3 JSON schema **as a string**
(escaped JSON, not a nested object). With `api_schema` the platform generates the actions
and returns `available: true`; without it you get an unusable shell (`available: false`)
that a later `PUT /v1/org/tool/update` must fill in. Update takes the same fields plus
`tool_id` and the auth block (`auth_provider`, `auth_type`, `auth_key`, `auth_secret`, and
their `_name`/`_tip` labels); omitting `api_schema` or `auth_provider` on update leaves
that part untouched rather than clearing it.

**MCP** — `POST /v1/org/mcp/create`. Same base fields as a Tool, plus `mcp_transport_type`
(`SSE` or `STREAMABLE_HTTP`), and optional `headers[]` (≤10) / `queries[]` (≤30) of
`{key, value}`. Create pulls the server's tool list and reports `action_count`; when the
remote server's tools change later, `POST /v1/org/mcp/refresh` re-pulls them. `available:
false` with `action_count: 0` means the handshake failed — check `url` and transport type
before blaming the config.

**Skill** — three ways in:
- `POST /v1/org/skill/create` makes an **empty** skill: `name` (≤50), `description` as a
  multilingual object that **must contain `en_US`**, optional `display_name`, and
  `owner_agent_id` — pass it to create a *private* skill on one Agent, omit it for an
  org-level skill.
- `POST /v1/org/skill/import` uploads a `.zip` / `.skill` package (multipart, optional
  `category_id`) — the path for a skill package this session produced.
- `POST /v1/org/skill/import/url` pulls the package from a public URL. The host must be on
  the server's `openapi.skill-package.allowed-hosts` allow-list; an arbitrary URL is
  rejected, so prefer the file upload unless the user already hosts packages somewhere
  approved.

Deletes (`/v1/org/tool/delete`, `/v1/org/mcp/delete` — both keyed `id`; `/v1/org/skill/delete`
— keyed `skill_id`) are **irreversible**: skill deletion cascades to drafts, version
snapshots and package files. Tools/MCPs already mounted on an Agent keep the console's
delete protection. Only call a delete endpoint when the user explicitly asked for it, by
name, and echo back what will be removed first.

## 6. Use the helper script

`scripts/gptbots_org_api.py` wraps all of the above (stdlib only, no deps). Credentials come
from `GPTBOTS_DEV_KEY` / `GPTBOTS_DEV_SECRET`, so nothing lands in the shell history:

```bash
export GPTBOTS_DEV_KEY=…  GPTBOTS_DEV_SECRET=…      # ask the user; never persist

python3 scripts/gptbots_org_api.py orgs                              # → org_id list
python3 scripts/gptbots_org_api.py models --org p-xxxx --agent-type LOOP_AGENT
python3 scripts/gptbots_org_api.py models --org p-xxxx --agent-type AGENT --capability CHAT --grep claude
python3 scripts/gptbots_org_api.py precheck-agent my-agent.bot --org p-xxxx
python3 scripts/gptbots_org_api.py import-agent  my-agent.bot --org p-xxxx --name "Support Bot"
python3 scripts/gptbots_org_api.py import-workflow my.flow --org p-xxxx
python3 scripts/gptbots_org_api.py tools  --org p-xxxx [--type TOOL|MCP]
python3 scripts/gptbots_org_api.py skills --org p-xxxx
python3 scripts/gptbots_org_api.py import-skill pack.skill --org p-xxxx
python3 scripts/gptbots_org_api.py create-tool --org p-xxxx --name weather --desc "…" \
        --logo https://… --url https://api.example.com --schema-file openapi.json
python3 scripts/gptbots_org_api.py create-mcp  --org p-xxxx --name crm --desc "…" \
        --logo https://… --url https://mcp.example.com/sse --transport SSE
```

`import-agent` / `import-workflow` run the precheck first and refuse to import an invalid
file, print the returned `api_key` **once** to stdout, and warn that the key has no
version-management permission. `models` prints `capability / vendor / model_name /
aiModelVersion / modelId` as an aligned table (`--json` for the raw body).

## 7. Bootstrap playbook — file on disk → running Agent

1. `orgs` → pick `org_id` (confirm with the user when the account has several).
2. `models --org … --agent-type <type>` → pick a `modelId`; write it into the generation
   script (LoopAgent: `model=` on the builder; QuestionAnswer: `chatModelVersionId`).
3. Regenerate the `.bot`/`.flow` and run `validate_gptbots_config.py` — the offline gate
   comes before any API call.
4. Create the Tools / MCPs / Skills the config expects (§5), so the import can bind them.
5. `precheck-agent` → read `valid` / `error_message`; fix and rebuild if invalid.
6. `import-agent` → record `agent_id`; **hand the user the `api_key` immediately**.
7. Tell the user to create a version-management API Key in the console if they want the
   API publish/rollback loop (§4.2), then continue in `version-manage-api.md`.
