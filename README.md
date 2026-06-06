# GPTBots Agent Skill

The GPTBots Agent Skill helps you create, read, update, and optimize
[GPTBots](https://www.gptbots.ai) Agent and Workflow configurations (`.bot` / `.flow` files),
and drive published Agents and Workflows via the GPTBots Open API.

## Install the skill

With the [`skills`](https://github.com/vercel-labs/skills) CLI (installs into Claude Code, Codex,
Cursor, Copilot, and other agents automatically):

```bash
npx skills add https://github.com/GPTBOTS/Agent-Skills/tree/main/gptbots-agent-skill
# or
npx skills add GPTBOTS/Agent-Skills --skill gptbots-agent-skill
```

This reads the skill straight from the source folder.

### Anthropic channels

For Claude's own channels, use the packaged build attached to the
[latest release](https://github.com/GPTBOTS/Agent-Skills/releases/latest), or build it locally with
`skillpack package`.

- **Claude app / Cowork** — share
  [`gptbots-agent-skill.skill`](https://github.com/GPTBOTS/Agent-Skills/releases/latest/download/gptbots-agent-skill.skill);
  it shows a one-click "Save skill" button.
- **claude.ai web** — Settings → Capabilities → Skills → upload the same file (rename `.skill` to `.zip`
  if the form requires it).
- **Anthropic Skills API** — upload
  [`gptbots-agent-skill.api.zip`](https://github.com/GPTBOTS/Agent-Skills/releases/latest/download/gptbots-agent-skill.api.zip)
  (SKILL.md at the archive root).

## What's inside

- [`gptbots-agent-skill/SKILL.md`](gptbots-agent-skill/SKILL.md) — the skill entry point
- [`gptbots-agent-skill/references/`](gptbots-agent-skill/references/) — detailed guides for Agents,
  Workflows, FlowAgent components, the Open API, variables, and material mapping
- [`gptbots-agent-skill/scripts/`](gptbots-agent-skill/scripts/) — a config validation helper

## Maintain the skill (skillpack)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

.venv/bin/skillpack validate            # lint the skill before publishing
.venv/bin/skillpack package             # write dist/*.skill and dist/*.api.zip
.venv/bin/skillpack publish             # validate, commit, then push (asks before pushing)
```

`skillpack` defaults to the skill at `gptbots-agent-skill/` (configurable in `skillpack.toml`).

## License

MIT — see [LICENSE](LICENSE).
