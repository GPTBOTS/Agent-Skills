# GPTBots Referenceable Variables

> Reference with `{{variable_name}}` (**double braces**), **only variables upstream on the path**. **Channel attributes exist only for the connected channel** (`wa_*` only when WhatsApp is connected, `tg_*` only when Telegram is connected…). Pick the right ones per scenario at design time.
>
> ⚠️ **Never run `str.format()` / f-strings over prompt text that contains `{{...}}`** — `.format()` collapses `{{sys_lang}}` → `{sys_lang}`, and a single-braced variable is no longer recognized by GPTBots (it renders literally). When templating a prompt in a generator, substitute with `.replace("{placeholder}", value)`, not `.format()`. The validator warns `MSG_SINGLE_BRACE_VAR` on any single-brace variable it finds in a prompt or message.

## System / global (`sys_*`, available on any agent)
- `sys_conversation_id` conversation ID
- `sys_user_id` user ID · `sys_anonymous_id` anonymous ID · `sys_user_email` user email
- `sys_lang` language · `sys_conversation_source` conversation source channel
- `sys_user_msg_count` (number) user message count (`=1` means the first message)
- `sys_agent_id` · `sys_dev_id` · `sys_sso_access_token`

## User input (`start_msg_*`, from Start)
- `start_msg_text` (string) user text
- `start_msg_image` / `start_msg_audio` / `start_msg_video` / `start_msg_document` / `start_msg_file` (all **array**, may contain multiple attachments)

## Browser (`browser_*`, web channel)
- `browser_lang` language · `browser_region` region · `browser_timezone` timezone · `browser_os` · `browser_info`
- `browser_current_url` current page · `browser_source_url` referrer page · `browser_duration_of_stay` (number) dwell time

## Channel attributes (only when the corresponding channel is connected)
- **WhatsApp**: `wa_user_id` · `wa_user_name` · `sender_whatsapp` (object)
- **Telegram**: `tg_user_id` · `tg_user_name` · `tg_lang_code`
- **LiveChat**: `lc_org_id` · `lc_chat_id` · `lc_thread_id` · `lc_user_id`
- **LiveDesk**: `ld_user_id` · `ld_conversation_id` · `ld_contact_id` · `ld_phone` · `ld_email` · `ld_full_name` · `ld_channels_sender` (object) · `ld_user_sender` (object)
- **LINE**: `line_user_id`

## User properties / custom variables (must be defined first)
- `{{<property_name>}}`: **user property**, defined in top-level `userProperties[]`; its runtime value is bound to one user and can cross conversations when the platform has a stable user identity.
- `{{<variable_name>}}`: **custom variable / conversation property**, defined in top-level `customVariables[]`; its runtime value belongs to one conversation and can differ from the `.bot` default.

Definitions and runtime values are separate. `.bot` contains definitions/defaults only. Set conversation values through `conversation_config.custom_variables` or a FlowAgent Variable component; set user values through the User API or an enabled conversation update. See `./bot-config-fields.md` for schemas and privacy boundaries.

## Node output
- `{{<upstream_node_name>}}`: reference an upstream node's output (give nodes unique, descriptive names at design time; the real platform variable name is mapped by the generating skill).

## Picking variables by scenario
- **Multilingual**: `sys_lang` / `browser_lang` / `tg_lang_code` follow the user's language.
- **Source routing**: `sys_conversation_source` to determine which channel the request came from.
- **Web acquisition personalization**: `browser_region` (region) / `browser_current_url`, `browser_source_url` (referrer page).
- **Channel identity/contact**: use `wa_user_name` to address the user on WhatsApp; use `ld_email` / `ld_phone` for contact info on LiveDesk.
