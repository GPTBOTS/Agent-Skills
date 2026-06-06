# GPTBots Referenceable Variables

> Reference with `{{variable_name}}`, **only variables upstream on the path**. **Channel attributes exist only for the connected channel** (`wa_*` only when WhatsApp is connected, `tg_*` only when Telegram is connected…). Pick the right ones per scenario at design time.

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

## User attributes / custom variables (must be defined first)
- `{{<attribute_name>}}`: **user attribute** (bound to the user, e.g. `name`)
- `{{<variable_name>}}`: **custom variable** (agent-global)

## Node output
- `{{<upstream_node_name>}}`: reference an upstream node's output (give nodes unique, descriptive names at design time; the real platform variable name is mapped by the generating skill).

## Picking variables by scenario
- **Multilingual**: `sys_lang` / `browser_lang` / `tg_lang_code` follow the user's language.
- **Source routing**: `sys_conversation_source` to determine which channel the request came from.
- **Web acquisition personalization**: `browser_region` (region) / `browser_current_url`, `browser_source_url` (referrer page).
- **Channel identity/contact**: use `wa_user_name` to address the user on WhatsApp; use `ld_email` / `ld_phone` for contact info on LiveDesk.
