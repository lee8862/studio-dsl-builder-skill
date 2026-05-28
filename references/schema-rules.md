# Studio DSL Schema Rules

Use these rules when generating, repairing, or validating Studio DSL YAML for internal KURO AI Studio.

## Top Level

Required shape:

```yaml
app:
  name: ...
  mode: advanced-chat | workflow | agent-chat
dependencies: []
kind: app
version: 0.6.0
workflow:
  graph:
    nodes: []
    edges: []
```

Use `version: 0.6.0`, the documented import version for the current internal KURO release docs, unless the internal release docs are updated.

## Canvas Graph Shape

Generated graphs must be canvas-safe, not just parseable. Internal Studio imports into a ReactFlow-style canvas and expects these fields.

Each node:

- top-level `type: custom`
- `data.type` contains the real node type, such as `start`, `llm`, `code`, `if-else`, `http-request`, `answer`, or `end`
- `position` and `positionAbsolute`
- `sourcePosition: right`, `targetPosition: left`
- top-level `selected: false`, `width`, `height`
- `data.desc` and `data.selected: false`

Each edge:

- `type: custom`
- `sourceHandle` and `targetHandle: target`
- `zIndex: 0`
- `data.isInIteration: false`, `data.isInLoop: false`
- `data.sourceType` and `data.targetType`

The graph should include:

```yaml
viewport: {x: 0, y: 0, zoom: 0.7}
```

Avoid simplified graph entries such as top-level node `type: llm`, edges without handles, or missing `positionAbsolute`; these can import but crash or blank the canvas.

## Node IDs and Template Variables

Node IDs must be safe for Studio's runtime template parser:

- Use `start`, `end`, or timestamp-like numeric IDs such as `1700000005`.
- Do not use human-readable IDs with hyphens, such as `node-search-reply-llm`.
- Any node ID referenced inside `{{#node_id.output#}}` must match `^[a-zA-Z0-9_]{1,50}$`.
- When generating from internal client IDs, keep a `client_id -> runtime_node_id` map and replace all references before output: node `id`, edge `source`/`target`, `value_selector`, `variable_selector`, and every `{{#...#}}` template.

Why this matters: the canvas editor may display `{{#node-search-reply-llm.text#}}` as a variable chip, but the runtime parser does not recognize hyphens in template variables and will output the raw string.

## Mode Rules

| app.mode | Terminal node | `{{#sys.query#}}` | LLM `memory` |
|---|---|---|---|
| `advanced-chat` | `answer` | allowed/recommended in LLM user prompt | allowed |
| `workflow` | `end` | forbidden | forbidden |
| `agent-chat` | agent config/tools | depends on agent config | agent memory |

Never put `answer` in a `workflow` app. Never put `end` in an `advanced-chat` app.

In `workflow` mode, user input must come from declared Start variables or upstream node outputs. Referencing `{{#sys.query#}}` causes `Variable #sys.query# not found`.

## Start Node

Allowed variable types include `text-input`, `paragraph`, `number`, `select`, `file`, and `file-list`.

Rules:

- `number`, `select`, `file`, and `file-list` use `max_length: null`.
- `select` requires `options`.
- `advanced-chat` commonly uses `variables: []` and reads the user message via `{{#sys.query#}}`; only add Start variables when needed.
- There is no native `object` Start type. For JSON/spec input in workflow tools, use `paragraph` and parse with Code.

## LLM Node

Rules:

- For internal KURO AI Studio DSL, default LLM nodes to `provider: kurogames/kuro_ai_gateway/kuro_ai_provider` and `name: claude-opus-4.7` unless the user specifies another model.
- Use a user-provided provider/name when the user gives one.
- Always include a system guard such as "只输出最终结果,不输出推理过程或 <think> 标签" for structured or user-facing outputs.
- For structured JSON outputs, pair the LLM with a downstream Code node that robustly extracts/parses JSON.
- In `workflow` mode, do not write `memory` and do not reference `{{#sys.query#}}`.

## Code Node

Rules:

- `data.variables[].variable` must match the Python `main(...)` parameter names.
- `data.outputs` keys must match every downstream `value_selector` key.
- Python `return` keys should match `data.outputs`.
- Use try/except for LLM JSON parsing and external data normalization.
- Studio Code node sandbox commonly supports `json`, `re`, `math`, `datetime`, `string`, `base64`, `hashlib`, `uuid`, and `urllib.parse`.

Use a Code node to create constant values for `end` outputs. Do not put raw constants directly into `end.outputs[].value_selector`.

## If-Else Node

Operator value types are fragile:

| operator | `value` type |
|---|---|
| `contains`, `not contains`, `start with`, `end with`, `is`, `is not`, `=`, `!=`, `>`, `<`, `>=`, `<=` | string or boolean as appropriate |
| `in`, `not in`, `all of`, `exists in`, `not exists in` | array |
| `empty`, `not empty`, `null`, `not null`, `exists`, `not exists` | omit `value` or use null |

For multi-class classification, prefer `LLM -> Code normalize -> one if-else` instead of many chained if-else nodes.

Use current canvas schema:

```yaml
data:
  type: if-else
  cases:
    - case_id: 'true'
      id: 'true'
      logical_operator: and
      conditions:
        - id: cond-1
          variable_selector: [parse, intent]
          comparison_operator: is
          value: search
          varType: string
```

Do not generate legacy `data.conditions` or `else_id`. The default branch edge uses `sourceHandle: 'false'`. Case branches use their `case_id` as `sourceHandle`.

## Answer Node

Only for `advanced-chat`.

Rules:

- Each terminal branch needs an `answer` node or a path to one.
- `answer` text should reference upstream outputs, not re-read `{{#sys.query#}}`.
- Do not hide missing outputs in prose; fix the selectors.

## End Node

Only for `workflow`.

Rules:

- `outputs[].value_selector` must point to an upstream node output.
- For fixed fields like `status: success`, insert a Code node returning `{"status": "success"}` and reference that output.
- Multiple branches may share one End only if all referenced outputs are defined on every path; otherwise use branch-specific End nodes or a pack Code node.

## Knowledge Retrieval Node

Rules:

- `dataset_ids` must be real IDs or a clean placeholder such as `PLEASE_FILL_DATASET_ID`.
- Do not invent UUIDs.
- `query_variable_selector` must point to a string output.
- `retrieval_mode: multiple` should use `multiple_retrieval_config`.
- If downstream LLM needs readable context, insert a Code node to format chunks into text.

## HTTP Request Node

Rules:

- Keep `url` as a clean URL string. Do not append Chinese instructions or comments inside the URL.
- Put user-facing instructions in warnings, not executable fields.
- Use env vars for secrets, for example `{{#env.crm_token#}}`.
- `authorization.type` must match the target schema. Prefer `no-auth` or `api-key` with env-token patterns.
- Use `retry_config`, not legacy `retry`.
- `body.type` and `body.data` must agree:
  - `none`: empty string
  - `json`: object/string JSON body
  - `form-data`: array
  - `x-www-form-urlencoded`: string like `k=v&k2=v2`

## Tool / Workflow Tool / Export

Tool nodes are provider-specific. Do not generate arbitrary Tool nodes unless the provider schema is known.

For file export in the existing KURO DSL generator, the known exporter is:

- provider: `kurogames/dify-yml-exporter/dify_yml_exporter`
- tool: `export_yml`

Do not include credentials in skills or generated DSL. Use placeholders or environment variables.

## Template Engine Trap

Studio scans `{{#...#}}` patterns even inside some prompt/code strings. If a literal template marker must appear in a generated Code string, construct it by concatenation, for example:

```python
"{" + "{#sys.query#}" + "}"
```

## Final Warnings Policy

Use warnings for:

- Placeholder dataset IDs.
- Placeholder URLs.
- Missing tool provider IDs.
- Environment variables the user must fill.

Warnings do not make a YAML invalid if the fields are clean resource placeholders and the user asked to generate before providing resources.
