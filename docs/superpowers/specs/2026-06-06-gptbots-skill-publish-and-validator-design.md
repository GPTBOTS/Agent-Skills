# GPTBots Skill 发布化 + 校验器 —— 设计文档

- 日期：2026-06-06
- 远程仓库：`git@github.com:GPTBOTS/Agent-Skills.git`（org `GPTBOTS`，repo `Agent-Skills`）
- 状态：待用户评审

## 1. 背景与目标

`gptbots-skills/` 是一个 GPTBots 的 Agent Skill（`SKILL.md` + `references/` + `scripts/`）。目标是像
Modellix 那样，通过 **`npx skills add <github-url>`** 分发，并在 **skills.sh** 市场自动收录；同时提供一个
**可复用的校验器 CLI**，在发布前检查 skill 是否合规。

### 关键认知（已核实，反编译 `skills@1.5.10` CLI 源码 + 官方文档）

- `npx skills add` 用的是 **Vercel Labs 的 `skills` npm 包**（skills.sh 是配套市场网站，同一项目）。
- 它是**跨工具安装器**：自动检测用户安装的 71 种 agent 工具（Claude Code、Codex、Cursor、Copilot 等），
  从 GitHub 把 skill 装进每个工具各自的 skills 目录（Claude Code → `~/.claude/skills`、Codex/Cursor/Copilot → `.agents/skills` 等）。
- **发布 = push 到 GitHub。** 不需要 npm publish、不需要提交 PR、不需要清单文件。skills.sh 靠安装遥测自动收录并排名。
- 因此**完全不需要 zip / `.skill` / 任何打包步骤** —— 一个结构正确的公开 GitHub 仓库即可。
- 安装支持多种 URL 形式：子文件夹 `.../tree/main/<folder>`、`<owner>/<repo> --skill <name>`、`<owner>/<repo>` 简写。
- 一个仓库可托管多个 skill（每个 skill 一个文件夹）。

### `skills` CLI 覆盖不到的两个渠道（本期不做，留作扩展）

- **claude.ai 网页端 / 桌面端**：需手动上传 `.zip`（结构 `name/SKILL.md` 嵌套，`<30MB`）。
- **Anthropic Skills API**：`POST /v1/skills`（zip，SKILL.md 在顶层，`<30MB`）。

## 2. 范围

### In scope
1. 把 skill 整理成可发布到 `GPTBOTS/Agent-Skills` 的仓库结构（集合仓库，skill 作根级子文件夹）。
2. 修复 folder / frontmatter `name` 不一致。
3. 内容修订：把 `bot-flow-generation-spec.md` 的有效部分整合进 skill 的参考文档。
4. 一个可复用的 Python 校验器 CLI（`skillpack validate`）。
5. 仓库脚手架：根 `README.md`（含 `npx skills add` 安装命令）、`LICENSE`、`.gitignore`、首次提交。

### Out of scope（明确不做）
- zip 构建（claude.ai 网页端 / Anthropic API）—— 以后需要再加一个 `build` 子命令。
- 斜杠 `/` 命令、插件、命令模板（已与用户确认去掉）。
- 自动 `git push` / 自动创建远程仓库内容 —— 需用户显式授权后再推。

## 3. 命名决策

- skill `name` 保持 `gptbots-skill`（改动最小）。
- 文件夹 `gptbots-skills`（复数）→ **`gptbots-skill`**（与 `name` 一致，满足 `skills` CLI 的 name == folder 规则）。
- 仓库为集合仓库 `Agent-Skills`，`gptbots-skill` 是其中第一个 skill；以后新 skill 作同级子文件夹。
- 安装命令：
  - `npx skills add https://github.com/GPTBOTS/Agent-Skills/tree/main/gptbots-skill`
  - 或 `npx skills add GPTBOTS/Agent-Skills --skill gptbots-skill`

## 4. 仓库结构（最终）

```
Agent-Skills/                         # git 仓库（GPTBOTS/Agent-Skills）；本地目录名可不同
├── gptbots-skill/                    # ★ 被发布的 skill（folder == frontmatter name）
│   ├── SKILL.md
│   ├── README.md                     # skill 自身说明（保留在 skill 内）
│   ├── references/
│   │   ├── create-gptbots-agent.md
│   │   ├── create-gptbots-flowagent.md   # ← 加一行指引指向整合后的规则
│   │   ├── create-gptbots-workflow.md
│   │   ├── call-gptbots-api.md
│   │   ├── flowagent-components.md        # ← 整合 spec §4/§5/branchId
│   │   ├── variables-reference.md
│   │   ├── materials-mapping.md
│   │   └── workflow-nodes.md
│   └── scripts/validate_gptbots_config.py
├── skillpack/                        # 校验器 CLI（开发工具，不随 skill 安装给用户）
│   ├── __init__.py
│   ├── cli.py                        # argparse、聚合输出、退出码
│   ├── source.py                     # 载入 skill 文件夹、解析 SKILL.md frontmatter
│   ├── validator.py                  # 全部检查 → Problem[]
│   ├── limits.py                     # 阈值检查
│   └── config.py                     # 默认值 + TOML 加载
├── tests/
│   ├── test_source.py
│   ├── test_validator.py
│   ├── test_limits.py
│   └── fixtures/                     # valid / name-mismatch / missing-md / bad-name /
│                                     #   no-description / symlink / junk / oversized
├── skillpack.toml                    # 校验默认阈值
├── pyproject.toml                    # 入口 `skillpack`，依赖 PyYAML
├── README.md                         # 仓库 README：介绍 + npx skills add + 校验器用法 + 其它渠道说明
├── LICENSE                           # MIT（建议）
└── .gitignore
```

说明：`skills` CLI 只安装 `gptbots-skill/` 子文件夹；`skillpack/`、`tests/`、打包配置等都是开发/CI 工具，
不会进入用户环境。把工具与 skill 放同一仓库便于 CI 校验与协作（可调整）。

## 5. 校验器 CLI 设计（`skillpack`）

### 命令
```
skillpack validate <skill-folder> [--strict] [--config FILE]
```
- `validate` 对单个 skill 文件夹做发布前 lint。
- `--strict`：把警告升级为错误。
- `--config`：覆盖默认阈值（默认读仓库根 `skillpack.toml`，存在则用）。
- 退出码：有错误（或 `--strict` 下有警告）返回 1，否则 0。
- 行为：**一次性收集并汇总所有问题**（非遇错即停），逐条 `ERROR:` / `WARN:` 输出，附 `hint`。

> 未来可加 `validate-all <repo>` 遍历仓库内所有 skill 文件夹；本期 YAGNI 不做。

### 模块职责
- `source.py`：读取文件夹 → `SkillSource(name, description, frontmatter: dict, body: str, files: [relpath], folder_name)`。frontmatter 解析失败时返回结构化错误而非抛栈。
- `validator.py`：纯函数 `validate(source, limits) -> list[Problem]`，`Problem(level, code, message, hint)`。
- `limits.py`：基于 `Limits` 配置做大小/数量/长度检查。
- `config.py`：`Limits` dataclass + 默认值 + `tomllib` 读取覆盖。
- `cli.py`：argparse → 调 source/validator → 渲染输出与退出码。

### 检查项

**错误（阻断发布）**
| code | 规则 |
|---|---|
| E001 | 路径必须存在且是目录 |
| E002 | 文件夹根必须有 `SKILL.md` |
| E003 | frontmatter 必须是 `---` 包裹的合法 YAML |
| E004 | `name` 必填、字符串、匹配 `^[a-z0-9]+(-[a-z0-9]+)*$`、长度 ≤ `max_name_length` |
| E005 | `name` 必须等于文件夹名（`skills` CLI 规则；用于捕获 gptbots-skills/gptbots-skill 这类不一致） |
| E006 | `description` 必填、非空、长度 ≤ `max_description_length` |
| E007 | 禁止符号链接（安全：避免越界打包 / 安装到用户机时跟随链接） |
| E008 | 总大小 ≤ `max_total_size`（默认 30MB，对齐官方上限） |

**警告（不阻断；`--strict` 升级为错误）**
| code | 规则 |
|---|---|
| W001 | 缺少 frontmatter `license`（市场/合规建议） |
| W002 | `SKILL.md` 正文为空（只有 frontmatter） |
| W003 | 含垃圾文件（`.DS_Store` / `.git/` / `__pycache__/` / `*.pyc`）—— `skills` CLI 会原样拷贝整个文件夹，建议清理 |
| W004 | 单文件大小 > `max_file_size` 或文件数 > `max_file_count` |
| W005 | `SKILL.md` 字节数 > `max_skill_md_bytes`（过长影响加载效率） |

### 阈值（`skillpack.toml` 默认值）
```toml
[limits]
max_total_size_mb      = 30      # 对齐 claude.ai / Skills API 上限
max_file_count         = 1000
max_file_size_mb       = 10
max_skill_md_bytes     = 65536
max_name_length        = 64      # 官方 name 上限
max_description_length = 1024    # 官方 description 上限

[exclude]
# 仅用于 W003 提示；校验器不修改文件
patterns = [".git/", ".DS_Store", "__pycache__/", "*.pyc"]
```

### 依赖与运行
- PyYAML（frontmatter）；标准库 `tomllib` / `pathlib`；Python 3.11+。
- `pip install -e .` 暴露 `skillpack` 命令。

## 6. 内容修订（整合 `bot-flow-generation-spec.md`）

把以下**新增且正确**的内容整合进 `gptbots-skill/references/flowagent-components.md`（句柄规则已在此文件）：
1. **§4** —— 分类器 / `Branch` 每个类目的 `condition`（branch rule）**不可为空**（前端报 "Cannot be empty"，后端不补全）；
   `Condition` / `Regular` 等带判定语义的字段同理。
2. **§5** —— `Human` 节点需要**组件级 `humanConfig`**（不只实体级），否则节点配置表单渲染为空白。
3. **§1/§3** —— `branchId` 为**稳定唯一 id**（时间戳式），component 配置与 `sourceHandle` 必须用同一个；
   勿自造 `branch1` / `product` 这类 key。

并在 `create-gptbots-flowagent.md` 第 2 步加一行指引指向上述规则。完成后**删除独立的 `bot-flow-generation-spec.md`**。

**不采纳**：spec §3 的 FormGather 源句柄 `form-collect_*` —— 与校验脚本
`validate_gptbots_config.py`（`formgather_*`，权威，镜像后端）冲突，以校验脚本/现有 `flowagent-components.md` 为准。

## 7. 仓库根 `README.md` 要点

- 一句话介绍：GPTBots 官方 Agent Skills 集合。
- **安装**：两种 `npx skills add` URL 形式；说明会自动装进 Claude Code / Codex / Cursor 等。
- **其它渠道**：claude.ai 网页端（手动 zip 上传，结构 `gptbots-skill/SKILL.md`，`<30MB`）；Anthropic Skills API（指路链接，本期不自动生成 zip）。
- **开发/维护**：`pip install -e . && skillpack validate gptbots-skill`。
- 许可（MIT）。

## 8. 测试（TDD）

- `test_source`：frontmatter 解析（合法 / 缺 `SKILL.md` / 非法 YAML / 无 `---` 分隔符 / 缺字段）。
- `test_validator`：每条 E/W 规则各配一个 fixture，断言产出对应 code；valid fixture 零问题。
- `test_limits`：阈值边界（恰好等于 / 超出）。
- 集成：对修复名字后的真实 `gptbots-skill` 跑 `validate`，应通过（退出码 0）。

## 9. 实现阶段交付顺序

1. `.gitignore`（Python：`__pycache__/`、`*.egg-info/`、`dist/`、`.venv/`、`.DS_Store`）。
2. 重命名 `gptbots-skills/` → `gptbots-skill/`（用 `git mv` 保留历史；当前尚未首次提交，则普通 `mv`）。
3. 内容修订（整合 spec，删除独立 `bot-flow-generation-spec.md`）。
4. TDD 实现 `skillpack`（先测试后实现）。
5. 写 `README.md` / `LICENSE` / `pyproject.toml` / `skillpack.toml`。
6. 跑 `skillpack validate gptbots-skill` 通过。
7. 首次提交。**推送到 `origin`（GPTBOTS/Agent-Skills）由用户显式授权后再做。**

## 10. 风险 / 开放问题

- **LICENSE**：默认建议 MIT（与 Modellix 一致），可改。
- **工具与 skill 同仓**：便于 CI/协作，但混合 Python 与 skill；如需纯净 skill 集合仓库，可把 `skillpack/` 拆到独立 repo（本期同仓）。
- **多 skill 布局**：当前根级子文件夹（Modellix 风格）。若将来 skill 很多，可改 `skills/<name>/` 布局；本期 YAGNI。
- **name == folder 设为硬错误**：因 `skills` CLI 依赖该一致性；如有反例可降级为警告。
