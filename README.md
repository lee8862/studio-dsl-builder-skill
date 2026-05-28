# Studio DSL Builder Skill

用于在 Codex 或 Claude Code 中生成、修复、校验 KURO AI Studio / Dify-compatible 的可导入 DSL YAML。

这个 skill 的目标不是只给架构建议，而是尽量产出一个能直接导入的 `.yml` 文件，并在输出前用内置校验脚本做结构检查。

## 适用场景

- 根据自然语言需求创建 `workflow`、`advanced-chat/chatflow`、`agent-chat` 应用 DSL。
- 把业务流程、审批规则、文案审查、RAG 问答等需求转成可导入 YAML。
- 修复已有 DSL 的导入失败、节点连接错误、变量引用错误、终止节点类型错误。
- 校验生成的 DSL 是否至少满足基础结构、节点边、变量选择器、模式终止节点等规则。

## 仓库结构

```text
studio-dsl-builder-skill/
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
|-- references/
|   |-- patterns.md
|   |-- schema-rules.md
|   `-- source-docs.md
`-- scripts/
    `-- validate_studio_dsl.py
```

## 在 Codex 中安装

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
git clone https://github.com/lee8862/studio-dsl-builder-skill.git "$env:USERPROFILE\.codex\skills\studio-dsl-builder"
```

### macOS / Linux / WSL

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/lee8862/studio-dsl-builder-skill.git ~/.codex/skills/studio-dsl-builder
```

安装后重启 Codex，或开启一个新的 Codex 会话。之后可以显式调用：

```text
使用 $studio-dsl-builder 创建一个 workflow 模式应用，名称叫「营销文案合规审查器」
输入字段：
- product_name，类型 text，必填，产品名称
- target_audience，类型 text，必填，目标人群
- copy_text，类型 paragraph，必填，营销文案
- channel，类型 select，必填，可选项：小红书、抖音、微信公众号、短信
输出可导入 yml。
```

也可以直接描述需求。只要任务明显是在创建、修复或校验 Studio DSL，Codex 会根据 skill 描述自动加载。

## 在 Claude Code 中安装

Claude Code 的 skill 是文件系统中的 `SKILL.md` 目录结构。可以安装到用户级，也可以安装到单个项目中。

### 用户级安装

适合所有项目都能使用：

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/lee8862/studio-dsl-builder-skill.git ~/.claude/skills/studio-dsl-builder
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
git clone https://github.com/lee8862/studio-dsl-builder-skill.git "$env:USERPROFILE\.claude\skills\studio-dsl-builder"
```

### 项目级安装

适合只在当前仓库中启用：

```bash
mkdir -p .claude/skills
git clone https://github.com/lee8862/studio-dsl-builder-skill.git .claude/skills/studio-dsl-builder
```

安装后重新打开 Claude Code 会话。可以这样调用：

```text
Use the studio-dsl-builder skill. Create a workflow app named 「企业采购申请智能审批预审」 and output an import-ready yml.
```

如果你的 Claude Code 版本支持 skill 目录生成 slash command，也可以尝试：

```text
/studio-dsl-builder 创建一个 workflow 模式应用，名称叫「营销文案合规审查器」，输出可导入 yml。
```

## 使用建议

对于规则复杂的审批、合规、财务、法务、HR、供应商管理等流程，最好一次性补齐这些信息：

- 输入字段、字段类型、是否必填、枚举项。
- 审查或审批规则，例如阈值、风险等级、驳回条件、必需附件、审批矩阵。
- 是否需要接入外部系统，例如预算系统、供应商库、飞书审批、知识库、黑名单。
- 期望输出字段，例如 `status`、`risk_level`、`reason`、`optimized_copy`。
- 应用模式：`workflow`、`advanced-chat/chatflow`、`agent-chat`。

如果信息不足，skill 会优先反问最多两个关键问题。你也可以明确说“使用默认值直接生成”，它会生成一个带占位提醒的可导入骨架。

## 校验生成的 YAML

生成或修改 DSL 后，可以运行：

```bash
python scripts/validate_studio_dsl.py path/to/app.yml
```

如果你是在其他目录生成文件，也可以使用 skill 目录里的脚本：

```bash
python ~/.codex/skills/studio-dsl-builder/scripts/validate_studio_dsl.py path/to/app.yml
```

校验脚本会检查基础结构、节点边、变量选择器、终止节点类型、常见节点配置错误等问题。通过校验不代表业务规则已经完整，只代表 DSL 结构更接近可导入状态。

## 更新

Codex：

```bash
git -C ~/.codex/skills/studio-dsl-builder pull
```

Claude Code：

```bash
git -C ~/.claude/skills/studio-dsl-builder pull
```

Windows PowerShell 示例：

```powershell
git -C "$env:USERPROFILE\.codex\skills\studio-dsl-builder" pull
git -C "$env:USERPROFILE\.claude\skills\studio-dsl-builder" pull
```

## 安全提醒

- 不要把真实 API Key、Cookie、用户 Token、内部 Console Header 写进需求或提交到仓库。
- 需要外部系统鉴权时，优先使用环境变量占位，例如 `{{#env.crm_token#}}`。
- 发布到公开仓库前，检查 `references/source-docs.md` 和示例 DSL 中是否包含内部路径、内部接口、真实数据集 ID 或模型供应商凭证。

## 参考

- Claude Code Skills 官方文档：https://docs.claude.com/en/docs/claude-code/skills
- Claude Code slash commands 与 skill 目录说明：https://code.claude.com/docs/en/slash-commands
