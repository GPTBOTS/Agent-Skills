# Create / optimize a GPTBots Audio Agent (.bot)

> Reference for the `GPTBots Skill` workflow when the target is an **Audio Agent** (`botType=Audio`) — a voice/telephony agent. Produces an importable `.bot` with `exportType=BOT`.

## 1. What an Audio Agent is

An Audio Agent is a **QuestionAnswer-shaped bot with a voice engine bolted on**. It reuses the whole flat Agent config (knowledge, tools, workflows, memory, human handoff) and adds one block: `multiModal`, which carries the engine mode, VAD, output, call control, welcome media and — importantly — its **own identity prompt**.

There is no canvas and no rule graph. Everything lives in top-level fields plus `multiModal`.

## 2. Pick the engine mode first — it decides the whole model wiring

`multiModal.engineMode` is **mandatory** (`AudioEngineMode`); an Audio Agent without it cannot start a session (`engineMode not configured`).

| mode | pipeline | model requirement | where the model ids go |
|---|---|---|---|
| `REALTIME` | one realtime model handles audio in **and** audio out | the chat model must declare the **realtime** capability | `chatModelVersionId` = the realtime audio LLM; voice = `multiModalOutput.audioVoice` |
| `ASR_LLM_TTS` | speech→text, text LLM, text→speech | audio model must have **SPEECH2TEXT** *and* **TEXT2SPEECH** | `multiModalInput.audioModelVersionId` = ASR; `chatModelVersionId` = text LLM; `multiModalOutput.audioModelVersionId` = TTS |
| `LLM_TTS` | audio-in LLM + TTS (no separate ASR) | audio model must have **TEXT2SPEECH** | `chatModelVersionId` = audio-input LLM; `multiModalOutput.audioModelVersionId` = TTS |

The backend rejects a mode whose model lacks the matching capability with `AUDIO_MODEL_CAPABILITY_MISMATCH`. **Leave every model id blank in a generated `.bot`** — the import backfills platform defaults (`BotModelVersionFixer` replaces ids the target environment does not know), and inventing one produces a bot that fails on the first call. Tell the user to pick the models in the console after import, and say which slots they need to fill for the mode you chose.

## 3. The identity prompt is `multiModal.identityPrompt` — not `prompt`

Audio Agents carry a **voice-specific identity prompt**, shared by all three engine modes and injected as the system message of whichever LLM carries the turn. The top-level `prompt` field is not what the voice session reads.

Write it for **speech, not for reading**:
- Short sentences. No markdown, no bullet lists, no tables, no emoji, no URLs read aloud — anything the TTS has to pronounce should be pronounceable.
- State how to handle silence, interruptions and mishearing ("if you don't understand, ask once, briefly").
- Give numbers, IDs and amounts a spoken format ("say the order number digit by digit").
- Keep it short. Every token is on the latency path of a real-time conversation.
- Platform variables use `{{var}}` and are substituted at session start (see `./variables-reference.md`).

## 4. `multiModal` block reference

All ranges below are enforced server-side by `AudioConfigValidator` (`AUDIO_CONFIG_PARAM_RANGE` on violation).

```jsonc
"multiModal": {
  "engineMode": "REALTIME",              // REALTIME | ASR_LLM_TTS | LLM_TTS  (required)
  "identityPrompt": "…",                 // the voice identity prompt (§3)

  "multiModalInput": {                   // must exist — shared auto-save NPE guard
    "audioMode": "ASR",                  // BotAudioModeEnum: ASR | LLM | DISABLED
    "chatMode": "INTERRUPT",             // BotChatModeEnum: Q_A | INTERRUPT
    "textSwitch": true,
    "fileMode": "DISABLED",              // SYSTEM | LLM | DISABLED
    "imageMode": "auto",                 // auto | low | high
    "fileLimit": 1,
    "fileSupportTypes": ["Image","Audio","Video","File","Document"],
    "audioModelVersionId": "",           // ASR model (ASR_LLM_TTS only) — leave blank
    "asrPrompt": "",                     // ASR biasing hint (product names, jargon)
    "transcribeQuality": "standard",      // "standard" | "high"
    "sourceLang": { "autoDetect": true }  // MUST contain a boolean autoDetect
                                          // fixed language: {"autoDetect": false, "languages": ["en"]}
  },

  "multiModalOutput": {
    "textLanguage": "auto",
    "audioMode": "DEFAULT",              // BotAudioModeType: DEFAULT (tts-1) | HD (tts-1-hd)
    "audioVoice": "alloy",               // none|alloy|echo|fable|onyx|nova|shimmer
    "audioModeOutput": "TTS",            // BotAudioOutputModeEnum: TTS | LLM | DISABLED
    "audioModelVersionId": "",           // TTS model — leave blank
    "textSwitch": true,
    "showAiGeneratedContent": false,
    "symbolFilter": {                    // TTS text cleaning (see below)
      "remove": ["≈","*","&","^","_","~","|","#","@","<",">","{","}","＝","＋"],
      "replace": [{"from":"《》","to":" "}, {"from":"【】","to":" "}, {"from":"[]","to":" "},
                  {"from":"()","to":" "}, {"from":"（）","to":" "}]
    }
  },

  "vad": {
    "pauseThresholdMs": 500,             // [0, 5000]   silence that ends a user utterance
    "interruptSensitivity": 0.5,         // [0, 1]
    "interruptible": true,               // barge-in: may the user cut the agent off
    "recognitionMode": "server",         // "semantic" | "server" | "preset"
    "responseSpeed": "medium",           // "low" | "medium" | "high"  (semantic mode)
    "minVolume": 0.5,                    // [0, 1]
    "activationThreshold": 0.5           // [0, 1]  higher = harder to trigger
  },

  "output": {
    "showControl": false,
    "bufferMs": 200,                     // [0, 1500]
    "bgSound": { "mode": "DISABLED",     // DISABLED | PRESET | CUSTOM
                 "presetId": null, "uploadUrl": null, "volume": 20 }  // volume [1, 50]
  },

  "callControl": {
    "coldStart": { "silenceThresholdSec": 10,   // [5, 60]
                   "promptText": "" },
    "hangup":    { "maxCallSec": 600,           // [30, 3600]
                   "maxSilenceSec": 60,         // [1, 180]
                   "maxSilenceCount": 5,        // [1, 100]
                   "hangupPromptText": "" }
  },

  "welcome": {                            // per-language maps; values are URLs
    "speakingAvatar": { "en": "https://…/speaking.mp4" },   // MP4 < 5 MB
    "waitingAvatar":  { "en": "https://…/waiting.mp4" },    // MP4 < 5 MB
    "welcomeAudio":   { "en": "https://…/hello.mp3" },      // MP3 < 200 KB
    "welcomeMessage": { "en": "Hi, how can I help?" }       // pre-recorded opening text
  }
}
```

Notes that bite:
- **`sourceLang.autoDetect` must be a boolean.** Any other type (including the string `"true"`) is rejected outright. Omit `sourceLang` entirely if you do not need it.
- **`maxRespTokens` must be > 0 and ≤ the chat model's context limit.** Audio budgets knowledge and plugin tokens as `tokensLimit − maxRespTokens`, so an oversized value makes the knowledge budget negative. Since you leave model ids blank, keep `maxRespTokens` modest (1024–4096).
- **`symbolFilter`** is applied before TTS: `remove` strips symbols so they are not spoken, `replace` maps a token to a single space (bracket **pairs** are one token — `"()"`, not `"("` and `")"`) so the TTS pauses naturally instead of reading "left parenthesis". New Audio Agents are seeded with the default sets shown above; keep them unless the user wants different ones.
- **Welcome avatars** are only auto-seeded on the SaaS global site. Any URL you write must be public `http(s)` — the import security scanner rejects internal/loopback addresses in URL fields.
- `vad.interruptible = false` disables barge-in entirely; combine with `chatMode = Q_A` for strict turn-taking, or `INTERRUPT` + `interruptible = true` for natural conversation.
- Knowledge bases and data tables are bound **bot-level** (like a QuestionAnswer agent), not through any rule block — and, as with every type, the ids are cleared on import.

## 5. Everything else is a normal Agent

Top-level fields behave exactly as in `./create-gptbots-agent.md`: `firstMessage` (not `welcomeMessage`), `presetQuestions` (not `guidingQuestions`), `creativityLevel ∈ [0, 0.95)` or null, `dataEnable` + knowledge tuning, `memoryEnable` / `shortTermMemory` / `shortTermMemoryRound`, `toolsEnable`, `workflowEnable` + `associatedWorkflows`, `humanConfig`, `plugins`, `userProperties`, `chatSecurityConfig`. `exportTime` must be an epoch-**milliseconds** bare integer.

## 6. Generate with the builder

```python
from build_gptbots_audioagent import audio_config, save
from gptbots_prompts import load_prompt_store

P = load_prompt_store("prompts/")                 # identity.md written for speech
cfg = audio_config(
    "Voice Support Agent",
    engine_mode="ASR_LLM_TTS",
    identity_prompt=P.require("identity"),
    first_message="Hi, how can I help you today?",
    voice="alloy", chat_mode="INTERRUPT", interruptible=True,
    source_lang="auto",                            # or "en" / "zh" …
    max_call_sec=600, cold_start_silence_sec=10,
    welcome_message={"en": "Hi, how can I help?"},
)
save(cfg, "voice-support.bot")                     # writes the file and runs the validator
```

Run the builder with no arguments for full usage, or `--demo <dir>` for a validated example.

## 7. Quality check (mandatory)

```
python3 ../scripts/validate_gptbots_config.py <name>.bot
```
Exit code 0 before delivery.

## 8. Delivery

Return the `.bot` path, then tell the user: developer space → **Create Agent → Import**; or `scripts/publish_gptbots.py` for a test-mode target. Call out explicitly which **model slots they must select after import** for the engine mode you chose (§2), plus any welcome media they need to upload — those are the two things that make an imported Audio Agent fail to start a session.

## References
- Shared Agent fields: `./create-gptbots-agent.md`
- Variables usable in the identity prompt: `./variables-reference.md`
- Public API playbooks: `./call-gptbots-api.md`
