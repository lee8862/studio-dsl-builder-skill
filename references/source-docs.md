# Internal Source Notes

This file is an internal maintenance map for KURO AI Studio teams. It is not required for normal skill usage.

The skill can generate and validate Studio DSL files from its bundled rules. Use the source documents only when schema behavior changes, a generated DSL fails in a new release, or a less common node needs to be checked against the current platform.

## DSL Agent Sources

Repository-relative path:

```text
docs/create-agent/dsl-agent/
```

Useful files:

- `README.md`: single-app DSL generator architecture and deployment overview.
- `DEPLOY.md`: detailed deployment and smoke-test checklist.
- `TROUBLESHOOTING.md`: known import/runtime failure modes.
- `dsl-agent-v1.6.9.3.yml`: single-app generator with YAML export attachment-card integration.
- `node_schemas_kb/*.md`: node schema rules for Start, LLM, Code, If-Else, HTTP, Knowledge Retrieval, Answer, and End.
- `examples/*.md`: benchmark graph patterns for moderation/translation, customer routing, and HTTP+RAG.

## Meta-Agent Sources

Repository-relative path:

```text
docs/create-agent/meta-agent/
```

Useful files:

- `TOOL_SPEC.md`: routing contract for plan/generate/troubleshoot/search capabilities.
- `SPLIT_NOTES.md`: notes on splitting the advanced-chat generator into stateless workflow tools.
- `README_DEPLOY.md`: manual deployment flow and provider ID pitfalls.
- `meta-agent.yml`: current agent-chat skeleton and prompt discipline.
- `plan-dsl-spec.yml`: stateless planner workflow.
- `generate-dsl-yml.yml`: YAML generator workflow.
- `troubleshoot-yml.yml`: troubleshooting workflow.
- `tests/cases.jsonl`: behavioral regression cases.
- `tests/reports/runs/*/summary.md`: observed pass/fail behavior.

## Safety Notes

- Do not copy credentials, API keys, cookies, app keys, user tokens, or console API headers into this skill or into generated public examples.
- Deployment handover files may contain operational context or credentials. Treat them as private operational records, not skill source material.
- Re-check the exact KURO AI Studio/Dify release version before changing node schemas or import rules.
- Prefer current exported YAML and node schema docs over old memory or summaries when they disagree.
