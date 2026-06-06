# Call the GPTBots Public API

> Reference for the `GPTBots Skill` workflow when the user wants to **drive a published Agent / Workflow via the public Open API** — scheduled triggering, batch test-case generation and regression evaluation, data queries, knowledge base management, RAG testing, etc. **Use only the public API**; never call any internal/console endpoint. Executed via bash + curl.

## Authentication and base URL
- Base URL follows the data-center region: `https://api-${endpoint}.gptbots.ai/`
  - `sg` = Singapore (**default** when no region is specified) → `https://api-sg.gptbots.ai/`
  - `jp` = Japan → `https://api-jp.gptbots.ai/`
  - `th` = Thailand → `https://api-th.gptbots.ai/`
  - Pick the region matching the organization's data center; if unsure, use `sg`.
- Request header: `Authorization: Bearer <YOUR_API_KEY>`. Ask the user to provide the key; **do not write the key into any file**.
- **Authoritative docs (read before calling)**: https://www.gptbots.ai/docs/api-reference/overview — endpoints, parameters, and responses follow the official docs; below is a quick reference of common endpoints.

## Step 1: Verify the key
```bash
curl -s -H "Authorization: Bearer $GPTBOTS_API_KEY" \
  https://api-sg.gptbots.ai/v1/api-key/verify
```
Returns the entity type (agent/workflow) and id; confirm the key is valid before continuing. (Swap `api-sg` for `api-jp` / `api-th` to match the org's region.)

## API catalog (every public endpoint)

> All paths are relative to the regional host `https://api-${endpoint}.gptbots.ai`. **Each endpoint name links to its own doc page** (open it for the full request/response parameters). Source index: https://www.gptbots.ai/docs/api-reference/overview

### Agent API (conversation)
| Name | Method | Path | Description |
|---|---|---|---|
| [Create Conversation ID](https://www.gptbots.ai/docs/api-reference/conversation-api/create-conversation) | POST | `/v1/conversation` | Create a `conversation_id` for multi-turn chat (binds user attributes + memory). |
| [Send Message](https://www.gptbots.ai/docs/api-reference/conversation-api/send-message-v2) | POST | `/v2/conversation/message` | Send a message and get the Agent reply; supports text/image/audio/document; `response_mode` `blocking` or `streaming`. |
| [Get Conversation List](https://www.gptbots.ai/docs/api-reference/conversation-api/get-conversation-list) | GET | `/v1/bot/conversation/page` | Paginated list of an Agent's conversations (ids, times, message counts, credits). |
| [Get Conversation Detail](https://www.gptbots.ai/docs/api-reference/conversation-api/get-conversation-detail) | GET | `/v2/messages` | All message details within a conversation, by `conversation_id`. |
| [Get Referenced Knowledge](https://www.gptbots.ai/docs/api-reference/conversation-api/get-correlated-dataset) | GET | `/v1/correlate/dataset` | Knowledge chunks referenced in a reply (content, source URL, relevance scores). |
| [Generate Suggested Questions](https://www.gptbots.ai/docs/api-reference/conversation-api/suggested-questions) | GET | `/v1/next/question` | Suggested follow-up questions for a reply. |
| [Agent Response Feedback](https://www.gptbots.ai/docs/api-reference/conversation-api/bot-response-feedback) | POST | `/v1/message/feedback` | Submit user feedback (positive/negative/canceled) on a reply. |
| [Agent Quality](https://www.gptbots.ai/docs/api-reference/conversation-api/quality) | POST | `/v1/message/quality` | Rate a reply's resolution quality (NONE / UNRESOLVED / PARTIALLY_RESOLVED / FULLY_RESOLVED). |
| [Human handoff service](https://www.gptbots.ai/docs/api-reference/conversation-api/human-handoff-service) | POST | `/v1/human/message/receive`, `/v1/human/close` | Agent→user reply + close conversation (plus 3 developer-hosted webhooks: establish / chat / close). |
| [Webhook V2 (receive)](https://www.gptbots.ai/docs/api-reference/conversation-api/webhook-receives-messages-v2) | POST | _(developer-hosted URL)_ | Your endpoint that GPTBots POSTs AI/human replies + usage/credit data to. |

### Knowledge API
| Name | Method | Path | Description |
|---|---|---|---|
| [Get Knowledge Base List](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/get-knowledge-base-list) | GET | `/v1/bot/knowledge/base/page` | Paginated list of the Agent's knowledge bases (doc/chunk counts, token usage). |
| [Get Doc List](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/get-knowledge-doc-list) | GET | `/v1/bot/doc/query/page` | Paginated list of documents within a knowledge base. |
| [Add Text Docs](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/add-knowledge-doc) | POST | `/v1/bot/doc/text/add` | Batch upload text docs (chunked, embedded, stored → new doc IDs). |
| [Update Text Docs](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/update-knowledge-doc) | PUT | `/v1/bot/doc/text/update` | Batch re-chunk/re-embed/replace text docs, preserving the doc ID. |
| [Add Q&A Knowledge Document](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/add-qa-doc) | POST | `/v1/bot/doc/qa/add` | Add Q&A docs via text, CSV upload, or auto doc→Q&A conversion. |
| [Update Q&A Knowledge Document](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/update-qa-doc) | PUT | `/v1/bot/doc/qa/update` | Replace Q&A pairs or the Q&A file of an existing Q&A doc. |
| [Add Q&A Chunks](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/add-qa-chunks) | POST | `/v1/bot/doc/qa/chunks/add` | Append Q&A chunks (with custom keywords) to an existing Q&A doc. |
| [Add Chunks (Text)](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/add-knowledge-text-chunk) | POST | `/v1/bot/doc/chunks/add` | Add text chunks into a doc (chunked, embedded, indexed). |
| [Add Spreadsheet Docs](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/add-knowledge-spreadsheet) | POST | `/v1/bot/doc/spreadsheet/add` | Batch upload spreadsheet docs (CSV/XLS/XLSX) → doc IDs. |
| [Update Spreadsheet Docs](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/update-knowledge-spreadsheet) | PUT | `/v1/bot/doc/spreadsheet/update` | Batch chunk/embed/replace spreadsheet docs, preserving the doc ID. |
| [Delete Docs](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/delege-knowledge-doc) | DELETE | `/v1/bot/doc/batch/delete` | Remove documents from a knowledge base by doc IDs. |
| [Query Doc Status](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/query-doc-status) | GET | `/v1/bot/data/detail/list` | Processing status of knowledge docs by their IDs. |
| [Re-embed Failed Docs](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/re-embed-failed-docs) | POST | `/v1/bot/data/retry/batch` | Batch re-embed all docs currently in "Failed" status. |
| [Vector Similarity Matching](https://www.gptbots.ai/docs/api-reference/knowledge-base-api/vector-similarity-matching) | POST | `/v1/vector/match` | Retrieve knowledge chunks by query/keywords (custom scope + rerank). |

### Workflow API
| Name | Method | Path | Description |
|---|---|---|---|
| [Run Workflow](https://www.gptbots.ai/docs/api-reference/workflow-api/workflow-call-api) | POST | `/v1/workflow/invoke` | Invoke a workflow with inputs; sync/async modes + optional webhook callbacks. |
| [Query Workflow Result](https://www.gptbots.ai/docs/api-reference/workflow-api/workflow-query-api-result) | POST | `/v1/workflow/query/result` | Retrieve a workflow run's result by its workflow run ID. |

### Database API
| Name | Method | Path | Description |
|---|---|---|---|
| [List Database Tables](https://www.gptbots.ai/docs/api-reference/database-api/list-database-tables) | POST | `/v1/database/tables/page` | List an Agent's data tables (name, description, field/record counts). |
| [Create Database Table](https://www.gptbots.ai/docs/api-reference/database-api/create-database-table) | POST | `/v1/database/create-table` | Create new data tables and their fields for an Agent. |
| [Add Table Data](https://www.gptbots.ai/docs/api-reference/database-api/add-table-data) | POST | `/v1/database/import/records` | Add up to 1000 rows to a table in one call. |
| [Query Status of Adding Table Data](https://www.gptbots.ai/docs/api-reference/database-api/query-the-status-of-adding-table-data) | GET | `/v1/database/query/import-results` | Status/progress of an add-data task (success/failure counts, errors). |
| [Retrieve Table Data](https://www.gptbots.ai/docs/api-reference/database-api/get-table-data) | POST | `/v1/database/records/page` | Paginated records from a table (filtering + keyword search). |
| [Update Table Data](https://www.gptbots.ai/docs/api-reference/database-api/update-datebase) | POST | `/v2/database/update/record` | Batch update up to 100 records by record ID or filter. |
| [Delete Table Data](https://www.gptbots.ai/docs/api-reference/database-api/delete-datebase) | POST | `/v2/database/delete/record` | Batch delete up to 1000 records by record IDs or filter. |

### Models API
| Name | Method | Path | Description |
|---|---|---|---|
| [Audio to Text](https://www.gptbots.ai/docs/api-reference/models-api/voice-to-text) | POST | `/v1/audio-to-text` | Transcribe audio (mp3/m4a/webm/mp4/mpga/wav/mpeg) to text. |
| [Text to Audio](https://www.gptbots.ai/docs/api-reference/models-api/text-to-audio) | POST | `/v1/text-to-audio` | Synthesize an Agent text message into audio. |

### User API
| Name | Method | Path | Description |
|---|---|---|---|
| [Set User Id](https://www.gptbots.ai/docs/api-reference/user-api/Set-User-Id) | POST | `/v1/user/set-userid` | Associate a unique user ID with anonymous identifiers across channels. |
| [Update User Attributes](https://www.gptbots.ai/docs/api-reference/user-api/Update-user-Attributes) | POST | `/v1/property/update` | Batch set custom user attributes for profiling/personalization. |
| [Query User Attributes](https://www.gptbots.ai/docs/api-reference/user-api/Query-user-Attributes) | GET | `/v2/user-property/query` | Query user attributes by user/anonymous IDs (≤100 per request). |
| [Get User CDP](https://www.gptbots.ai/docs/api-reference/user-api/get-user-cdp) | GET | `/v1/user/get-user-cdp` | Get user CDP info (user ID, anonymous ID, conversation type). |

### Analytics API
| Name | Method | Path | Description |
|---|---|---|---|
| [Get Total Credit Consumption](https://www.gptbots.ai/docs/api-reference/analytics-api/get-credit-consumption) | GET | `/v1/account/bill/total` | Total credits consumed by the Agent within a time range. |
| [Get Detailed Credit Consumption](https://www.gptbots.ai/docs/api-reference/analytics-api/get-credit-consumption-detail) | GET | `/v1/account/bill/page` | Daily credit consumption over a period. |
| [Get Agent Conversation Credit List](https://www.gptbots.ai/docs/api-reference/analytics-api/agent-conversation-credits) | GET | `/v1/account/agent/conversation/credits` | Per-conversation credit use (last 30 days). |
| [Get Workflow Run Credit List](https://www.gptbots.ai/docs/api-reference/analytics-api/workflow-run-credits) | GET | `/v1/account/workflow/run/credits` | Per-run workflow credit use (last 30 days). |

### Account API
| Name | Method | Path | Description |
|---|---|---|---|
| [Get Bot Information](https://www.gptbots.ai/docs/api-reference/account-api/get-bot-information) | GET | `/v1/bot/detail` | Basic Agent info (id, name, configuration, operational parameters). |

### History API (legacy v1; prefer the v2 equivalents above)
| Name | Method | Path | Description |
|---|---|---|---|
| [Get Conversation Detail V1](https://www.gptbots.ai/docs/api-reference/history-api/get-conversation-detail) | GET | `/v1/messages` | Message history for a conversation (v2 equivalent: `GET /v2/messages`). |
| [Get Q&A List](https://www.gptbots.ai/docs/api-reference/history-api/get-qa-list) | GET | `/v1/message/qa/record/page` | Q&A records from chat history (optional feedback filter). |
| [Get Correlated Document](https://www.gptbots.ai/docs/api-reference/history-api/get-correlated-doc) | POST | `/v1/bot/data/references` | Documents an Agent referenced when replying (ids, names, source URLs). |
| [Send Message V1](https://www.gptbots.ai/docs/api-reference/history-api/send-message-v1) _(deprecated)_ | POST | `/v1/conversation/message` | Legacy send-message (use `POST /v2/conversation/message` instead). |
| [Webhook V1](https://www.gptbots.ai/docs/api-reference/history-api/webhook-receives-messages) _(deprecated)_ | POST | _(developer-hosted URL)_ | Legacy inbound webhook (use Webhook V2 instead). |

## Quick reference of common endpoints (official docs are authoritative)
###  Trigger Agent/FlowAgent via conversation/messages
- The request body structure for Agent and FlowAgent is consistent. For a new conversation, a conversationID should be generated first; for historical conversations, you can directly reuse the original conversationID.
- Conversations/messages: `POST /v1/conversation` (create conversation), then `POST /v2/conversation/message` with `response_mode` `blocking` or `streaming`.
- Request Example (blocking):
```
curl -X POST 'https://api-${endpoint}.gptbots.ai/v2/conversation/message' \
-H 'Authorization: Bearer ${API Key}' \
-H 'Content-Type: application/json' \
-d '{
    "conversation_id": "686e2646cb8ee942d9a62d79",
    "response_mode": "blocking",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "I have uploaded 2 image files, please OCR and return 2 json records."
                },
                {
                    "type": "image",
                    "image": [
                        {
                            "base64_content": "<complete_base64_string>",
                            "format": "jpeg",
                            "name": "TAXI1"
                        },
                        {
                            "url": "https://gptbots.ai/example.png",
                            "format": "png",
                            "name": "TAXI2"
                        }
                    ]
                },
                {
                    "type": "audio",
                    "audio": [
                        {
                            "url": "https://gptbots.ai/example.mp3",
                            "format": "mp3",
                            "name": "example1 audio"
                        }
                    ]
                },
                {
                    "type": "document",
                    "document": [
                        {
                            "base64_content": "<complete_base64_string>",
                            "format": "pdf",
                            "name": "example pdf"
                        }
                    ]
                }
            ]
        }
    ],
    "conversation_config": {
        "long_term_memory": false,
        "short_term_memory": false,
        "knowledge": {
            "data_ids": [
                "58c70da0403cc812641b9356",
                "59c70da0403cc812641df35a"
            ],
            "group_ids": [
                "67c70da0403cc812641b93je",
                "69c70da0403cc812641df35f"
            ]
        },
        "custom_variables": {
            "var_current_url": "https://gptbots.ai/example",
            "var_session_id": "abcdef"
        }
    }
}'
```
### Trigger Workflow
- Each workflow has a different request body structure, so the request parameters must be analyzed based on the start node in the workflow's .flow file.
- `POST /v1/workflow/invoke`, `POST /v1/workflow/query/result`.
- Request Example:
```
curl -X POST 'https://api-${endpoint}.gptbots.ai/v1/workflow/invoke' \
-H 'Authorization: Bearer ${API Key}' \
-H 'Content-Type: application/json' \
-d '{
    "userId": "<your_user_id>",
    "input": {
        "id": "123",
        "doc": {
            "format": "pdf",
            "base64_content": "..."
        }
    },
    "isAsync": true,
    "webhook": [
        {
            "method": "POST",
            "url": "https://example-1.com",
            "headers": {
                "Accept": "application/json",
                "Authorization": "Bearer <your_token>"
            }
        },
        {
            "method": "GET",
            "url": "https://example-2.com?fr=google",
            "headers": {
                "Accept": "application/json",
                "Authorization": "Bearer <your_token>"
            }
        }
    ]
}'
```
> For all other endpoints (data queries, knowledge base, database, analytics…) see the **API catalog** above.

## Playbook: scheduled-task triggering
The user wants to "invoke an Agent on a schedule to run a message task".
1. Create/reuse a conversation → record the `conversation_id`.
2. Use `POST /v2/conversation/message` (`response_mode: blocking`) to send the task message (body includes `conversation_id` and `messages`).
3. Schedule the curl call via the user's own cron / platform scheduler (this skill does not hold a scheduler; it only provides a script that can be run on a schedule).

## Playbook: test-case generation and regression evaluation (quality / RAG testing)
The public API has *no dedicated batch-evaluation endpoint*; orchestrate via the message interface:
1. Prepare the test set (inputs + expected key points).
2. For each case, call `POST /v2/conversation/message` (`response_mode: blocking`) to get the reply.
3. Compare/score in a local script (you may also call a reviewer Agent's message endpoint to do LLM scoring), and aggregate the pass rate.
4. Regression: after a version change, rerun the same test set and compare scores.

## Playbook: Agent data queries
- Conversation/message history: `GET /v2/messages` (by `conversation_id`), `GET /v1/bot/conversation/page` (pagination `pageSize` 10–100).
- Usage/credits: `GET /v1/account/bill/page`, `/v1/account/bill/total` (require `start_time`/`end_time`, epoch ms).

## Playbook: knowledge base management
- List knowledge bases/documents: `GET /v1/bot/knowledge/base/page`, `GET /v1/bot/doc/query/page`.
- Add: `POST /v1/bot/doc/text/add`, `/v1/bot/data/file/upload`, `/v1/bot/doc/qa/add`; chunked `POST /v1/bot/doc/chunks/add` (≤50 keywords per chunk).
- Update/delete: `PUT /v1/bot/doc/text/update`, `DELETE /v1/bot/doc/batch/delete`.

## Constraints
- Public `/v1`·`/v2` API only; for capabilities that require console/internal, clearly tell the user that the capability is currently outside the scope of the public API, and do not fabricate endpoints.
- Rate: conversation-type endpoints are roughly 100 req/min/bot; pagination `pageSize` is mostly 10–100.
