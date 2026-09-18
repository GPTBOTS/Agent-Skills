# 最新 `.bot` 配置支持设计文档

> 版本说明：本设计最初以 Skill `1.4.0` 为交付目标；功能分支 rebase 到新版主分支后，最终集成版本为 `2.1.0`。

**日期**：2026-09-14
**作者**：Codex
**状态**：已在会话中确认

---

## 1. 目标

扩展 `gptbots-agent-skill`，使智能体能够安全地读取、更新和生成包含人工服务提示、多语言服务状态提示、自定义变量/对话属性及用户属性的 `.bot` 配置。

## 2. 本次不做

- 不修改 GPTBots 后端、前端、数据库结构或生产数据。
- 不修改 `.bot` 的 `formatVersion`，后端当前仍导出 `1.0`。
- 不支持从零生成 `LoopAgent.clawRule`，只允许基于已有 LoopAgent 导出文件进行透传式更新。
- 不创建 GitHub Release。本次只把源码推送到功能分支，Release 产物由独立发布流程处理。

## 3. 已确认的后端契约

后端已经支持下列字段的导入和导出：

| 功能 | `.bot` 路径 | 契约 |
|---|---|---|
| 发送服务提示 | `humanConfig.sendHumanTipSwitch` | 可选布尔值。字段缺失时，不同运行路径具有不同默认行为。 |
| 多语言服务状态提示语 | `humanConfig.multiLanguages.<language>[]` | 语言标识到 `{code, text}` 列表的映射。 |
| 自定义变量定义和对话属性默认值 | `customVariables[]` | `.bot` 只导出定义；具体会话值属于运行时数据，不导出。 |
| 用户属性定义 | `userProperties[]` | `.bot` 只导出定义；具体用户值会被明确排除。 |

服务状态提示的标准 code 为 `29`、`30`、`31`、`33`、`34`、`35`、`36`、`37`、`38`、`84`。

`sendHumanTipSwitch` 不能使用统一的隐式默认值：

- Flow Human + LiveDesk 转移失败提示（`code=84`）：字段缺失或为 null 时按开启处理。
- LoopAgent + LiveChat 渠道内转人工提示（`code=36`）：字段缺失或为 null 时按关闭处理。
- 用户没有明确指定开关值时，更新已有配置应保留原字段，新建配置应省略该字段。

## 4. 影响文件

- **新增**：`gptbots-agent-skill/references/bot-config-fields.md`，作为新 `.bot` 字段、示例、默认值和隐私边界的统一参考文档。
- **修改**：`gptbots-agent-skill/SKILL.md`，把相关 `.bot` 任务路由到新参考文档，并将 Skill 版本从 `1.3.2` 升级到 `1.4.0`。
- **修改**：`gptbots-agent-skill/README.md`，记录新参考文档及其后端事实来源。
- **修改**：`gptbots-agent-skill/references/create-gptbots-agent.md`，生成包含人工服务或变量/属性设置的 Agent 时必须读取新参考文档。
- **修改**：`gptbots-agent-skill/references/create-gptbots-flowagent.md`，补充组件级 Human 配置和对话属性赋值语义。
- **修改**：`gptbots-agent-skill/references/flowagent-components.md`，说明 Human 与 Variable 组件行为，不重复整份字段目录。
- **修改**：`gptbots-agent-skill/references/variables-reference.md`，区分定义、默认值、会话级值和用户级值。
- **修改**：`gptbots-agent-skill/references/call-gptbots-api.md`，说明 `conversation_config.custom_variables` 只接收已定义的对话属性，并在当前会话内持久化。
- **重构**：`gptbots-agent-skill/scripts/validate_gptbots_config.py`，保留现有 CLI 入口，把不同校验职责拆到 `scripts/gptbots_config_validator/`。
- **新增**：`gptbots-agent-skill/scripts/gptbots_config_validator/`，包含共享报告/辅助逻辑、Workflow、FlowAgent 和 Bot 字段校验模块，每个文件控制在 250 行有效代码以内。
- **新增**：`tests/test_gptbots_config_validator.py`，通过真实 CLI 子进程验证配置校验行为。
- **按需新增**：`tests/fixtures/` 下的 `.bot` 样例，仅在样例比测试内联数据更容易理解时创建。

## 5. 主流程

```text
用户需求或已有 .bot
  -> SKILL.md 路由到对应的 Agent/FlowAgent 指南
  -> 涉及人工服务或变量/属性时读取 bot-config-fields.md
  -> 智能体保留未知的已有字段，只修改有文档依据的目标字段
  -> validate_gptbots_config.py 解析完整文件
  -> Bot 字段校验器检查 humanConfig/customVariables/userProperties
  -> FlowAgent 校验器额外检查组件级 humanConfig
  -> 所有校验通过后才能交付配置文件
```

更新已有 LoopAgent 文件时，Skill 应保留 `clawRule` 及无关字段，在可行范围内避免无意义的格式改写，只修改用户要求且已有文档定义的字段，并校验共享顶层字段。Skill 不生成新的 `clawRule`。

## 6. 校验规则

### 6.1 人工服务配置

- `sendHumanTipSwitch` 存在时必须是 JSON boolean。
- `multiLanguages` 存在时必须是对象，每个语言对应一个数组。
- 每条提示必须是包含整数 `code` 和字符串 `text` 的对象。
- 同一语言内出现重复 code 时按错误处理。
- 未知整数 code 只告警，不报错，避免阻断后端未来新增的状态提示。
- 顶层 `humanConfig` 和所有 Flow Human 组件内的 `humanConfig` 使用相同规则。
- Flow Human 组件缺少组件级 `humanConfig` 时只告警，因为后端当前会从顶层配置回填。

### 6.2 自定义变量和对话属性

- `customVariables` 存在时必须是对象数组。
- 每个元素必须包含非空 `name` 和有效的后端 `BotCustomVariableType`。
- 后端允许的类型为 `STRING`、`INTEGER`、`NUMBER`、`BOOLEAN`、`DATETIME`、`OBJECT`、`ARRAY_STRING`、`ARRAY_INTEGER`、`ARRAY_NUMBER`、`ARRAY_BOOLEAN`、`ARRAY_OBJECT`、`FILE`、`ARRAY_FILE`。
- 变量名重复时按错误处理。
- Skill 新建配置时默认只生成前端可编辑的 `STRING`、`INTEGER`、`NUMBER`；更新已有导出文件时保留后端支持的其他类型。
- 变量名没有 `var_` 前缀时只告警，不阻断旧配置。
- 参考文档必须明确：`customVariables[]` 保存定义和默认值，运行时对话属性值不属于 `.bot`。

### 6.3 用户属性

- `userProperties` 存在时必须是对象数组。
- Skill 新建的每个元素包含 `name`、`showName`、`type`、`value`、`desc`、`chatUpdate`、`chatQuery`。
- `type` 允许值为 `string`、`number`、`datetime`、`bool`、`list`。
- `chatUpdate` 和 `chatQuery` 存在时必须是布尔值。
- 用户属性重名，或者与 `customVariables` 重名时按错误处理，因为变量替换共用扁平命名空间。
- 禁止生成或填充 `accountId`、嵌套 `userProperties` 等运行时用户数据字段。STG 官方导出会保留值为 `null` 的占位键，编辑官方导出时允许原样保留；发现非空值时按隐私错误处理。
- `chatUpdate=false` 时，LLM 发起的更新会进入失败列表；HTTP 或工具调用成功不代表属性已落库。生成的 Prompt 必须禁止模型直接回复“已保存”，只有目标属性出现在成功列表且未出现在失败列表时才能确认；强一致场景再调用查询接口回读。
- 平台合法导出允许 `creativityLevel=1.0`，校验范围使用闭区间 `[0,1]`，不得沿用旧的 `[0,0.95)` 限制。

所有新增顶层字段均保持可选，保证旧 `.bot` 文件继续通过校验。

## 7. 异常处理

| 异常情况 | 处理方式 | 用户可见结果 |
|---|---|---|
| JSON 类型错误或枚举非法 | 输出包含准确 JSON 路径和修复建议的错误 | 修复前不得交付文件。 |
| 变量或属性名称重复 | 输出校验错误 | 避免变量被静默覆盖。 |
| `.bot` 包含具体用户运行时数据 | 输出隐私错误 | 避免意外导出个人数据。 |
| 服务状态提示 code 未知 | 输出告警 | 提示 schema 漂移，同时保持向前兼容。 |
| 新字段缺失 | 正常通过 | 保持旧 `.bot` 兼容。 |
| 用户要求从零创建 LoopAgent | 要求用户先提供平台导出的 `.bot` | 可以更新已有配置，但不臆造 `clawRule`。 |

## 8. 方案对比

**方案 A（推荐）：统一参考文档 + 确定性校验模块。** 字段事实只维护一份，Agent 与 FlowAgent 文档不易漂移，同时保留现有校验命令。代价是需要顺带拆分已经过大的校验脚本。

**方案 B：在各 Agent 指南中重复字段说明。** 新增文件较少，但相反的开关默认值和共享变量语义很容易出现文档漂移，不采用。

**方案 C：只更新文档。** 实施最快，但格式错误或包含用户隐私数据的 `.bot` 仍会通过强制离线检查，不采用。

## 9. 实施计划

- [ ] 为完整合法配置、错误人工提示结构、非法变量/属性、隐私字段、旧文件兼容和 Flow 组件级配置编写失败的 CLI 测试。
- [ ] 运行聚焦测试，确认失败原因是目标能力尚未实现。
- [ ] 按职责拆分校验器，同时保持 CLI 输出和退出码不变。
- [ ] 实现让失败测试通过所需的最小校验逻辑。
- [ ] 新增 `bot-config-fields.md`，并从所有相关 Skill 文档直接路由到该文件。
- [ ] 为服务提示、对话属性和用户属性新增三组 Skill 评估任务及预期行为标准。
- [ ] 使用更新前 Skill 运行评估并记录现有缺口，再使用更新后 Skill 重跑并记录结果。
- [ ] 将 Skill 版本升级到 `1.4.0`，更新维护说明。
- [ ] 运行聚焦测试、全量测试、Skill 校验、打包和样例 CLI 校验。
- [ ] 审查完整 diff，原子提交，并把 `feat/support-latest-bot-config` 推送到 `origin`。

## 10. 验证方案

- 单元及 CLI 测试：`python -m pytest tests/test_gptbots_config_validator.py -q`。
- 全量测试：`python -m pytest -q`。
- Skill 结构校验：`python -m skillpack.cli validate`。
- 打包：`python -m skillpack.cli package`。
- 手工 CLI 验证：分别校验一个包含全部新字段的合法 `.bot` 和一个故意构造的非法文件。
- 产品验证：在 GPTBots 开发环境导入合法文件，检查保存后的配置，再次导出并比较归一化后的目标字段。该步骤需要已登录的开发环境，不能由离线测试替代。

必须使用 Python 3.11 或更高版本。当前机器默认 `python3` 是 3.9，实施和验证使用 `/Users/lerp/.local/bin/python3.12` 创建项目虚拟环境。

## 11. 系统约束检查

- **版本可用性**：Agent-Skills 声明 Python `>=3.11`；实现只使用该锁定基线支持的语法及标准库能力，不新增运行时依赖。
- **多站点与配置同步**：不新增 MongoDB/MySQL 配置项。发布前确认新加坡、日本、泰国均已部署现有后端字段；旧后端可能静默忽略未知可选字段。
- **性能与全表扫描**：Skill 校验器只在本地对单个有大小限制的配置文件做线性扫描，不访问生产 DB、Redis 或 ES，不引入请求链路 I/O、N+1 或全表扫描。

## 12. 发布与回滚

- 发布：推送功能分支，评审后合并到 `main`；Release 产物继续使用仓库现有发布流程生成。
- 回滚：回退 Skill 提交即可，不涉及产品数据或后端 schema。
- 兼容：全部新字段均为可选；未知服务状态 code 只告警，因此旧 `.bot` 仍可使用。

## 13. 改动影响边界

最坏影响：🔴 校验规则或默认语义写错会让生成的 `.bot` 无法导入，或让转人工提示行为与用户配置相反。

必须一起改：共享字段参考、Agent/FlowAgent 路由文档、变量/API 语义、校验器、CLI 测试、Skill 版本和打包验证。

明确不改：GPTBots 后端与前端、数据库结构、存量数据、运行时提示逻辑、`.bot formatVersion`、GitHub Release。

不改但有风险：各生产区域的后端部署版本尚未运行时核实；合并前需确认新加坡、日本、泰国均已支持这些字段。

迁移/刷数专项：不适用；不改字段名、不迁移结构、不刷草稿或发布数据。
