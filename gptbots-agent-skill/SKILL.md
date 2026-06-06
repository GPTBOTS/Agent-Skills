---
name: gptbots-agent-skill
description: Create, read, update, and optimize GPTBots (https://www.gptbots.ai) Agent and Workflow configurations (.bot / .flow files), and drive published Agents/Workflows via the GPTBots Open API. Use this skill whenever the user mentions GPTBots, provides or references a .bot or .flow file, wants to build/optimize a chatbot Agent, FlowAgent, or Workflow for the GPTBots platform, or wants API-based evaluation, quality assessment, RAG testing, scheduled triggering, or knowledge-base/data management — even if they just say "optimize my bot config" with an attached .bot/.flow file.
license: MIT
metadata:
  version: 1.3.2
  generatedBy: gptbots-agent-skill
---

# GPTBots Skill

A platform-level skill for working with **GPTBots** (https://www.gptbots.ai) Agents and Workflows.

Use this skill to:
- **Read / update / optimize** an Agent or Workflow config from a **user-provided `.bot` or `.flow` file**.
- **Create a new** Agent or Workflow from scratch (scenario + requirements → importable `.bot` / `.flow`).
- **Drive** a published Agent/Workflow via the public Open API for evaluation, quality assessment, RAG testing, scheduled triggering, and data/knowledge-base management.

## Package layout

```
SKILL.md                      # this guide
references/                   # how-to specs (read the one matching the task)
  create-gptbots-agent.md         # QuestionAnswer / MultiAgent → .bot
  create-gptbots-flowagent.md     # FlowAgent (botType=Flow) → .bot
  create-gptbots-workflow.md      # Workflow → .flow
  call-gptbots-api.md             # drive an Agent/Workflow via the public API
  variables-reference.md / materials-mapping.md / workflow-nodes.md / flowagent-components.md
scripts/
  validate_gptbots_config.py  # offline .bot/.flow quality check (mandatory self-check)
```

## Where the target config comes from

This skill does not bundle any config. The target `.bot` / `.flow` is **provided by the user** (an attachment, a file path, or pasted JSON — exported from the GPTBots platform via Export). That file is the authoritative starting point for any optimization task. If the user wants to optimize an existing Agent/Workflow but has not provided the file, ask them to export it from the platform first (developer space → the Agent/Workflow → Export). For brand-new creation, no file is needed — start from the user's scenario and requirements.

## Workflow

### A. Optimize / update a user-provided Agent or Workflow
1. Read the user's `.bot` (or `.flow`) file to understand the current design. Identify its type from `botType` (`QuestionAnswer`/`MultiAgent`/`Flow`/`Workflow`) and read the matching `references/create-gptbots-*.md`.
2. Clarify what the user wants to change and gather their materials (FAQ/docs, data, examples). Do not invent requirements.
3. Edit **only** the documented fields needed (see the matching `references/create-gptbots-*.md`). Keep model ids / plugin auth / cross-org references blank (the backend backfills or clears them on import).
4. For a **Workflow / FlowAgent**, generate an `overview.md` next to the output file containing a `## Flow (mermaid)` diagram of the new design, so the design intent stays reviewable.
5. Run the quality check, then deliver (sections below).

### B. Create a new Agent or Workflow
Follow the reference matching the target type, then quality-check and deliver:
- QuestionAnswer / MultiAgent → `references/create-gptbots-agent.md`
- FlowAgent (`botType=Flow`) → `references/create-gptbots-flowagent.md`
- Workflow → `references/create-gptbots-workflow.md`

### C. Drive a published Agent/Workflow via the API
For evaluation / quality assessment / RAG testing / scheduled triggering / data & knowledge-base management, follow `references/call-gptbots-api.md` (public Open API only).

## Prompt quality for LLM-capable nodes (critical)

Several nodes carry an LLM prompt: the top-level identity `prompt` of a QuestionAnswer/MultiAgent agent, FlowAgent `LLM` components, the Classifier (`Branch`) — **which is LLM-driven: every category rule is a prompt the LLM executes to route each message** — and `Condition` components (also LLM-judged), `ChatGather` (LLM-driven collection: its prompt's field definitions + SOP drive both asking and extraction, and it monopolizes the conversation while collecting — see the FlowAgent reference), and Workflow `LLM` / `INTENT` nodes. These prompts — the identity (system) prompt above all — determine the Agent's runtime quality and efficiency more than any other field, so invest more effort here than anywhere else in the config:

- **Clear, concise, executable.** State the role/identity, goal, boundaries, and expected output format in short imperative sentences. Every sentence should change model behavior; cut filler and vague adjectives — verbose prompts cost tokens on every turn and dilute the instructions that matter.
- **One node, one job.** Scope each prompt to that node's single responsibility; don't restate global rules in every node — put shared identity/boundaries once in the identity prompt.
- **Classifier branch rules are prompts too.** Each `Branch` category rule and `INTENT` intent description deserves the same care as a system prompt: the rules must be **mutually exclusive and unambiguous**, written as concrete descriptions of what belongs in that category (add examples for easily-confused intents), with everything else falling to the `Other`/fallback branch. Routing accuracy — and therefore the whole flow's quality — is capped by the weakest branch rule.
- **No conflicts.** Before delivery, re-read all prompts in the config **as a set** (identity prompt + every LLM/classifier/condition prompt) and resolve any contradiction in goals, tone, boundaries, or output format. Conflicting prompts make the model behave inconsistently at runtime, which no amount of flow design can fix.

## Quality check (mandatory — never deliver a config that fails)
After producing or editing any `.bot`/`.flow`, run:
```
python3 scripts/validate_gptbots_config.py <path/to/output>.bot
```
On a non-zero exit code, fix the JSON per the reported `path`/`fix`, rerun, and only deliver once it passes (exit code 0).

## Delivery
1. Place the new/updated `.bot` / `.flow` file (and `overview.md` with its mermaid diagram, for Workflow/FlowAgent) in the current working directory, and return their local paths. Never overwrite the user's original file unless they explicitly ask — deliver an updated copy alongside it.
2. Tell the user: on **www.gptbots.ai** (developer space), **Create Agent / Workflow → Import**, then select the file.

## API
- Docs (authoritative): https://www.gptbots.ai/docs/api-reference/overview
- Base URL by region: `https://api-${endpoint}.gptbots.ai/` — `sg`=Singapore (default), `jp`=Japan, `th`=Thailand.
- Auth: `Authorization: Bearer <YOUR_API_KEY>` — never write a real key into any file. You must ask the user for the target Agent/Workflow's API key before making an API call.
- Playbooks: `references/call-gptbots-api.md`.
