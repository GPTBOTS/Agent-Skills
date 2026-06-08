# Create / optimize a GPTBots Agent (.bot)

> Reference for the `GPTBots Skill` workflow when the target is a **QuestionAnswer Agent**. Turn "scenario + requirements" (or a user-provided existing `.bot` file) into a **plaintext `.bot` config** (`exportType=BOT`, `botType=QuestionAnswer`) that imports directly into the GPTBots platform.

## Workflow (follow the order strictly)

### 1. Requirements discussion (clarify before building)
Confirm item by item; do not invent anything the user did not state: business goal / channels / materials (FAQ, product database, API, web pages, images…) / data to collect / handoff method / boundaries and tone. See `./materials-mapping.md` for how materials are connected. When optimizing an existing Agent, start from the `.bot` file the user provided and change only what the user asked for; if they want to optimize but provided no file, ask them to export it from the platform first.

### 2. Reuse the existing public API to fetch real references (critical; do not leave blanks or guess)
If the user provided an API key and wants to connect resources from an existing Agent, use the **public Open API** to pull real ids into the config (**never call internal/console APIs**). Use the regional base URL `https://api-${endpoint}.gptbots.ai` (`sg`=Singapore default, `jp`=Japan, `th`=Thailand):
- Knowledge base list: `GET https://api-sg.gptbots.ai/v1/bot/knowledge/base/page`
- Documents/metadata: `GET /v1/bot/doc/query/page`, `GET /v1/bot/data/detail/list`
- Datasets: `GET /v1/database/tables/page`
- Verify key: `GET /v1/api-key/verify`
Request header `Authorization: Bearer <API_KEY>`. Fill the real `docGroupIds`/table ids you found into the config; if not found, leave them blank (associate them on the platform after import).

### 3. Design and generate
Start from the user's existing `.bot` (or generate the skeleton with `agent_config()` from `../scripts/build_gptbots_agent.py`, whose `save()` runs the validator), and only change documented fields. Keep the identity prompt external like every other bot — a `prompts/` folder with `identity.md` (one md per prompt), loaded via `load_prompts("prompts/")` and passed as `prompt=P["identity"]` — rather than embedding the long text in the script. Key points:
- Required top-level fields: `formatVersion`, `exportType=BOT`, `exportTime`, `name`, `botType`. `exportTime` MUST be an epoch-milliseconds integer (Long, e.g. `1765077600000`) — an ISO string like `"2026-06-07T00:00:00Z"` fails import with `value not allowed for field exportTime`.
- Model id (`chatModelVersionId`, etc.) **left blank or as a placeholder** — the backend import backfills the default model; inventing real ids will cause errors.
- Plugin authentication, `apiSecrets`, cross-organization references **left blank** — import always clears them.
- **Always include top-level `"multiModal": {"multiModalInput": {}}`** — the import does no backfill and the console auto-save NPEs (HTTP 500 on every save) if `multiModalInput` is null (backend regression 2025-12-02); `agent_config()` emits this automatically. Don't guess the enum fields inside; copy from a real export or omit them.
- `creativityLevel ∈ [0,0.95)`.
- **The identity `prompt` is the highest-leverage field in the whole config** — it drives the Agent's runtime quality and efficiency. Write it with extra care: clear role/goal/boundaries/output format in short imperative sentences, no filler, no internal contradictions (see *Prompt quality for LLM-capable nodes* in SKILL.md).

### 4. Quality check (mandatory; do not deliver if it fails)
After writing the `.bot` you **must** run:
```
python3 ../scripts/validate_gptbots_config.py <name>.bot
```
Non-zero exit code → fix the JSON per the `path`/`fix` in `errors` → rerun, until it passes (exit code 0). **Only after the quality check passes** should you hand the file to the user to import.

### 5. Delivery
Place the new/updated `.bot` file in the current working directory and return its local path (never overwrite the user's original file unless asked — deliver an updated copy alongside it). Then tell the user: on **www.gptbots.ai** (developer space), **Create Agent / Workflow → Import**, then select the file.

## References
- Material → mechanism mapping: `./materials-mapping.md`.
- Referenceable variables: `./variables-reference.md`.
- Authoritative public API docs: https://www.gptbots.ai/docs/api-reference/overview
