# GPTBots Agent Skill

The GPTBots Agent Skill helps you create and optimize GPTBots Agents and Workflows, and drive
published ones via the public API. This repo holds the skill (`gptbots-agent-skill/`) plus
`skillpack`, a small tool to validate, package, and publish it.

## Install the skill

With the [`skills`](https://github.com/vercel-labs/skills) CLI (installs into Claude Code, Codex,
Cursor, Copilot, and other agents automatically):

```bash
npx skills add https://github.com/GPTBOTS/Agent-Skills/tree/main/gptbots-agent-skill
# or
npx skills add GPTBOTS/Agent-Skills --skill gptbots-agent-skill
```

### Anthropic-only channels

- **Claude app / Cowork** — share `gptbots-agent-skill.skill` (built by `skillpack package`); it shows
  a one-click "Save skill" button.
- **claude.ai web** — Settings → Capabilities → Skills → upload the same file (rename `.skill` to `.zip`
  if the form requires it).
- **Anthropic Skills API** — upload `gptbots-agent-skill.api.zip` (SKILL.md at the archive root).

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
