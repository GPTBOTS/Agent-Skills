# Latest `.bot` configuration Skill evaluations

Run each prompt once without the updated Skill as a baseline and once with `gptbots-agent-skill` version `1.4.0`. Evaluate behavior, not exact wording.

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
- Runs the validator before delivery.
