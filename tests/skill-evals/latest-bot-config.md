# Latest `.bot` configuration Skill evaluations

Run each prompt once without the updated Skill as a baseline and once with `gptbots-agent-skill` version `1.4.1`. Evaluate behavior, not exact wording.

## Service tips

**Prompt**

> Update this exported FlowAgent `.bot` so its LiveDesk Human node sends a custom English transfer-failure message. I did not specify whether the service-tip switch should be on or off.

**Expected behavior**

- Reads `bot-config-fields.md`.
- Writes the message as integer `code=84` under the Human component's `humanConfig.multiLanguages.en`.
- Preserves an existing `sendHumanTipSwitch`, or leaves it omitted when absent; does not invent a universal default.
- Preserves unrelated component and bot fields.
- Runs the validator before delivery.

## Conversation properties

**Prompt**

> Add a string conversation property for an order ID, set it from a FlowAgent Variable component, and show how to supply it through the public conversation API.

**Expected behavior**

- Adds a unique top-level `customVariables[]` definition using a `var_` name and backend type `STRING`.
- Treats the `.bot` value as a default, not a captured conversation value.
- Uses `variableType=CUSTOM_VARIABLE` in the Variable component.
- Uses the same predefined key under `conversation_config.custom_variables` and explains conversation scope.
- Does not write runtime conversation state into `.bot`.

## User properties

**Prompt**

> Add a user property named customer tier that the Agent can read and update during chat, with a default of standard.

**Expected behavior**

- Adds one `userProperties[]` definition with `name`, `showName`, `type`, `value`, `desc`, `chatUpdate`, and `chatQuery`.
- Uses a valid lowercase property type and JSON booleans.
- Checks that the name does not collide with `customVariables[]`.
- Does not add `accountId`, nested `userProperties`, or any real user's value history.
- Only claims an update was saved after the result marks that property successful and not failed; uses read-after-write verification when persistence matters.
- Runs the validator before delivery.

## Read-only user property

**Prompt**

> Add a customer tier user property that the Agent may read but must not update during chat. Make its runtime response honest if a user asks it to save a different tier.

**Expected behavior**

- Sets `chatQuery=true` and `chatUpdate=false`.
- Adds a prompt rule that the Agent must say the property cannot be changed in chat.
- Does not claim the value was saved from an attempted call or an HTTP/tool success alone.
- Points API-driven updates to `/v1/property/update` and verifies persistence through the result collections or `/v2/user-property/query`.
