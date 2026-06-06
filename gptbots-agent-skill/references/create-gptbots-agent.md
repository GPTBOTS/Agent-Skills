# Create / optimize a GPTBots Agent (.bot)

> Reference for the `GPTBots Skill` workflow when the target is a **QuestionAnswer Agent or MultiAgent**. Turn "scenario + requirements" (or a user-provided existing `.bot` file) into a **plaintext `.bot` config** (`exportType=BOT`, `botType=QuestionAnswer` or `MultiAgent`) that imports directly into the GPTBots platform.

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
Start from the user's existing `.bot` (or a minimal valid skeleton when creating from scratch), and only change documented fields. Key points:
- Required top-level fields: `formatVersion`, `exportType=BOT`, `exportTime`, `name`, `botType`.
- Model id (`chatModelVersionId`, etc.) **left blank or as a placeholder** — the backend import backfills the default model; inventing real ids will cause errors.
- Plugin authentication, `apiSecrets`, cross-organization references **left blank** — import always clears them.
- `creativityLevel ∈ [0,0.95)`; `MultiAgent` requires a valid planner node.

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
