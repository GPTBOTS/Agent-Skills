# GPTBots `.bot` human-service and property fields

> Use this reference whenever a `.bot` task reads, creates, or updates service tips, service-status messages, custom variables, conversation properties, or user properties. Preserve unrelated exported fields exactly; do not invent credentials, ids, or runtime user data.

## Field locations

| Capability | `.bot` field | Scope |
|---|---|---|
| Send service tips | `humanConfig.sendHumanTipSwitch` | Bot-level human configuration; also copy to a FlowAgent Human component when that node owns the configuration |
| Service-status messages | `humanConfig.multiLanguages.<language>[]` | Localized human-service status text |
| Custom-variable definitions | `customVariables[]` | Agent definitions and defaults |
| Conversation-property values | Public API `conversation_config.custom_variables` or a FlowAgent Variable component | Runtime values persisted in one conversation; not exported in `.bot` |
| User-property definitions | `userProperties[]` | Agent definitions and defaults shared by users |
| User-property values | User API or conversation collection/update | Runtime values bound to an individual user; never export in `.bot` |

All fields in this reference are optional. An older `.bot` without them remains valid.

## Send service tips

`sendHumanTipSwitch` is a JSON boolean. Use `true` or `false`, never the strings `"true"` or `"false"`.

The missing-value behavior is intentionally different between two runtime paths:

| Runtime path | Affected message | Missing or `null` |
|---|---|---|
| Flow Human component + LiveDesk | transfer failure, `code=84` | enabled |
| Existing LoopAgent + LiveChat in-channel handoff | handoff trigger, `code=36` | disabled |

Do not normalize a missing value to one universal default. When updating an existing `.bot`, preserve the field unless the user explicitly changes it. When creating a new configuration and the user has not chosen a value, omit the field.

The switch currently controls only the two paths above. Do not promise that it changes ordinary Agent or FlowAgent same-channel handoff behavior in other integrations.

## Localized service-status messages

`multiLanguages` maps each platform language key, such as `en`, `ja`, or `th`, to an array of `{code, text}` objects:

```json
{
  "humanConfig": {
    "sendHumanTipSwitch": true,
    "multiLanguages": {
      "en": [
        {"code": 36, "text": "Connecting you to human support."},
        {"code": 84, "text": "The transfer failed. Please try again later."}
      ],
      "ja": [
        {"code": 36, "text": "有人サポートに接続しています。"},
        {"code": 84, "text": "転送に失敗しました。後でもう一度お試しください。"}
      ]
    }
  }
}
```

Supported status codes:

| Code | Meaning |
|---|---|
| `29` | entering human service |
| `30` | waiting timeout / ask whether to keep waiting |
| `31` | human service connected |
| `33` | user ended human service |
| `34` | support agent ended human service |
| `35` | human-service conversation timed out |
| `36` | calling or triggering human service |
| `37` | outside service hours |
| `38` | human service not ready |
| `84` | transfer failed |

Within one language, each code may appear at most once. Keep `code` as an integer and `text` as a string. Unknown integer codes may come from a newer backend, so preserve them when editing and treat them as a compatibility warning rather than deleting them.

For a FlowAgent Human component, write the intended `humanConfig` on `flowRule.components[].humanConfig`. The bot-level `humanConfig` may remain as a fallback, but it does not replace component-level configuration for authoring.

## Custom variables and conversation properties

`customVariables[]` stores definitions and default values, not values captured during a particular conversation:

```json
{
  "customVariables": [
    {
      "name": "var_order_id",
      "type": "STRING",
      "value": ""
    },
    {
      "name": "var_retry_count",
      "type": "INTEGER",
      "value": "0"
    }
  ]
}
```

Valid backend types are `STRING`, `INTEGER`, `NUMBER`, `BOOLEAN`, `DATETIME`, `OBJECT`, `ARRAY_STRING`, `ARRAY_INTEGER`, `ARRAY_NUMBER`, `ARRAY_BOOLEAN`, `ARRAY_OBJECT`, `FILE`, and `ARRAY_FILE`.

For newly generated `.bot` files, prefer the platform UI's editable subset: `STRING`, `INTEGER`, and `NUMBER`. Preserve any other valid backend type already present in an exported file. The exported entity stores `value` as text; for complex types, preserve the platform-exported representation instead of inventing serialization rules.

Use the `var_` prefix for newly created custom-variable names. Existing exports without the prefix are compatible and should only produce a warning. Names must be unique across `customVariables` and `userProperties`, because runtime replacement resolves both through one flat namespace.

Conversation properties are values assigned to these definitions for one conversation. Set them through:

- `conversation_config.custom_variables` when creating/sending a public API conversation request; use only names already defined in `customVariables[]`.
- A FlowAgent Variable component with `variableType=CUSTOM_VARIABLE`; downstream nodes read the updated value immediately and later turns in the same conversation keep it.

Never copy a real conversation's value map into the top-level `.bot`; doing so leaks runtime state and changes the default for every future conversation.

## User properties

`userProperties[]` stores reusable definitions:

```json
{
  "userProperties": [
    {
      "name": "customer_tier",
      "showName": "Customer tier",
      "type": "string",
      "value": "standard",
      "desc": "Support tier used for routing",
      "chatUpdate": true,
      "chatQuery": true
    }
  ]
}
```

Valid `type` values are `string`, `number`, `datetime`, `bool`, and `list`.

For newly generated definitions, include `name`, `showName`, `type`, `value`, `desc`, `chatUpdate`, and `chatQuery`. Both flags are JSON booleans:

- `chatUpdate`: the conversation may collect or update this property.
- `chatQuery`: the conversation may read this property.

Preserve backend-managed typed-value fields if they already exist in an exported definition, but do not invent them in a new definition.

Never generate or populate `accountId` or nested `userProperties` inside a definition. Current backend exports can retain these keys as `null` placeholders; preserve them when editing an official export, but any non-null value is per-user runtime data and must fail privacy validation.

## Editing checklist

1. Identify whether the value is a definition, a default, a conversation value, or a user value.
2. Preserve omitted `sendHumanTipSwitch` values unless the user explicitly chooses a setting.
3. Put Flow Human settings on the Human component, not only at the bot level.
4. Keep service-status codes numeric and unique within each language.
5. Keep custom-variable and user-property names unique across both arrays.
6. Exclude conversation values and per-user runtime data from `.bot`.
7. Run `../scripts/validate_gptbots_config.py <file.bot>` before delivery.
