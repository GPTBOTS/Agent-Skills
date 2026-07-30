#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Agent `.bot` builder (botType=Audio) - a voice / telephony agent.

An Audio Agent is a QuestionAnswer-shaped bot plus one extra block: `multiModal`,
which carries the voice engine mode, VAD, output, call control, welcome media and
the voice-specific identity prompt. There is no rule graph.

Two things decide everything else:
  1. `engineMode` - REALTIME | ASR_LLM_TTS | LLM_TTS. It determines which model
     slots the operator must fill after import (see references/create-gptbots-audioagent.md).
  2. `multiModal.identityPrompt` - the prompt the voice session actually runs.
     The top-level `prompt` field is NOT what the audio pipeline reads. Write it
     for speech: short sentences, no markdown/bullets/URLs, explicit handling of
     silence and interruptions.

Model ids are left blank on purpose: the import backfills environment defaults
and rewrites ids the target environment does not know, so inventing one produces
a bot that fails on its first call.

Server-enforced ranges reproduced here (AudioConfigValidator):
  vad.pauseThresholdMs [0,5000] | vad.interruptSensitivity [0,1]
  vad.minVolume [0,1] | vad.activationThreshold [0,1]
  vad.recognitionMode in semantic|server|preset | vad.responseSpeed in low|medium|high
  output.bufferMs [0,1500] | output.bgSound.volume [1,50]
  callControl.coldStart.silenceThresholdSec [5,60]
  callControl.hangup.maxCallSec [30,3600] | maxSilenceSec [1,180] | maxSilenceCount [1,100]
  multiModalInput.sourceLang.autoDetect must be a BOOLEAN
  maxRespTokens > 0 and <= the chat model's context limit

Example
-------
    from build_gptbots_audioagent import audio_config, save
    from gptbots_prompts import load_prompt_store

    P = load_prompt_store("prompts/")
    cfg = audio_config(
        "Voice Support Agent",
        engine_mode="ASR_LLM_TTS",
        identity_prompt=P.require("identity"),
        first_message="Hi, how can I help you today?",
        voice="alloy", chat_mode="INTERRUPT", interruptible=True,
        source_lang="auto", max_call_sec=600,
        welcome_message={"en": "Hi, how can I help?"},
    )
    save(cfg, "voice-support.bot")
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from gptbots_prompts import load_prompts, load_prompt_store  # noqa: F401
except ImportError:
    load_prompts = load_prompt_store = None

ENGINE_MODES = {"REALTIME", "ASR_LLM_TTS", "LLM_TTS"}
AUDIO_VOICES = {"none", "alloy", "echo", "fable", "onyx", "nova", "shimmer"}
AUDIO_QUALITY = {"DEFAULT", "HD"}                 # BotAudioModeType
AUDIO_OUTPUT_MODES = {"TTS", "LLM", "DISABLED"}   # BotAudioOutputModeEnum
AUDIO_INPUT_MODES = {"ASR", "LLM", "DISABLED"}    # BotAudioModeEnum
CHAT_MODES = {"Q_A", "INTERRUPT"}                 # BotChatModeEnum
FILE_MODES = {"SYSTEM", "LLM", "DISABLED"}        # BotFileModeEnum
IMAGE_MODES = {"auto", "low", "high"}             # BotImageModeType
RECOGNITION_MODES = {"semantic", "server", "preset"}
RESPONSE_SPEEDS = {"low", "medium", "high"}
BG_SOUND_MODES = {"DISABLED", "PRESET", "CUSTOM"}
MULTI_MODAL_DATA_TYPES = {"Text", "Image", "File", "Audio", "Video", "Document"}

DEFAULT_MAX_TOKENS = 1024
DEFAULT_AGENT_LOGO = "/developer/static/images/avatar/default_avatar_202506131619.png"

# Seeded on every new Audio Agent (BotManageService): symbols that must not be
# read aloud, and bracket PAIRS replaced by a single space so the TTS pauses
# instead of pronouncing "left parenthesis".
DEFAULT_SYMBOL_REMOVE = ["≈", "*", "&", "^", "_", "~", "|", "#", "@", "<", ">",
                         "{", "}", "＝", "＋"]
DEFAULT_SYMBOL_REPLACE_PAIRS = ["《》", "【】", "〖〗",
                                "[]", "()", "（）"]


def _one_of(value, allowed, label):
    if value is not None and value not in allowed:
        raise ValueError("%s must be one of %s, got %r" % (label, sorted(allowed), value))
    return value


def _num_in(value, low, high, label, integer=True):
    if value is None:
        return None
    if integer:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("%s must be an integer, got %r" % (label, value))
    else:
        value = float(value)
    if value < low or value > high:
        raise ValueError("%s must be in [%s, %s], got %s" % (label, low, high, value))
    return value


def default_symbol_filter():
    """The TTS text-cleaning rules a freshly created Audio Agent ships with."""
    return {"remove": list(DEFAULT_SYMBOL_REMOVE),
            "replace": [{"from": pair, "to": " "} for pair in DEFAULT_SYMBOL_REPLACE_PAIRS]}


def source_lang_record(lang):
    """UI language pick -> the persisted `sourceLang` record.

    `autoDetect` MUST be a boolean - anything else is rejected server-side.
    Pass None to omit the field entirely.
    """
    if lang is None:
        return None
    if lang == "auto":
        return {"autoDetect": True}
    return {"autoDetect": False, "languages": [lang]}


def audio_multimodal(engine_mode, identity_prompt="",
                     audio_input_mode="ASR", chat_mode="INTERRUPT", text_switch=True,
                     file_mode="DISABLED", image_mode="auto", file_limit=1,
                     file_support_types=None, asr_prompt="", transcribe_quality="standard",
                     source_lang="auto",
                     voice="alloy", audio_quality="DEFAULT", audio_output_mode="TTS",
                     text_language="auto", show_ai_generated_content=False,
                     symbol_filter=None,
                     interruptible=True, pause_threshold_ms=500, interrupt_sensitivity=0.5,
                     recognition_mode="server", response_speed="medium",
                     min_volume=0.5, activation_threshold=0.5,
                     show_control=False, buffer_ms=200, bg_sound=None,
                     cold_start_silence_sec=10, cold_start_prompt="",
                     max_call_sec=600, max_silence_sec=60, max_silence_count=5,
                     hangup_prompt="",
                     speaking_avatar=None, waiting_avatar=None,
                     welcome_audio=None, welcome_message=None):
    """Build the `multiModal` block. All ranges match the server-side validator."""
    _one_of(engine_mode, ENGINE_MODES, "engineMode")
    _one_of(audio_input_mode, AUDIO_INPUT_MODES, "multiModalInput.audioMode")
    _one_of(chat_mode, CHAT_MODES, "multiModalInput.chatMode")
    _one_of(file_mode, FILE_MODES, "multiModalInput.fileMode")
    _one_of(image_mode, IMAGE_MODES, "multiModalInput.imageMode")
    _one_of(voice, AUDIO_VOICES, "multiModalOutput.audioVoice")
    _one_of(audio_quality, AUDIO_QUALITY, "multiModalOutput.audioMode")
    _one_of(audio_output_mode, AUDIO_OUTPUT_MODES, "multiModalOutput.audioModeOutput")
    _one_of(recognition_mode, RECOGNITION_MODES, "vad.recognitionMode")
    _one_of(response_speed, RESPONSE_SPEEDS, "vad.responseSpeed")
    for t in (file_support_types or []):
        _one_of(t, MULTI_MODAL_DATA_TYPES, "multiModalInput.fileSupportTypes[]")

    _num_in(pause_threshold_ms, 0, 5000, "vad.pauseThresholdMs")
    _num_in(interrupt_sensitivity, 0, 1, "vad.interruptSensitivity", integer=False)
    _num_in(min_volume, 0, 1, "vad.minVolume", integer=False)
    _num_in(activation_threshold, 0, 1, "vad.activationThreshold", integer=False)
    _num_in(buffer_ms, 0, 1500, "output.bufferMs")
    _num_in(cold_start_silence_sec, 5, 60, "callControl.coldStart.silenceThresholdSec")
    _num_in(max_call_sec, 30, 3600, "callControl.hangup.maxCallSec")
    _num_in(max_silence_sec, 1, 180, "callControl.hangup.maxSilenceSec")
    _num_in(max_silence_count, 1, 100, "callControl.hangup.maxSilenceCount")

    if bg_sound is not None:
        _one_of(bg_sound.get("mode"), BG_SOUND_MODES, "output.bgSound.mode")
        _num_in(bg_sound.get("volume"), 1, 50, "output.bgSound.volume")

    mm_input = {
        "audioMode": audio_input_mode, "chatMode": chat_mode, "textSwitch": bool(text_switch),
        "fileMode": file_mode, "imageMode": image_mode, "fileLimit": int(file_limit),
        "audioModelVersionId": "",          # ASR model - operator picks it after import
        "asrPrompt": asr_prompt or "",
        "transcribeQuality": transcribe_quality,
    }
    if file_support_types:
        mm_input["fileSupportTypes"] = list(file_support_types)
    lang_record = source_lang_record(source_lang)
    if lang_record is not None:
        mm_input["sourceLang"] = lang_record

    mm_output = {
        "textLanguage": text_language, "audioMode": audio_quality, "audioVoice": voice,
        "audioModelVersionId": "",          # TTS model - operator picks it after import
        "audioModeOutput": audio_output_mode, "textSwitch": bool(text_switch),
        "showAiGeneratedContent": bool(show_ai_generated_content),
        "symbolFilter": default_symbol_filter() if symbol_filter is None else symbol_filter,
    }

    welcome = {}
    for key, value in (("speakingAvatar", speaking_avatar), ("waitingAvatar", waiting_avatar),
                       ("welcomeAudio", welcome_audio), ("welcomeMessage", welcome_message)):
        if value:
            if not isinstance(value, dict):
                raise ValueError("welcome.%s must be a {language: value} map" % key)
            welcome[key] = dict(value)

    block = {
        "engineMode": engine_mode,
        "identityPrompt": identity_prompt or "",
        "multiModalInput": mm_input,
        "multiModalOutput": mm_output,
        "vad": {"pauseThresholdMs": int(pause_threshold_ms),
                "interruptSensitivity": float(interrupt_sensitivity),
                "interruptible": bool(interruptible),
                "recognitionMode": recognition_mode, "responseSpeed": response_speed,
                "minVolume": float(min_volume),
                "activationThreshold": float(activation_threshold)},
        "output": {"showControl": bool(show_control), "bufferMs": int(buffer_ms),
                   "bgSound": bg_sound or {"mode": "DISABLED", "presetId": None,
                                           "uploadUrl": None, "volume": 20}},
        "callControl": {
            "coldStart": {"silenceThresholdSec": int(cold_start_silence_sec),
                          "promptText": cold_start_prompt or ""},
            "hangup": {"maxCallSec": int(max_call_sec),
                       "maxSilenceSec": int(max_silence_sec),
                       "maxSilenceCount": int(max_silence_count),
                       "hangupPromptText": hangup_prompt or ""}},
    }
    if welcome:
        block["welcome"] = welcome
    return block


def audio_config(name, engine_mode="REALTIME", identity_prompt="",
                 first_message=None, preset_questions=None,
                 creativity=0.3, max_tokens=DEFAULT_MAX_TOKENS,
                 description="", logo=DEFAULT_AGENT_LOGO,
                 human_config=None, multi_modal=None, **kwargs):
    """Build an Audio Agent .bot dict.

    Voice keyword arguments are forwarded to audio_multimodal(); pass a prebuilt
    `multi_modal=` to bypass it. Any other documented top-level field
    (dataEnable + knowledge tuning, toolsEnable, workflowEnable +
    associatedWorkflows, memory settings, reasoningEffort, plugins,
    userProperties, ...) can be passed through **kwargs.
    """
    if creativity is not None and not (0 <= creativity < 0.95):
        raise ValueError("creativityLevel must be in [0, 0.95) or None")
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("maxRespTokens must be a positive integer (and must not exceed "
                         "the chat model's context limit)")
    if not (identity_prompt and identity_prompt.strip()):
        raise ValueError("identityPrompt is the field the voice session actually runs - "
                         "it must be non-empty (the top-level `prompt` is not read)")

    voice_keys = set(audio_multimodal.__code__.co_varnames[
        :audio_multimodal.__code__.co_argcount])
    voice_kw = {k: kwargs.pop(k) for k in list(kwargs) if k in voice_keys}
    if multi_modal is None:
        multi_modal = audio_multimodal(engine_mode, identity_prompt=identity_prompt, **voice_kw)
    elif voice_kw:
        raise ValueError("pass either multi_modal= or the voice keyword arguments, not both")

    cfg = {
        "formatVersion": "1.0", "exportType": "BOT",
        "exportTime": int(datetime.now(timezone.utc).timestamp() * 1000),
        "name": name, "botType": "Audio", "logo": logo,
        # Kept in sync with identityPrompt so a human reading the file sees the
        # same text; the audio pipeline reads multiModal.identityPrompt.
        "prompt": identity_prompt,
        "chatModelVersionId": "",       # backend backfills; never invent one
        "creativityLevel": creativity, "maxRespTokens": int(max_tokens),
        "multiModal": multi_modal,
        "multiResponseTypes": ["Text"],
    }
    if first_message is not None:
        cfg["firstMessage"] = first_message           # NOT welcomeMessage
    if preset_questions:
        cfg["presetQuestions"] = list(preset_questions)   # NOT guidingQuestions
    if description:
        cfg["description"] = description
    if human_config:
        cfg["humanConfig"] = human_config
    cfg.update(kwargs)
    return cfg


def save(cfg, path, validate=True):
    """Write JSON; then run validate_gptbots_config.py (same dir) if present."""
    p = Path(path)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote %s" % p)
    validator = Path(__file__).resolve().parent / "validate_gptbots_config.py"
    if validate and validator.exists():
        return subprocess.run([sys.executable, str(validator), str(p)]).returncode
    return 0


def _demo(outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = audio_config(
        "Demo Voice Agent",
        engine_mode="ASR_LLM_TTS",
        identity_prompt=(
            "You are a phone support agent for a demo delivery service. "
            "Speak in short sentences. Confirm what you heard before acting. "
            "Read order numbers digit by digit. "
            "If the caller is silent, ask once whether they are still there, then wait. "
            "If you cannot help, offer to transfer to a human."),
        first_message="Hi, this is demo support. How can I help?",
        voice="alloy", chat_mode="INTERRUPT", interruptible=True,
        source_lang="auto", max_call_sec=600, cold_start_silence_sec=10,
        welcome_message={"en": "Hi, this is demo support. How can I help?"},
    )
    return save(cfg, out / "demo-audioagent.bot")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--demo":
        sys.exit(_demo(sys.argv[2]))
    print(__doc__)
