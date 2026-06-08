# GPTBots Component Reference

## ⚠️ Component `type` must be the enum value (not the UI name)

In the generated `.bot`, each `flowRule.components[].type` **must be the exact `FlowComponentType` enum value** below, **not** the UI display name. Writing a UI name such as `"Classifier"` makes the platform import fail (the backend rejects unknown enum values). This doc describes components by their UI name; map each to its enum value here:

| UI name (used in this doc) | `.bot` `type` (enum value) |
|---|---|
| Start / User Input | `Input` |
| End / Output | `Output` |
| LLM / Large model | `LLM` |
| **Classifier** | **`Branch`** |
| Condition (LLM semantic if/else) | `Condition` |
| **If / Else** (variable-based) | **`Bool`** |
| Knowledge Search | `Dataset` |
| Variable Assignment | `Variable` |
| Workflow | `Workflow` |
| Tools | `ToolApi` |
| Card Message | `Predefine` |
| Message Pass-through | `Message` |
| Human Service | `Human` |
| Conversational Collection | `ChatGather` |
| Form Collection | `FormGather` |
| Regular (rule-based branching) | `Regular` |

The full valid set (16): `Input, Output, LLM, Bool, Branch, Predefine, Dataset, Human, Condition, Regular, ChatGather, FormGather, Message, ToolApi, Workflow, Variable`.

## Component catalog (index)

- **Start** (Start / User Input) → `type: Input`: entry; receives the user's message.
- **End** (End / Output) → `type: Output`: returns the upstream content to the user as the reply (endpoint).
- **LLM** (Large model / LLMs) → `type: LLM`: generates text; can have tools/workflows/databases attached.
- **Classifier** → `type: Branch`: routes input into named branches by rules (can be multi-branch).
- **Condition** → `type: Condition`: semantic if/else; the LLM judges whether a natural-language condition is true/false.
- **If / Else** → `type: Bool`: deterministic branching based on variables (does not consume LLM).
- **Knowledge Search** → `type: Dataset`: retrieves from the knowledge base.
- **Variable Assignment** → `type: Variable`: assigns values to user attributes / custom variables.
- **Workflow** → `type: Workflow`: calls an external workflow (standalone node).
- **Tools** → `type: ToolApi`: calls platform-preconfigured interfaces (APIs); as an attachment it relies on function call, as a standalone node it is a stable call.
- **Card Message** → `type: Predefine`: sends preset text/card/form/JSON to downstream.
- **Message Pass-through** → `type: Message`: sends a message directly to the user (whether or not it reaches End).
- **Human Service** → `type: Human`: hands the conversation off to a third-party human customer-service system.
- **Conversational Collection** → `type: ChatGather`: an LLM collects fields item by item over multiple turns.
- **Form Collection** → `type: FormGather`: renders a visual form for the user to fill in to collect fields.
- **Regular** → `type: Regular`: rule-based branching; each rule group has true/false branches.

---

# Component details

## Start (Start / User Input)
The flow entry; receives user input. **Unique in the whole flow** (an AgentFlow has only one Start).

**Attachments (configured uniformly at the Agent "Input" area, not a flow node):**
- **Attachment recognition**: `System file recognition` (parse into Text by non-LLM means, then hand to the LLM) / `LLM recognition` (hand directly to the multimodal LLM).
- **Attachment types**: `Image` / `Audio` / `Video` / `Document` / `File` (each with its own limit); **count** limit is 9.
- ⚠️ **You must enable attachments here first**, otherwise LLMs in the flow cannot be configured for multimodal/attachment recognition.

**Output:** a single outlet, which can connect to multiple downstream nodes at once (parallel fan-out).

## End (End / Output)
The flow endpoint; returns the connected upstream content to the user as the reply. **Unique in the whole flow** (an AgentFlow has only one End).

**Input:** can receive **multiple upstream merges**, and supports **ordering** them before outputting in sequence.
**Output:** none (endpoint).

## LLM (Large model / LLMs)
Pick a model and generate a reply from the upstream input by "identity + knowledge + user question".

**Prompt = identity prompt + knowledge data + user question** (all three boxes support inserting `{{}}` variables):
- **Identity prompt**: a hand-written system prompt (role/task/constraints/output format).
- **Knowledge data**: **automatically references the output of the upstream knowledge search node**; not connected = empty, connected = always included, cannot be removed, but you can append extra content (may include `{{}}`).
- **User question**: **automatically references the upstream node's output**; cannot be removed, but you can append (may include `{{}}`). Pass-through nodes don't change it; it traces back further upstream (e.g. to Start).

**A few choices that affect the flow:**
- **Response format**: `Text` / `JSON Object` / `JSON Schema` — choose JSON when the output needs to be parsed structurally downstream. In the `.bot` the `responseFormat` value must be the enum **name** `Text` / `JsonObject` / `JsonSchema` (not `json_object`).
- **Multimodal / attachment recognition** (toggleable): let the LLM handle upstream attachments. **Prerequisite: attachments must first be enabled at the Agent "Input"**; `LLM recognition` mode also requires the model to support the corresponding type, while in `System file recognition` mode the attachment is already parsed into Text before arriving.
- **The three attachments (workflow/tool/database, each toggleable) = the LLM autonomously decides to call them** (agentic), flexible but demanding on model capability. ⚠️ **For stability/determinism, do not attach; use external connection nodes instead** (Workflow/Tools/Knowledge search connected into the flow as standalone nodes). An attached "database (dataset)" **≠ knowledge base**.
- **Exception mechanism** (toggleable): once enabled, when the LLM errors it takes the **exception branch**, which can connect to a fallback node.

**Memory settings (master switch, enable as needed; each of the four items below can also be independently `enabled/disabled`. Enabled items enter the context, affecting reply quality and token usage; trade off per scenario):**
- **Long-term memory** (toggleable): turns all historical conversations into a vector store, recalled on demand during the conversation.
- **Short-term memory** (toggleable): brings the most recent N turns of full conversation verbatim to the LLM (limit 50 turns).
- **User attributes** (toggleable): must be predefined in Agent settings. When "attributes + collection" is enabled, the LLM **autonomously updates attribute values based on the conversation** (backed by a built-in hidden tool). ⚠️ Update reliability depends on the model — **for stability use the "Variable Assignment" component or the API**, don't rely on the LLM self-updating.
- **Key events** (optional toggle; see "Key events details" for configuration rules): requires a predefined event taxonomy; the LLM automatically summarizes key events in the conversation and injects them into context, mitigating attention dilution in long conversations / interleaved multiple questions.

**Output (by default only one `Success` outlet; enable the exception mechanism to add an `Exception branch`):**
- `Success`: the LLM-generated content flows to downstream nodes as their input.
- `Exception branch` (when the exception mechanism is on): passes the **input the LLM previously received** verbatim to the exception branch, which can connect to **any node** for fallback/human handoff.

### Key events details
> An **optional toggle, enabled as needed** in the LLM memory settings. It extracts key business events from the conversation and injects them into context, mitigating attention dilution in long conversations / interleaved multiple questions.

**Mechanism**: when a trigger timing is reached, an "extraction model" summarizes key events from the conversation by "extraction rules + event taxonomy dictionary", keeping the most recent several to inject into the subsequent LLM context. **Either** of the two trigger-timing thresholds triggers it.

**Configuration items (tuning levers):**
- **Extraction model**: the LLM that runs extraction & summarization. Use a stronger model when event judgment is hard; use a lightweight model for simple scenarios to save cost.
- **Extraction rules** (optional): supplementary explanation of business rules / field constraints / merge strategy. Blank = rely purely on the taxonomy dictionary; fill in when you have special merging or field requirements.
- **Historical key events** (count): how many historical events to keep for injection into context. More = more complete but more token-consuming, fewer = cheaper but easier to lose early events.
- **Message-count threshold**: trigger one extraction after N accumulated new messages. Low = more real-time, more compute; high = cheaper, more lag.
- **Idle-minutes threshold**: trigger one extraction after M idle minutes. Low = capture as soon as the conversation pauses, more timely; high = cheaper.
- **Event taxonomy dictionary**: predefined event categories (`category name` + `category description` to guide the LLM in classifying); the clearer the categories, the more accurate the classification.

⚠️ **The event taxonomy dictionary can be referenced as a variable in the Agent config; delete with caution.**

## Classifier
A built-in LLM that routes upstream messages into named branches by branch rules (**multiple can be activated at once**); the whole routing costs one LLM call.

**LLM core:** same as the LLM node (identity prompt/knowledge data/user question/multimodal/exception mechanism); memory **has no long-term memory** (only short-term memory/user attributes/key events).

**Classification config:**
- Each category = name + **branch rule** (natural language, supports `{{}}`); anything matching no rule goes to `Other`.
- **Run mode**: `Extract` (each branch only receives the part matching its own rule, `Other` receives the full message) / `Pass-through` (each matched branch receives the full upstream message).

⚠️ **Every category's branch rule must be non-empty.** The canvas rejects an empty rule with **"Cannot be empty"** and the classifier becomes unusable, so write an explicit decision description for each category — never leave it blank. `Other` is **system-preset**: it is not a category you create (it carries no rule and is not counted among your `branch_1/branch_2/…`); it always exists as the fallback. You only optionally wire its `branch_other` edge to choose where unmatched messages go.

**Output (multi-branch, multiple can be activated at once):**
- One branch per category: taken on a hit; the content carried is determined by the run mode (extract = matched part / pass-through = full message).
- `Other`: fallback for anything matching no rule (receives the full message).
- `Exception branch` (when the exception mechanism is on): taken when the LLM errors, carrying the full upstream input.

## Condition
The LLM evaluates one natural-language condition you write → if it holds, take `If`; if not, take `Else` (always has an else). The taken branch **passes through the full upstream input verbatim** (no extract mode like the classifier).

**LLM core:** same as the LLM node (identity prompt/knowledge data/user question/multimodal/exception mechanism); memory **has no long-term memory** (only short-term memory/user attributes/key events).

**Condition config:** the condition is written in the "Condition setting → If" box (supports `{{}}`); `Else` is an automatic fallback. ⚠️ The `If` condition text **must be non-empty** (an empty condition is rejected with "Cannot be empty"); `Else` needs no text. **In the JSON the IF text lives on the `conditions_true` edge's `condition` field, with the edge `name:"_true"`; the `conditions_false` edge is `name:"_false"` with `condition:""`.** Putting the IF text only in a node message leaves the canvas IF box empty. Use the builder's `condition_edges(cond, if_text, true_dst, false_dst)`; the validator flags an empty IF (`CONDITION_IF_EMPTY`) and wrong edge names (`CONDITION_EDGE_NAME`).

> **Root cause of a greyed/unusable IF port** (from real-export comparison): the `conditions_true` edge's `name` was `null` (it MUST be `"_true"`), often together with leftover duplicate exception edges (e.g. two `name:"Exception"` plus a `name:"_exception"` on the same `conditions_exception` port from an old import round-trip). Filling the IF box in the UI only sets `condition` — it can't set the edge `name`, so the port stays grey. The fix is at the JSON level: `name:"_true"` on the true edge and exactly one edge per output handle. The validator now errors on a repeated `sourceHandle` (`EDGE_DUP_HANDLE`).

**Output (all pass through the full upstream input):**
- `If`: taken when the condition holds.
- `Else`: taken when the condition does not hold (else).
- `Exception branch` (when the exception mechanism is on): taken when the LLM errors.

## If / Else
Deterministic branching based on **variable values**, **does not consume LLM**, passes through upstream data.

**Condition config:**
- Chained branches: `If` / `Else If` (can add multiple) / `Else` (fallback).
- Multiple rules within a group are combined by `AND` / `OR`; each rule = a variable value (supports `{{}}`) + operator + target value.
- Operators: `=` / `≠` / `contains` / `does not contain` / `length ≥` / `length >` / `length ≤` / `length <` / `has value` / `has no value`.

**Output (all pass through the upstream input, only one is taken):**
- `If` / each `Else If`: **evaluated in order, the first branch that holds is taken**.
- `Else`: taken when none hold (fallback).

## Knowledge Search
Retrieves from the knowledge base: **passes the original upstream input through to downstream**, and on a hit **attaches the matched knowledge** (often connected to the LLM's "knowledge data" box). Internally there is a hidden LLM responsible for the `on-demand call` decision and `query enhancement`, but it **does not rewrite the upstream input passed through to downstream**.

**Knowledge scope:** select one or more **knowledge bases**.

**Retrieval invocation:**
- **Invocation mode** (pick one): `Forced call` (retrieve every time) / `On-demand call` (the internal LLM decides whether to retrieve).
- **Query enhancement** (toggleable): the internal LLM rewrites the query based on conversation history to improve retrieval accuracy (only for retrieval, does not affect the downstream pass-through).

**Recall mechanism** (directly determines "what is recalled and how accurately", has a big impact on agent quality; tune per knowledge characteristics):
- **Retrieval weighting** (pick one of three): `Semantic search` (vector, understands rephrasing) / `Keyword search` (exact words/numbers/models) / `Hybrid search` (a combination of both). The default hybrid is the most stable; lean toward keyword for many terms/numbers, lean toward semantic for colloquial, heavily-paraphrased content.
- **Knowledge relevance** (threshold `0 – 0.95`): the minimum similarity required for a hit. High = more accurate but easier to miss, low = more complete but noisier — raise it if you fear errors, lower it if you fear misses.
- **Recall count** (`1 – 50`): how many knowledge entries to return. More = more complete but token-consuming, may dilute the key point; fewer = focused and token-saving but may miss.
- **Knowledge rerank** (toggleable; pick a rerank model after enabling: NetEase / Baai / Jina): a second precise reranking of the initial recall results, improving top relevance. Enable it when recall volume is large or accuracy demands are high; it slightly increases latency and compute.
- **Graph recall** (toggleable; set the retrieval depth in hops after enabling): use the knowledge graph for multi-hop associative recall expansion. Enable it when the knowledge has strong entity relations; the greater the depth, the broader the association and the higher the noise/overhead.
- **Metadata filter** (optional; not configured = no filtering): narrow the recall scope by document fields; the final scope = filter ∩ selected knowledge bases ∩ ACL. Up to 10 rules combined by `AND`/`OR`; each = field + operator (`=`/`≠`/`contains`/`does not contain`/`starts with`/`ends with`/`is empty`/`is not empty`) + value (literal or `{{variable}}`). Available fields:
  - Preset: `Knowledge base name` / `Document name` / `Uploader` / `Uploader email` / `Upload time` / `Last updated time` / `Document source link` / `Source` / `Data storage type` / `Document format`;
  - or **custom fields** defined in "Metadata".

**Output (two branches, no exception branch):**
- `Has result`: pass through the upstream input + the matched knowledge to downstream.
- `No result`: pass through only the upstream input (no knowledge).

### Metadata (knowledge base field definitions)
> **Custom fields** defined for knowledge base documents, used by "Metadata filter". Define a field first, then you can filter by it in the node.
- **Scope**: `Global metadata` (applies to documents in all knowledge bases under this Bot) / `Knowledge-base level` (applies only to documents in the current knowledge base).
- **Each field**: display name + field name (lowercase letters + digits + underscore) + type (`string` / `number` / `datetime` / `list`) + description + default value.
- At most **50** fields per scope.

## Variable Assignment
Assigns values to **user attributes or custom variables**, **deterministically** (more stable than the LLM's "user attribute" self-update). After assignment, downstream references to the variable get the latest value.

**Prerequisite (critical for imports):** at least one **user attribute or custom variable** must already exist in the workspace; otherwise there is no assignable target, the node can't be configured, and it **can't connect downstream**. **Importing a `.bot` does NOT auto-create these variables** — so a Variable node whose targets aren't pre-defined shows "No variables available" and its `variableSetValueConfigs` are silently dropped. For the common "collect fields → act" pattern you usually **don't need a Variable node at all**: route the ChatGather's collect-complete edge straight to the next step (e.g. human handoff); the collected fields + conversation context carry forward, and key events capture the business type/status. Only use Variable assignment when the target attributes are pre-defined in the workspace.

**Config:** you can add **multiple assignments**, each independent; each = target variable + operation + value.
- Operations: `Overwrite` (replace the original value) / `Append` (**`list` type only**, add an item to the end) / `Clear`.
- Value: a literal, or `{{reference}}` (upstream output / user input / another variable).

**Output (two branches, pass through the upstream input):**
- `Success`: taken when the assignment succeeds.
- `Failure`: taken when the assignment fails/errors.

## Workflow
Calls an external workflow (a standalone node, **deterministic** execution; distinct from the autonomous invocation of a workflow attached to an LLM). A Workflow is a **parameterized program interface** (JSON inputs/outputs, no conversation with the user; connections only trigger it, data flows via explicit parameters), suitable for **deterministic data processing / automation**: calling external APIs, running code, structured data transformation, loop/batch processing, complex conditional orchestration — encapsulating such logic into a Workflow and then calling it is more stable and clearer than piling up nodes in the AgentFlow. Available internal nodes include LLM, intent recognition, knowledge retrieval, HTTP request, code, condition, loop, etc.

**Output:** the workflow result flows to downstream (single output, no exception branch).

## Tools
Calls **interfaces (APIs) preconfigured** on the platform. Two usages:
- **As an LLM attachment**: relies on the model's **function call** capability to **autonomously** decide when to call and how to pass arguments — flexible but demanding on model capability.
- **As a standalone node**: a **deterministic** call (stable), similar to Workflow; for stability use the standalone node.

**Output:** the interface result flows to downstream (single output).

## Card Message
Passes **a preconfigured piece of content** (a structured object) directly to the downstream node, rendered to the user by downstream/the channel.

**Data type** (pick one; **text-type content supports `{{}}` variables**, while button/image/video/coordinates/JSON **do not**):
- **Text**: plain text (supports `{{}}`).
- **Card**: a card = title, body (**both support `{{}}`**) + up to 2 buttons; style `text` / `Image` (with an image) / `Video` (with a video) / `Location` (with a location). Button actions: `Call phone` / `Send SMS` / `Send email` / `Open web page` / `URL Scheme`.
- **Form**: a form = title, description (**both support `{{}}`**) + up to 3 fields (field name / display name / type / required / placeholder) + a submit button (button text + submit URL). ⚠️ Form submission is **purely outbound** (POST to the submit URL); **the data does not flow back into the flow**. To use the collected results in the flow, use "Form Collection / Conversational Collection".
- **JSON**: arbitrary JSON (does not support `{{}}`).

**Output:** the configured content flows downstream as its input, **replacing the upstream input** (replacement, not pass-through).

## Message Pass-through
**Sends a message directly** to the user at any point in the flow, displayed immediately without having to reach End. As for the data flow, it is a **pass-through**: the upstream input is passed verbatim to downstream, unaffected by this message.

**Message content:** a piece of text, supports `{{}}`, ≤2000 characters. ⚠️ **In the JSON, `content` MUST be a JSON STRING keyed by `contentType`** — e.g. `contentType:"Text"` → `content:"{\"Text\":\"...the text...\"}"`. A plain text string (not JSON-encoded) fails to parse and the message renders **empty**. Use the builder's `message_content(text, content_type)` (or just pass `content="plain text"` to `add("Message", ...)` — the builder auto-encodes it); the validator flags a non-JSON content as `MSG_CONTENT_NOT_JSON`.

**Output:** passes the upstream input through to downstream (the message is only sent to the user; downstream does not receive it); it **may also have no downstream**.

## Human Service
Hand off to a human — hand the conversation to a **third-party human customer-service system**, after which there is no more AI reply.

The vendor is set in the top-level `humanConfig.manufacturer`. Its value **MUST be a `HumanManufacturerEnum` value, not a display name** — one of: `Intercom`, `Webhook`, `LiveChat`, `SoBot`, `ZohoSalesIQ`, `LiveDesk`, `Omnichat` (`Omnichat` = the Crescendo Lab vendor). A display name such as `"livechat"`, `"Livedesk"`, `"Zoho Sales IQ"` or `"Crescendo Lab"` will fail import with `Invalid import file: value "..." is not allowed for field "manufacturer"`. `humanConfig.status` is `enable` / `disable`.

⚠️ **Also write `humanConfig` at the component level** (on the `Human` component itself), not only at the bot-entity level. The transfer-to-human config form renders from the component-level `humanConfig`; if it is missing the node's config shows up blank. The backend backfills entity→component on import, but the generator should set it directly on the component.

**Output:** no successor node; after the human handoff the flow ends here (terminal node).

## Conversational Collection
A built-in LLM that proactively asks the user through **multiple turns of conversation**, collecting the specified fields one by one (vs. "Form Collection" = pop up a form and fill it once).

**LLM core:** same as the LLM node (identity prompt / multimodal / exception mechanism); memory includes long-term memory / short-term memory / user attributes / key events.

**Collection fields:** you can add multiple, each = source (`Custom`) + field name + type (`String` / `Number` / `Integer` / `Boolean` / `datetime`) + description (supports `{{}}`). ⚠️ **In the JSON the field name MUST be `fieldName` (with `showName` as the display label), and `optionFieldType` is required (`null` for free text).** The keys `name` / `variableName` / `key` are silently dropped on import, after which the platform assigns random default names (age / user_birthday / …). `fieldName` becomes a variable key, so it must contain only **lowercase letters, digits, and underscores (`[a-z0-9_]`)**. Use the builder's `gather_fields()` which emits the correct shape; the validator flags a missing `fieldName` as `GATHER_FIELD_NAME` and a bad charset as `GATHER_FIELD_NAME_FORMAT`.

**Collection control:** automatically ends after more than N turns of conversation; the whole thing ends if the node runs longer than N minutes.

⚠️ **While collection is in progress it exclusively holds the interaction with the user** — at that point other branches cannot output content to the user.

**Output** (all **pass through the upstream input**, plus the collected content of this branch):
- `Collection complete`: taken when the fields are fully collected, attaching the **successfully collected content** (a list of field names + values).
- `Collection failed`: taken on exceeding turns / timeout / incomplete collection, attaching the **failed collection content**.
- Enable the exception mechanism to add an `Exception branch`.

## Form Collection
Renders a **visual form** for the user to fill in to collect fields (vs. "Conversational Collection" = the LLM asks over multiple turns). **No LLM core**, does not consume LLM. ⚠️ Do not use it on the API / third-party channels — the form cannot be rendered, which causes an exception.

**Form config:** title, body (both support `{{}}`).

**Form fields:** you can add multiple, each = field name + data type (`String` / `Number` / `Integer` / `Boolean` / `datetime`) + display name + input control (`Text input` / `Multiline text input` / `Number input` / `Phone input` / `Email input` / `Date input` / `Single choice` / `Multiple choice`) + required.

**Collection method:** `Item-by-item collection` (the conversation window shows one item at a time, step by step) / `One-time collection` (show all fields at once).

**Collection timeout:** the whole round ends if the node runs longer than N minutes.

⚠️ **While collection is in progress it exclusively holds the interaction with the user** — at that point other branches cannot output content to the user.

**Output** (all **pass through the upstream input**, plus the collected content of this branch):
- `All collected successfully`: taken when all fields are collected.
- `Other (collection timeout/incomplete)`: taken on timeout or incomplete collection.

---

## Variables and references

Reference with `{{...}}` in fields, **only variables upstream on the path**. In most cases the connection automatically brings in upstream content (such as the LLM's "user question / knowledge data"); only manually reference when you need to additionally pull a particular upstream output.

**Important**: if an upstream node **replaced** the input (such as Card Message, or the LLM outputting its own content), what downstream automatically receives is the replaced content; **if downstream needs the user's original input, it must explicitly inject it with `{{start_msg_text}}` etc.** (it cannot rely on the automatic carry-in). Pass-through nodes (knowledge search / condition / If-Else / variable assignment) don't change the input.

- **Node output**: `{{upstream_node_name}}` (give nodes descriptive names at design time; use `{{node_name.output_name}}` for a Workflow's multiple outputs; the real variable name is mapped by the generating skill).
- **Platform variables** (system `sys_*`, user input `start_msg_*`, browser `browser_*`, per-channel `wa_*/tg_*/...`, user attributes, custom variables): use the **real names**; **the full catalog is in `variables-reference.md`** — pick per scenario (especially channel attributes: an attribute exists only when its channel is connected).

## Connection rules

- **Multi-in**: each node's input can receive **multiple upstream merges** (e.g. multiple intents sharing one LLM, multiple branches merging into End).
- **Multi-out / fan-out**: each branch (output) can connect to **multiple parallel downstream nodes**.
- **Exceptions**: Start has no upstream (entry); End and Human Service have no downstream (terminal nodes); Message Pass-through may have no downstream.
- For branching nodes (Classifier/Condition/If-Else/Knowledge Search/Variable Assignment), **connect every meaningful branch** (especially fallbacks like `Other` / `Else` / exception branches).

---

# Per-component JSON fields & enum values

> All `flowRule.components[]` share one object schema (a "kitchen-sink" with ~60 fields); each
> `type` only uses a subset, leave the rest `null`/absent. **Every value below that is an enum
> must be the exact value listed — an out-of-enum string makes the backend import reject the whole
> file** (`Invalid import file: value "..." is not allowed for field "..."`). Run
> `scripts/validate_gptbots_config.py` after generating; it checks all of these.

**Common to every component:** `type` (FlowComponentType), `id` (unique integer), `name`, `title`,
`x`, `y` (canvas coordinates — see Connections & handles), `nextComponents[]` (outgoing edges).

### PromptMessage object shape (LLM-capable nodes) — `text`, never `content`

Every entry of a node's `messages[]` (and `datasetMessages[]`) is exactly:
```json
{"lineId": null, "type": "Role", "text": "…the prompt…", "ids": [], "upstream": null, "children": null, "datasetType": null}
```
The prompt text lives in **`text`**. ⚠️ A `content` key here is the **wrong field** (that's the
reply field of `Message`/`Predefine` nodes) — on import the prompt **deserializes BLANK** and the
node silently runs with no instructions. The standard array is, in order:
`[Role, LongMemory, ShortMemory, Plugin, Input]` — plus a `Condition` entry (the If-text) right
before `Input` on `Condition` nodes. `LongMemory`/`ShortMemory`/`Plugin` are present with empty
`text`. The trailing **`Input`** message's `upstream` = the id of the node feeding this one, with a
display label `"name(title)"`. Knowledge retrieval is NOT a message — set `dataEnable: true` and
`datasetMessages: [{… type:"Content" …}]` on the consuming LLM (the builder's `reads_kb=True`).
The builder assembles all of this automatically; the validator flags `content`-keyed prompts as
`MSG_CONTENT_FIELD` and an empty Role as `MSG_ROLE_EMPTY`.

| `type` | Key fields it uses (beyond the common ones) | Outputs |
|---|---|---|
| `Input` | — (flow entry) | single |
| `Output` | — (flow endpoint) | none (terminal) |
| `LLM` | `chatModelVersionId` (leave blank → backfilled), `messages[]` (PromptMessage), `maxRespTokens`, `responseFormat`, `memoryEnable`/`longTermMemory`/`shortTermMemory`/`userPropertyEnable`, `toolsEnable`/`databaseEnable`, `reasoningEffort`/`showReasoning`/`reasoningEnabled`, `multiResponseTypes[]`, `multiModalLlmInput`, `exceptionSwitch` | `success` (+ `_exception` if `exceptionSwitch`) |
| `Branch` (Classifier) | `messages[]` = `[Role, ShortMemory, Input]` only (no LongMemory/Plugin — the classifier has no long-term memory; the prompt does NOT hold the per-category rules), `branchRunMode` (`EXTRACT`/pass-through), branches carried by `nextComponents[]` (each edge: `name` = category label, `condition` = the **routing-rule text**), `exceptionSwitch` | one per branch + the built-in Other (`name:"_other"`, `condition:""`). **No `branch_exception` edge** — the classifier's exception is the preset `exceptionSwitch` row, never a wired edge. |
| `Condition` | `messages[]` (LLM core), `exceptionSwitch` | `true` / `false` (+ `_exception`). IF text on the `conditions_true` edge's `condition` (`name:"_true"`); `conditions_false` is `name:"_false"`, `condition:""`. |
| `Bool` (If/Else) | `regularGroups[]` (no LLM) | `true` / `false` / `other` |
| `Dataset` (Knowledge) | `docCorrelation` (0–1), `matchDataLimit` (1–50), `embeddingRate`, `rerankSwitch`/`rerankModelVersionId`, `dataSourceShowType`, `customKnowledgeType`, `docGroupIds` (real ids or empty), `metadataFilter` | `true` (found) / `false` (no result) |
| `Variable` | `variableSetValueConfigs[]` | `true` / `exception` |
| `Regular` | `regularGroups[]` (`id`, `combine`, `items[]`) | per group `<groupId>_true` / `false` |
| `Predefine` (Card) | `contentType` + `content` | single |
| `Message` | `contentType` + `content` (text ≤2000) | single (may be terminal) |
| `Human` | `humanConfig` (see Human Service above) | none (terminal) |
| `ChatGather` | `messages[]` (LLM core), `gatherFields[]`, `gatherControl` (`chatCountLimit`, `timeoutLimit`), `exceptionSwitch` | `true` / `false` (+ `_exception`) |
| `FormGather` | `gatherFields[]` (+ `isRequired`, `optionFieldType`), `gatherControl` (`formGatherType`, `timeoutLimit`), `formGatherConfig` (`title`, `content`, `multiLanguages`); no LLM | `true` / `false` |
| `ToolApi` | `toolApiParam` (`toolId`, `toolApiId`, `url`, `inputs[]`, `outputs[]`) | single |
| `Workflow` | `workflowParam` (`workflowId`, `inputs[]`, `outputs[]`) | single |

### Enum value sets (exact, case-sensitive)

Top-level **and** per-component (a field may appear in both places):
- `reasoningEffort`: `MINIMAL` `LOW` `MEDIUM` `HIGH`
- `showReasoning`: `SHOW` `COLLAPSE` `HIDDEN`
- `dataSourceShowType`: `MIN_SHOW` `LIST_SHOW` `CORNER_SHOW`
- `customKnowledgeType`: `DEFAULT` `LLM`
- `responseFormat`: `Text` `JsonObject` `JsonSchema`  *(enum names — NOT `text`/`json_object`)*
- `modeType` (top-level only): `general` `excellent` `specialist`
- `multiResponseTypes[]`: `Text` `Image` `File` `Audio` `Video` `Document`

Component-nested:
- `contentType` (Predefine/Message): `Form` `Text` `Json` `Card`
- `messages[].type` / `datasetMessages[].type` (PromptMessage): `Role` `LongMemory` `ShortMemory` `Dataset` `Input` `Output` `Plugin` `Content` `Choices` `Condition` `Attr` `Gather`
- `gatherFields[].gatherType`: `userProperty` `selfDefining`
- `gatherFields[].valueType`: `string` `bool` `integer` `number` `datetime` `list`
- `gatherFields[].optionFieldType` (FormGather): `string` `multiString` `bool` `integer` `number` `datetime` `phoneNumber` `email` `radio` `checkbox`
- `gatherControl.formGatherType` (FormGather): `single` `all`
- `variableSetValueConfigs[]` real shape: `{variableName, operation, value}` — `operation` is `Cover` `Clear` `Append` (**capitalized**, not `COVER`/`CLEAR`/`APPEND`). `value` may embed `{{...}}`. (The legacy `variableType`/`variableOperateType` fields are not in the real export.)
- `regularGroups[].combine`: `and` `or`
- `regularGroups[].items[].category`: `GlobalVariable` `UserProperty` `BrowserProperty` `Upstream` `WhatsApp` `Telegram` `LiveChat` `LiveDesk` `Line` `Start` `CustomVariable` `KeyEvent`
- `regularGroups[].items[].type`: `string` `number` `datetime` `bool` `list`
- `multiModalLlmInput.fileMode`: `SYSTEM` `LLM` `DISABLED`
- `humanConfig.manufacturer` / `humanConfig.status`: see the Human Service section above.

> ⚠️ **Top-level `multiModal` is mandatory in every delivered `.bot`** (auto-save NPE guard):
> the import copies `multiModal` verbatim with **no default backfill**, while the console
> auto-save dereferences `multiModalForm.multiModalInput.chatMode` **without a null check**
> (backend regression 2025-12-02). A `.bot` imported without it imports fine but then returns
> HTTP 500 on **every** auto-save — the bot is uneditable. Normally-created bots get defaults
> at creation and never hit this; only imported bots do. Minimal safe shape:
> `"multiModal": {"multiModalInput": {}}` — an empty object gives a non-null VO whose null
> `chatMode` is safe downstream (only ever compared against `INTERRUPT`). The builder emits
> this automatically; the validator flags its absence as `L0_MULTIMODAL_AUTOSAVE_NPE`.
>
> ⚠️ Do **not** set `multiModal` input/output `audioMode`/`chatMode`/`imageMode` from guesswork —
> the same key uses different enums on input vs output. Copy them from a real exported `.bot`;
> omitting them (null) is always safe.
>
> ⚠️ **Duplicate exception edges are a known import artifact**: platform round-trips have been
> observed duplicating a Condition's exception exit (an old `Exception` entry with
> `condition=null` + a new `_exception` entry, same id/sourceHandle). The engine tolerates it
> (nextComponents is pass-through) but it's dirty data — the validator warns as `EDGE_DUP_LINE`;
> remove the duplicates before re-delivery.

---

# Connections & handles (avoid distorted lines)

Each edge lives in the **source** component's `nextComponents[]` as:
`{ id, nextComponentId, sourceHandle, targetHandle, condition, sort, name }`.

**Strong-typed Integer fields — wrong type is import-fatal:** the backend deserializes with strict
Jackson typing (`BotFlowComponent.id` is Integer; `BotFlowNext.id/nextComponentId/sort` are
Integer; `x`/`y` are Integer), and the global ObjectMapper has `FAIL_ON_UNKNOWN_PROPERTIES=false`
— so EXTRA fields never fail an import, only wrong TYPES do, always with the signature error
`value X is not allowed for field "…"` (same as `exportTime`).

| Field | Type | Trap |
|---|---|---|
| `components[].id` | bare int | `"1"` (quoted) or `vueflow__node-...` string → rejected |
| `components[].x` / `y` | bare int | quoted numbers / floats |
| `nextComponents[].id` | bare int | `"e1"`, `vueflow__edge-...` (the frontend canvas is VueFlow, but the backend type is still Integer) |
| `nextComponents[].nextComponentId` | bare int | must equal an existing component `id` |
| `nextComponents[].sort` | bare int | **set it equal to the edge `id`** (globally unique) |

Use unique edge ids that don't collide with component ids, e.g. `100001, 100002, …` (100000+seq). ⚠️ **`sort` must be globally unique too — set `sort == id`.** A per-node counter (1, 2, … restarting at each node) makes edges across the bot share sort values; that collision makes the canvas mis-render and shows branch **target nodes as greyed/unusable**. The validator flags duplicate sorts as `EDGE_SORT_DUP`.
The builder's `connect()` generates these automatically; the validator flags violations as
`EDGE_ID_NOT_LONG` / `EDGE_INT_FIELD` / `FLOW_COMP_ID_NOT_INT` / `FLOW_COMP_XY_NOT_INT` /
`EDGE_ID_DUP`. **Before delivery, recursively scan the JSON: any quoted number or string in an
`id`/`nextComponentId`/`sort`/`x`/`y` position must become a bare integer.**

**Routing vs rendering — what each field is for:** the runtime routes **only** by `nextComponentId` (the engine does not read the handles), so a wrong `sourceHandle`/`targetHandle` does **not** misroute execution. Handles are purely the **canvas** port anchors: when a handle id can't be resolved to a rendered port, the edge endpoint falls back to the node origin and the line draws distorted/misrouted. That visual breakage is why the validator still flags every handle mismatch as an error — a flow that looks broken on the canvas is not deliverable. `targetHandle` is fully deterministic (target id + target type, no suffix); only `sourceHandle` carries an output suffix (below).

**Handle id format:** `{side}{componentId}-{handleKey}[_{suffix}]`
- `right…` = an **output** handle of *this* (source) component → goes in `sourceHandle`.
- `left…` = an **input** handle of the *destination* component → goes in `targetHandle`.

**Invariants (violating any of these makes the canvas draw a distorted / misrouted line, because the
handle can't be resolved and the edge falls back to the node origin):**
1. `sourceHandle` = `right{thisComponentId}-{sourceKey}[_suffix]` — the id **must** equal the
   component that owns the `nextComponents` entry.
2. `targetHandle` = `left{nextComponentId}-{targetKey}` — the id **must** equal `nextComponentId`.
3. The `{handleKey}` must match the component type (table below).

**Per-type handle keys** (left = target/input key · right = source/output key):

| type | target key (`left…`) | source key (`right…`) |
|---|---|---|
| Input | input | input |
| Output | output | — (terminal) |
| LLM | LLM | LLM |
| Bool | boolean | boolean |
| Branch | branch | branch |
| Predefine | preset | preset |
| Message | message | message |
| Dataset | knowledge | knowledge |
| Human | artificial | — (terminal) |
| Condition | conditions | conditions |
| Regular | regular | regular |
| ChatGather | qa-collect | qa-collect |
| **FormGather** | **form-collect** | **formgather** *(asymmetric!)* |
| ToolApi | toolapi | toolapi |
| Workflow | workflow | workflow |
| Variable | variable | variable |

**Output suffixes on `sourceHandle`** (single-output types — LLM/Message/Predefine/ToolApi/Workflow
— carry no suffix on the success path):
- Branch: `branch_1` / `branch_2` / … (**sequential per classifier**) per category + `branch_other`; the edge's `condition` carries the **routing-rule text** (a natural-language string), NOT an id. ⚠️ **The built-in Other edge MUST be `name:"_other"` + `condition:""`** (an empty string, NOT null/omitted) so the platform maps it to the bottom built-in Other. Using `name:null` backfires — the platform renders branch_other as an editable BLANK category, and deleting it loses the Other route. Every classifier needs exactly one branch_other edge. **There is no `branch_exception` edge** — the classifier's exception is the system-preset `exceptionSwitch` row (set `exceptionSwitch=true`; do not wire an exception edge), and the validator flags `branch_exception` as `BRANCH_EXCEPTION_EDGE`. The validator also flags a wrong/absent Other (`BRANCH_OTHER_NAME` / `BRANCH_NO_OTHER`) and a numeric id in `condition` (`BRANCH_RULE_IS_ID`).
- Bool: `boolean_true` / `boolean_false` / `boolean_other`.
- Condition: `conditions_true` (edge `name:"_true"`, `condition` = the IF text) / `conditions_false` (edge `name:"_false"`, `condition:""`).
- Dataset: `knowledge_true` (found) / `knowledge_false` (no result).
- Regular: `regular_<groupId>_true` / `regular_<groupId>_false`; `condition` carries the group id.
- ChatGather: `qa-collect_true` / `qa-collect_false`.
- FormGather: `formgather_true` / `formgather_false`.
- Variable: `variable_true` / `variable_exception`.
- Exception outlet (a wired edge when `exceptionSwitch=true`): LLM `LLM_exception`, Condition `conditions_exception`, ChatGather `qa-collect_exception`, Variable `variable_exception`. **The Classifier (Branch) is excluded** — its exception is the preset `exceptionSwitch` row, not a `branch_exception` edge.

**Common wrong handles (all draw distorted lines — never emit these):**
- Capitalized / wrong key: `left7-Branch`, `left7-Dataset`, `left2-Output` → keys are case-sensitive and mostly lowercase (only `LLM` is uppercase); use `left7-branch`, `left7-knowledge`, `left2-output`.
- Made-up Dataset outputs: `right7-hasresult` / `right7-noresult` → use `right7-knowledge_true` / `right7-knowledge_false`.
- Semantic / invented Branch keys: `right5-product`, `right5-branch1` → use `right5-branch_1`, `right5-branch_2`, … (sequential per classifier) and `right5-branch_other` for the fallback. Do **not** use a timestamp id here, and do **not** put the id in `condition` — the rule text goes in `condition`.

**Example** (LLM #4 → Output #2, and Branch #5 → Dataset #7 on its first category):
```json
{ "id": 100001, "sourceHandle": "right4-LLM",        "targetHandle": "left2-output",    "nextComponentId": 2, "sort": 100001 }
{ "id": 100002, "sourceHandle": "right5-branch_1",   "targetHandle": "left7-knowledge", "nextComponentId": 7, "sort": 100002,
  "name": "faq", "condition": "The user is asking about product features, usage, or rules." }
```

**Layout:** each node renders ~320px wide; place components with generous horizontal/vertical spacing
(left→right by flow order) so edges route cleanly. The Input node is the single entry (left), the
Output node the single exit (right). After generating, run the validator — it verifies invariants
1–3 above; fix any `EDGE_*` error before delivery.
