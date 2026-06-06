# GPTBots Agent Skill —— 校验 / 发布 / 打包 工具 设计文档（v2）

- 日期：2026-06-06
- 远程仓库：`git@github.com:GPTBOTS/Agent-Skills.git`（org `GPTBOTS`，repo `Agent-Skills`）
- 规范文件来源：`bot-flow-generation-spec.md`（待整合后删除）
- 状态：待用户评审

## 1. 背景与目标

`GPTBots-Skill/` 下有唯一一个 GPTBots Agent Skill（源目录，详见 §3 命名）。目标：建一个**针对这一个
skill 的生命周期工具**，支持 **校验（validate）/ 发布（publish）/ 打包（package）**，并把 skill 整理成
可经 `npx skills add` 分发、skills.sh 自动收录的 GitHub 仓库；同时能产出 Anthropic 自家渠道的 `.skill` /
zip。

### 已核实的关键事实（反编译 `skills@1.5.10` + 官方文档）

- `npx skills add` = **Vercel Labs 的 `skills` CLI**（skills.sh 是配套市场）。它跨工具安装：自动检测 71 种
  agent 工具（Claude Code → `~/.claude/skills`，Codex/Cursor/Copilot → `.agents/skills` 等），从 GitHub
  把 skill 装进各工具目录。**发布 = push 到 GitHub**；skills.sh 靠安装遥测自动收录排名，无需提交/清单。
- **安装时整包递归拷贝**被选中的 skill 文件夹（`copyDirectory`，[cli.mjs:1785]），仅排除 `.git/`、
  `__pycache__/`、`__pypackages__/`、`metadata.json`；**`.DS_Store` 等不在排除内、会装到用户机**。
  → 推论：(a) 工具代码必须放在 skill 文件夹**之外**；(b) skill 目录要干净（校验器需 lint 垃圾文件）。
- **skill 的名字取自 frontmatter `name`，不是文件夹名**（`parseSkillMd` 要求 frontmatter 有
  `name`/`description`；安装目录 = `sanitizeName(name)`）。文件夹名与 `name` 不一致是允许的（Modellix 即如此），
  但本设计选择让二者一致（见 §3）。
- **`.skill` 文件 = 整个 skill 目录打成的 zip、后缀改 `.skill`。** 这是 **Anthropic 自家产品（Claude 应用 /
  Cowork）的一键安装分发格式**（分享时显示"保存技能"按钮）。其他工具不认该后缀——解压后把目录放进各工具
  skills 路径即可。
- **Anthropic Skills API**：`POST /v1/skills`，zip 内 SKILL.md 在**顶层**，总大小 `<30MB`，`name ≤64`、
  `description ≤1024`。（注意：与 `.skill`/claude.ai 的"嵌套目录"布局不同。）

### 三类分发渠道 → 三种处理

| 渠道 | 形态 | 工具动作 |
|---|---|---|
| `npx skills add` / skills.sh（Claude Code、Codex、Cursor、Copilot…71 种） | GitHub 仓库目录 | `publish`（push，不打包） |
| Claude 应用 / Cowork 一键"保存技能"、claude.ai 网页端上传 | `.skill`（嵌套目录 zip 换后缀） | `package` |
| Anthropic Skills API | `*.api.zip`（SKILL.md 顶层 zip） | `package` |

## 2. 范围

### In scope
1. 命名统一与目录整理（§3）。
2. 内容修订：整合 `bot-flow-generation-spec.md` 有效部分，删除该独立文件（§6）。
3. Python CLI `skillpack`，三子命令 `validate` / `publish` / `package`（§5）。
4. 仓库脚手架：根 `README.md`（含安装命令）、`LICENSE`、`pyproject.toml`、`skillpack.toml`、首次提交。

### Out of scope
- 斜杠 `/` 命令、插件、命令模板（已与用户确认去掉）。
- 多 skill 支持（确认只有一个 skill）。
- 自动创建 GitHub 远程仓库；`publish` 的实际 `push` 需用户确认后执行（§5）。

## 3. 命名（终稿）

三处统一为 **`gptbots-agent-skill`**：
- frontmatter `name`：`gptbots-skill` → **`gptbots-agent-skill`**（用户已同意改）。
- 源/发布文件夹：`GPTBots-Agent-Skill` → **`gptbots-agent-skill`**（小写连字符，符合 skills.sh/社区惯例，
  URL 干净；= frontmatter name；= 安装后本地目录名；= skills.sh 收录名）。
- 仓库 `GPTBOTS/Agent-Skills` 内只此一个 skill，位于子文件夹 `gptbots-agent-skill/`。
- 安装命令：
  - `npx skills add https://github.com/GPTBOTS/Agent-Skills/tree/main/gptbots-agent-skill`
  - 或 `npx skills add GPTBOTS/Agent-Skills --skill gptbots-agent-skill`

> 同时需把 `SKILL.md` 正文里出现的 `name` 用法（如 `resources/<name>.bot`）保持一致即可，无需改逻辑。

## 4. 仓库结构（终稿）

```
Agent-Skills/                          # git 仓库（GPTBOTS/Agent-Skills）；本地目录名可不同
├── gptbots-agent-skill/               # ★ 被发布/打包的 skill（folder == frontmatter name）
│   ├── SKILL.md                       # name: gptbots-agent-skill
│   ├── README.md
│   ├── references/
│   │   ├── create-gptbots-agent.md
│   │   ├── create-gptbots-flowagent.md     # ← 加一行指引指向整合后的规则
│   │   ├── create-gptbots-workflow.md
│   │   ├── call-gptbots-api.md
│   │   ├── flowagent-components.md          # ← 整合 spec §4/§5/branchId
│   │   ├── variables-reference.md
│   │   ├── materials-mapping.md
│   │   └── workflow-nodes.md
│   └── scripts/validate_gptbots_config.py
├── skillpack/                         # CLI 工具（开发用，安装时不会带给用户）
│   ├── __init__.py
│   ├── cli.py                         # argparse：validate / publish / package
│   ├── source.py                      # 载入 skill 目录、解析 frontmatter → SkillSource
│   ├── validator.py                   # 全部检查 → Problem[]
│   ├── limits.py                      # 阈值检查
│   ├── archive.py                     # 确定性 zip 写入（排序、固定时间戳）
│   ├── packager.py                    # 生成 .skill（嵌套）与 .api.zip（顶层）
│   ├── publisher.py                   # git add/commit/push（push 前确认）
│   └── config.py                      # 默认值 + skillpack.toml 加载
├── tests/                             # 单元 + 集成 + fixtures
├── dist/                              # package 输出（.gitignore）
├── skillpack.toml                     # 配置：skill 路径、阈值、远程
├── pyproject.toml                     # 入口 `skillpack`，依赖 PyYAML
├── README.md                          # 仓库说明：安装命令 + 工具用法 + 各渠道
├── LICENSE                            # MIT（建议）
└── .gitignore
```

`skills` CLI **整包拷贝** `gptbots-agent-skill/`，所以 `skillpack/`、`tests/`、`dist/` 等放在它之外，
安装时不会外泄给用户。

## 5. CLI 设计（`skillpack`）

通用：默认操作对象 = 配置里的 skill 路径（`skillpack.toml` 的 `skill_path = "gptbots-agent-skill"`），
也可显式传 `<path>`。所有子命令先跑校验；问题一次性汇总，`ERROR:`/`WARN:` 前缀；有错误（或 `--strict`
下有警告）退出码 1。

### 5.1 `skillpack validate [path] [--strict] [--config FILE]`
仅做发布前 lint。

**错误（阻断）**
| code | 规则 |
|---|---|
| E001 | 路径存在且是目录 |
| E002 | 目录根有 `SKILL.md` |
| E003 | frontmatter 是 `---` 包裹的合法 YAML |
| E004 | `name` 必填、字符串、匹配 `^[a-z0-9]+(-[a-z0-9]+)*$`、长度 ≤ `max_name_length`(64) |
| E005 | `description` 必填、非空、长度 ≤ `max_description_length`(1024) |
| E006 | 禁止符号链接（安全） |
| E007 | 总大小 ≤ `max_total_size`(30MB) |

**警告（不阻断；`--strict` 升级为错误）**
| code | 规则 |
|---|---|
| W001 | 文件夹名 ≠ frontmatter `name`（仅整洁度；CLI 不强制，安装名取自 `name`） |
| W002 | 缺 frontmatter `license` |
| W003 | `SKILL.md` 正文为空 |
| W004 | 含会被一并安装的垃圾文件（`.DS_Store`、编辑器临时文件等）。注：`skills` CLI 仅自动排除 `.git/`/`__pycache__/`/`__pypackages__/`/`metadata.json`，`.DS_Store` 等会装到用户机 |
| W005 | 单文件 > `max_file_size` 或文件数 > `max_file_count` 或 `SKILL.md` 字节 > `max_skill_md_bytes` |

### 5.2 `skillpack package [path] [--out dist] [--config FILE]`
先 `validate`（有错误即止），再按配置产出（默认两者都生成；用 `[package]` 段开关）：
- `dist/gptbots-agent-skill.skill` —— **嵌套布局**（zip 内含 `gptbots-agent-skill/SKILL.md …`），后缀 `.skill`。
  用于 Claude 应用 / Cowork 一键"保存技能"，以及 claude.ai 网页端上传（必要时改后缀为 `.zip`）。
- `dist/gptbots-agent-skill.api.zip` —— **顶层布局**（zip 内 `SKILL.md …` 在根），用于 Anthropic Skills API。

打包要点：确定性（条目排序 + 固定时间戳，输出可复现）；排除垃圾（`.git/`、`.DS_Store`、`__pycache__/`、
`*.pyc`、`metadata.json`）；产物 < 30MB（超限报错）。

### 5.3 `skillpack publish [path] [--message MSG] [--yes] [--config FILE]`
先 `validate`（有错误即止），再：
1. `git add` skill 目录（及相关改动）。
2. `git commit`（`--message` 指定，缺省用模板）。
3. **展示将要 push 的内容并要求确认**（交互），或 `--yes` 跳过确认，然后 `git push origin <branch>`。

> push 是对外操作：默认必须确认；无远程/无网时给出清晰报错。实现阶段由用户显式授权后才真正 push。

### 5.4 配置（`skillpack.toml`）
```toml
[skill]
path = "gptbots-agent-skill"     # 默认操作对象

[git]
remote = "origin"
branch = "main"

[limits]
max_total_size_mb      = 30
max_file_count         = 1000
max_file_size_mb       = 10
max_skill_md_bytes     = 65536
max_name_length        = 64
max_description_length = 1024

[package]
emit_skill   = true              # .skill（嵌套）
emit_api_zip = true              # .api.zip（顶层）

[exclude]
patterns = [".git/", ".DS_Store", "__pycache__/", "*.pyc", "metadata.json"]
```

### 5.5 模块职责
- `source.py`：读目录 → `SkillSource(name, description, frontmatter, body, files[], folder_name)`；解析失败返回结构化错误。
- `validator.py`：纯函数 `validate(source, limits) -> list[Problem]`。
- `limits.py` / `config.py`：阈值与配置加载（`tomllib`）。
- `archive.py`：确定性 zip（被 `packager` 复用）。
- `packager.py`：两种布局产物。
- `publisher.py`：git 操作 + 确认。
- `cli.py`：argparse、聚合输出、退出码。

### 5.6 依赖
PyYAML；标准库 `tomllib`/`zipfile`/`pathlib`/`subprocess`(git)；Python 3.11+。`pip install -e .` 暴露 `skillpack`。

## 6. 内容修订（整合 `bot-flow-generation-spec.md`）

整合进 `gptbots-agent-skill/references/flowagent-components.md`（句柄规则已在此）：
1. **§4** 分类器/`Branch` 每类目 `condition`（branch rule）**不可为空**（前端 "Cannot be empty"，后端不补全）；
   `Condition`/`Regular` 判定字段同理。
2. **§5** `Human` 节点需**组件级 `humanConfig`**（不只实体级），否则节点配置表单空白。
3. **§1/§3** `branchId` 为稳定唯一 id（时间戳式），component 配置与 `sourceHandle` 用同一个；勿自造 `branch1`/`product`。

并在 `create-gptbots-flowagent.md` 第 2 步加一行指引。完成后**删除独立 `bot-flow-generation-spec.md`**。

**不采纳**：spec §3 的 FormGather 源句柄 `form-collect_*` —— 与 `validate_gptbots_config.py`
（`formgather_*`，镜像后端，权威）冲突，以现有 `flowagent-components.md`/校验脚本为准。

## 7. 仓库根 `README.md` 要点
- 一句话介绍。
- **安装（主推）**：两种 `npx skills add` URL；说明自动装进 Claude Code/Codex/Cursor 等。
- **Anthropic 渠道**：`.skill` 一键"保存技能"（Claude 应用/Cowork）、claude.ai 网页端上传、Skills API（`.api.zip`）。
- **工具用法**：`pip install -e .`；`skillpack validate` / `package` / `publish`。
- 许可（MIT）。

## 8. 测试（TDD）
- `test_source`：frontmatter 解析（合法/缺 SKILL.md/非法 YAML/无 `---`/缺字段）。
- `test_validator`：每条 E/W 各一 fixture；valid fixture 零问题。
- `test_limits`：阈值边界。
- `test_archive` / `test_packager`：`.skill` 为嵌套布局、`.api.zip` 为顶层布局、确定性（两次构建字节一致）、排除生效、< 30MB。
- `test_publisher`：用临时 git 仓库验证 add/commit；push 用 dry-run 或 mock，确认默认需确认。
- 集成：对真实 `gptbots-agent-skill` 跑 `validate` 应通过；`package` 产物可重新解压并校验。

## 9. 实现阶段交付顺序
1. `.gitignore`（含 `dist/`）。
2. 重命名文件夹 `GPTBots-Agent-Skill` → `gptbots-agent-skill`；改 `SKILL.md` 的 `name`。
3. 内容修订（整合 spec，删除独立 `bot-flow-generation-spec.md`）。
4. TDD 实现 `skillpack`（source → validator → limits → archive → packager → publisher → cli）。
5. 写 `README.md`/`LICENSE`/`pyproject.toml`/`skillpack.toml`。
6. `skillpack validate` 通过；`skillpack package` 产物校验。
7. 首次提交。**`skillpack publish`（push 到 GPTBOTS/Agent-Skills）由用户显式授权后再做。**

## 10. 风险 / 开放问题
- **LICENSE**：默认 MIT（同 Modellix），可改。
- **`.skill` 与 claude.ai 网页端**：二者均为"嵌套目录 zip"，同一份产物；若网页表单只认 `.zip` 后缀，改名即可（已在 README 说明）。
- **工具与 skill 同仓**：安装只带 `gptbots-agent-skill/`，工具不外泄；便于 CI/协作。如需绝对纯净可拆独立 repo（本期同仓）。
- **publish 的 push**：默认需确认；CI/批量场景用 `--yes`。
