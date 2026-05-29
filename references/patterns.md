# Studio DSL Generation Patterns

Use these patterns as building blocks for internal KURO AI Studio DSL apps. Keep the final YAML specific to the user's requirement.

## Spec Template

Before generating, hold a compact internal spec:

```json
{
  "app_name": "中文应用名",
  "app_mode": "advanced-chat",
  "goal": "用户要完成什么",
  "inputs": [{"name": "question", "type": "paragraph", "required": true}],
  "outputs": [{"name": "answer", "type": "string"}],
  "processing_steps": [
    "start",
    "knowledge-retrieval",
    "format context",
    "llm answer",
    "answer"
  ],
  "resources": {
    "datasets": ["PLEASE_FILL_DATASET_ID"],
    "apis": [],
    "models": [{"provider": "kurogames/kuro_ai_gateway/kuro_ai_provider", "name": "claude-opus-4.7"}]
  },
  "fallbacks": ["知识库为空时给兜底回复"],
  "warnings": []
}
```

Strip internal fields before passing a spec into a generated workflow.

## Domain Completeness Gate

Use this gate before generating business workflows that make decisions or risk judgments.

Rule-heavy examples:

- procurement approval or pre-check
- reimbursement and finance review
- legal/contract review
- vendor onboarding or blacklist screening
- HR screening or policy enforcement
- security/compliance/audit checks
- customer service routing with SLA or escalation rules

Ask at most two questions, chosen by impact:

1. **Decision policy**
   - "预审/审批规则按什么来? 例如金额阈值、必需材料、供应商准入、预算科目、风险评分规则。"
   - "是否有制度知识库或政策文档要接入? 如果没有,是否允许先用通用规则?"

2. **System integration**
   - "是否要接真实系统? 例如预算系统、供应商库、黑名单、OA/飞书审批接口。"
   - "最终结果只是输出字段,还是要自动发起审批/写回系统?"

Default behavior:

- If the user answers, reflect the rules in nodes, prompts, branches, and End outputs.
- If the user says "直接生成/用默认", generate an internal skeleton and include warnings.
- If the user gave only a name and app mode for a rule-heavy app, ask first. Do not silently produce a skeleton and call it complete.

Generic skeleton label:

```text
This DSL is import-ready as an internal skeleton. It still needs real policy rules/data sources before production use.
```

## Advanced-Chat: Simple LLM Assistant

Use when the app is a chat assistant without explicit batch outputs.

Graph:

```text
start -> llm -> answer
```

LLM prompt:

- system: role, style, safety/fallback, no reasoning output.
- user: `{{#sys.query#}}` or Start variable if declared.

## Advanced-Chat: RAG Q&A

Use for knowledge-base customer service, manuals, FAQ, product docs.

Graph:

```text
start -> knowledge-retrieval -> code(format chunks) -> llm -> answer
```

Rules:

- `query_variable_selector` can use `['sys', 'query']` in advanced-chat.
- Format chunks before the final LLM.
- If dataset ID is unknown, use `PLEASE_FILL_DATASET_ID` and warn.

## Advanced-Chat: Branching Answer

Use for review, moderation, intent split, route-to-human.

Graph:

```text
start -> llm(classify JSON) -> code(parse/normalize) -> if-else
if true -> branch A -> answer A
if false -> branch B -> answer B
```

Rules:

- If using `in`, `value` is an array.
- Every branch must end in `answer`.
- Use canvas-safe graph entries: top-level nodes are `type: custom`, the actual node type is in `data.type`, and every edge has `sourceHandle`, `targetHandle`, `type: custom`, `zIndex`, and edge `data`.
- If-else nodes use `data.cases`; do not use legacy `data.conditions` / `else_id`.
- Use runtime-safe node IDs. Prefer timestamp-like numeric IDs in final YAML, and replace any internal `client_id`/human-readable node names in template variables such as `{{#1700000005.text#}}`.

## Workflow: Batch / API Job

Use when the app has explicit inputs and output fields.

Graph:

```text
start -> code/llm/http/kr -> code(pack outputs) -> end
```

Rules:

- Use Start variables for all inputs.
- No `{{#sys.query#}}`.
- No LLM `memory`.
- End outputs reference the final pack Code node.

## Workflow: Multi-Class Route Compression

Use for categories such as account/recharge/bug/other.

Graph:

```text
start -> llm(classify category) -> code(normalize category + route) -> if-else(route == escalate)
true -> escalation code -> pack/end
false -> llm auto reply -> pack/end
```

Avoid one branch per class unless the user's business process truly differs for every class.

## HTTP + RAG Chat

Use when an app calls an internal API and combines it with KB context.

Graph:

```text
start -> http-request
start -> knowledge-retrieval
http + kr -> code(format context) -> llm -> answer/end
```

Rules:

- Put API host and token in `workflow.environment_variables`.
- Use clean URL strings, for example `{{#env.crm_base_url#}}/orders/{{#start.order_no#}}`.
- For request tokens returned by a previous HTTP node, insert a Code node to parse the token before adding it to an Authorization header. Do not use the whole HTTP response body as a bearer token.
- Warnings carry "fill this later" instructions.

## Agent-Chat Meta-Agent

Use `agent-chat` when the app routes between tools or sub-workflows.

Typical tool set:

- `plan_dsl_spec`: collect and refine spec.
- `generate_dsl_yml`: generate YAML from complete spec.
- `troubleshoot_yml`: diagnose import/runtime errors.
- `export_yml`: optional file export, provider-specific.
- Built-in dataset RAG for docs.

Rules:

- Workflow tools are often stateless; pass `history_summary` and JSON-serialized `spec_so_far`.
- Function-calling strategy value in the documented release is `function_call`.
- Do not keep giant `yml_full` in memory after delivery; keep summary/id only.
- Treat workflow-tool `provider_id` as a publish-time workspace binding, not an app ID. If a sub-workflow is re-imported or re-published, re-check the provider ID and tool configuration before claiming the agent is runnable.
- When repairing an existing agent or workflow-tool setup, patch the latest exported YAML instead of regenerating from a blank graph. The export includes real provider IDs, canvas geometry, and provider metadata that generated skeletons cannot safely infer.
- Keep sub-workflow inputs string-compatible. For object-like values, pass JSON strings and parse them in the child workflow.

## Tool / MCP Integration Pattern

Use when the app reads or writes external systems through Studio tools, MCP, or installed plugins.

Rules:

- Ask for the current workspace's exported tool node or provider binding before generating a fully runnable DSL.
- If the binding is missing, generate an import-ready skeleton with placeholders and explicit warnings.
- For MCP and plugin tool outputs, route downstream parsing through the tool node `json` output. Do not select a non-existent `data` output.
- For installed `.difypkg` tools, preserve exported `provider_type: builtin`, `plugin_id`, `plugin_unique_identifier`, `tool_configurations`, and `tool_parameters`.
- For Feishu/Lark actions, first map the domain with `feishu-mcp-guide.md`, then bind to the current workspace's installed MCP tool.

## Output File Pattern

When creating a DSL file:

1. Generate the YAML.
2. Write it to `<cwd>/studio-dsl-output/<slug>.yml` unless user gives a path.
3. Run `scripts/validate_studio_dsl.py --profile generated <path>` for newly generated DSL; fix structural errors and canvas-shape errors.
   For real Studio exports or hand-patched production YAML, run `scripts/validate_studio_dsl.py <path>` with the default/base profile so canvas decoration drift is reported as warnings instead of false-positive errors.
4. Patch until errors are gone.
5. Final reply:
   - file path
   - one-line graph summary
   - validator result
   - remaining placeholders

## Placeholder Policy

Best effort "ready" means:

- **Fully runnable**: model is set to the internal Studio default or user-provided model, and the user provided datasets, APIs, tool provider IDs, and env values.
- **Import-ready**: imports cleanly, but has placeholders the user must fill.

Do not call a resource-placeholder-heavy DSL fully runnable.

## Internal Studio Defaults

For internal KURO AI Studio generation, fill LLM model config by default:

```yaml
model:
  completion_params: {temperature: 0.3}
  mode: chat
  name: claude-opus-4.7
  provider: kurogames/kuro_ai_gateway/kuro_ai_provider
```

Do not leave model fields blank for internal Studio DSL.
