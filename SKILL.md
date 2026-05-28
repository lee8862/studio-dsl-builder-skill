---
name: studio-dsl-builder
description: Generate, repair, and validate import-ready Studio DSL YAML files for workflow, advanced-chat/chatflow, and agent-chat apps on internal KURO AI Studio. Use when the user asks to create a Studio agent/workflow/app from requirements, convert a product idea into DSL YAML, produce a usable `.yml` file, fix generated DSL import/runtime errors, or check whether a Studio DSL is structurally runnable.
---

# Studio DSL Builder

## Objective

Turn user requirements into a real Studio DSL `.yml` that can be imported into internal KURO AI Studio with minimal manual work. Do not stop at architecture advice unless the user explicitly asks for advice only.

Prefer creating or patching an actual YAML file in the current workspace or the user-provided path. Also provide a short summary and the file path. If the user requests inline output, include the YAML in a fenced block after writing the file.

## First Decision

Classify the request:

- **Create**: user wants a new agent/workflow/chatflow/app DSL.
- **Repair**: user has an existing YAML or import/runtime error.
- **Validate**: user asks whether a generated YAML is usable.
- **Explain**: user asks concept/schema questions; answer from references, and avoid generating files unless asked.

For repair/validate, inspect the real YAML first. For create, run the domain completeness gate, build a spec, then generate.

## Domain Completeness Gate

Before generating a business workflow, decide whether the user's request contains enough domain rules to produce a useful app rather than a generic shell.

Treat these as **rule-heavy domains**: procurement, approval, finance, legal, compliance, HR, contract review, vendor management, reimbursement, audit, security review, customer service routing with SLAs, and any workflow that claims to "approve", "pre-check", "score", "risk-rate", "route", or "decide".

For rule-heavy domains, ask up to two high-impact questions before generating unless the user explicitly says "use defaults", "do not ask", "直接生成", or already provided equivalent details:

- **Decision rules/source of truth**: thresholds, required documents, policy KB, scoring rubric, SLA, branch conditions, approval matrix.
- **System/data integration**: budget system, supplier system, OA/Feishu approval API, blacklist, contract repository, knowledge base, tool/provider IDs.

If the user does not answer and still wants output, generate a file labeled as an **internal import-ready skeleton**, include warnings about missing rules/data sources, and avoid claiming it is production-ready or fully runnable.

## Creation Workflow

1. **Clarify blocking or rule-heavy gaps.**
   Ask at most two questions if missing details would change the graph shape, app mode, external resource wiring, or domain decision logic. For rule-heavy domains, do not silently invent policy thresholds or approval rules. If the user says "directly generate" or enough information exists, choose safe defaults and continue.

2. **Build a compact spec.**
   Capture:
   - `app_name`
   - `app_mode`: `advanced-chat`, `workflow`, or `agent-chat`
   - inputs and outputs
   - node chain and branch logic
   - domain decision rules or the explicit decision to use generic defaults
   - Studio resources: KB dataset IDs, APIs, tools, env vars, and LLM model override if any
   - error handling and fallback behavior
   - warnings/placeholders that remain

3. **Choose app mode.**
   - Use `advanced-chat` for user-facing chat, one user message to one streamed answer, memory, RAG Q&A, customer service, assistants.
   - Use `workflow` for API/batch jobs with explicit inputs/outputs, scheduled/triggered jobs, ETL, document processing, deterministic output fields.
   - Use `agent-chat` for tool-calling agents that route between tools or sub-workflows.

4. **Generate import-ready YAML.**
   Use the hard rules in `references/schema-rules.md`. Use the graph patterns in `references/patterns.md`. Use the internal Studio default model unless the user specifies another model. Avoid inventing workspace-specific IDs. If a dataset, API, or tool resource is unknown and the user did not provide it, either ask or use a clean placeholder plus a warning.

5. **Write a `.yml` file.**
   If no path is given, create a descriptive file under the current workspace, such as `studio-dsl-output/<slug>.yml`. Use stable, readable app and node names. Keep Chinese labels when the user uses Chinese.

6. **Validate before finalizing.**
   Run:
   ```bash
   python scripts/validate_studio_dsl.py <path-to-yml>
   ```
   Fix errors. If warnings remain because placeholders are intentional, mention them clearly.

## Repair Workflow

1. Parse the YAML.
2. Identify the failing node or import/runtime constraint.
3. Patch narrowly; preserve existing I/O contracts unless the user asks to change them.
4. Re-run the validator.
5. Return the patched file path and the exact risk/warning that remains.

Common repair targets:

- `workflow` app uses `answer`, or `advanced-chat` app uses `end`.
- `workflow` LLM node contains `memory` or `{{#sys.query#}}`.
- `if-else` operator value has the wrong type.
- `end.outputs[].value_selector` points to a missing upstream output.
- URL/header/body fields contain natural language instructions.
- KB/model/tool IDs were hallucinated.
- Code node outputs do not match the Python `return` keys.
- Answer/LLM templates render raw strings such as `{{#node-reply.text#}}` because the node ID contains hyphens; replace final YAML node IDs and all selectors/templates with runtime-safe IDs.

## Validation Standard

A DSL is not "done" just because YAML parses. It must pass:

- Top-level `app`, `kind: app`, `version`, `workflow`.
- Every edge references existing source and target nodes.
- App mode terminal nodes are correct.
- Every selector points to a real upstream node/output.
- Node IDs and `{{#node.output#}}` template variables are runtime-safe; do not leave hyphenated `node-*` IDs in final YAML.
- LLM model config is filled with the internal Studio default model or the user-provided model.
- Resource placeholders are clean and contained in the correct machine fields.
- No executable field contains explanatory prose.
- Branches terminate in an `answer` or `end` path appropriate to the app mode.

## Resource Loading

Load only what is needed:

- `references/schema-rules.md`: hard import/runtime rules and known traps.
- `references/patterns.md`: reusable graph patterns and spec/output templates.
- `references/source-docs.md`: source document paths and when to inspect them.

Use `scripts/validate_studio_dsl.py` every time you create or patch a DSL file.

## Output Style

Final responses should be concise and operational:

- State what file was created or patched.
- Summarize the graph in one sentence.
- List only remaining placeholders or manual steps.
- Mention validator result.

Do not present generated YAML as "ready" if validation failed. If a file has resource placeholders, call it "import-ready after filling placeholders" rather than "fully runnable".
