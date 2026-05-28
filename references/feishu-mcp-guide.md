# Internal Feishu/Lark MCP Guide

Use this guide when a Studio DSL requirement interacts with Feishu/Lark documents, Wiki, Base, Sheets, Drive, IM, tasks, calendar, contacts, HR, or AI Gateway quota.

## Source of Truth

Internal Base:

- URL: `https://kurogame.feishu.cn/base/Ktdbb6EYXanw7Ns5Uj0cEMVWnrb`
- Name observed via CLI: `MCP接入指南`
- Tables:
  - `场景速查` (`tbl9TtLXsGSQvCqI`): user goal -> required MCP domains and service addresses
  - `MCP 服务目录` (`tblbmzinsrE5FS6X`): domain -> MCP address, token mode, deployment status, applicable scenarios
  - `Tool 明细` (`tblvZ914EoR5zXS0`): tool id/name, domain, support status, token mode, tags

If the user asks for Feishu/Lark interaction and the exact tool/domain is not already known, query this Base instead of guessing.

## CLI Lookup

On this Windows machine, prefer:

```powershell
npm.cmd exec -g -- lark-cli auth status
npm.cmd exec -g -- lark-cli base +base-get --base-token Ktdbb6EYXanw7Ns5Uj0cEMVWnrb
npm.cmd exec -g -- lark-cli base +table-list --base-token Ktdbb6EYXanw7Ns5Uj0cEMVWnrb --limit 100
npm.cmd exec -g -- lark-cli base +record-list --base-token Ktdbb6EYXanw7Ns5Uj0cEMVWnrb --table-id tbl9TtLXsGSQvCqI --limit 100
npm.cmd exec -g -- lark-cli base +record-list --base-token Ktdbb6EYXanw7Ns5Uj0cEMVWnrb --table-id tblbmzinsrE5FS6X --limit 100
npm.cmd exec -g -- lark-cli base +record-list --base-token Ktdbb6EYXanw7Ns5Uj0cEMVWnrb --table-id tblvZ914EoR5zXS0 --limit 100
```

Use `--as user` for user-authorized token behavior when needed. If `auth status` says the user token is expired or cannot refresh, ask the user to refresh CLI authorization before claiming current MCP/tool availability.

## Routing Rules

- Feishu cloud documents: use `docx`. For reading content, prefer `docx.v1.document.rawContent`; for block-level operations, use document block tools when available.
- Wiki / company knowledge base: use `wiki` to locate nodes or browse spaces, then `docx` to read document content when the node points to a document.
- Multi-dimensional Base data: use `bitable` for apps/tables/fields/views/records and batch record reads/writes.
- Feishu spreadsheet cells: use `sheets`, not `bitable`.
- Drive files/folders/downloads/permissions: use `drive`.
- User lookup by email/phone/open id: use `contact`.
- Sending messages, group membership, message history: use `im`, but check deployment status first because many IM tools may be marked `待上线`.
- Tasks and calendar: use `task` or `calendar`, but check deployment status first.
- Studio quota and model consumption under Feishu account: use the AI Gateway MCP entry.

## Token Mode

- `UAT`: user-authorized token. Prefer this for document/Wiki/Drive/Base operations where user permissions must be respected.
- `TAT`: tenant/app token. Use only when the Base lists the service/tool as tenant-token based and the scenario is app identity or tenant-level lookup.

Do not embed Feishu user tokens, tenant access tokens, app secrets, cookies, or console headers in generated DSL. Use environment variables or MCP/tool credentials managed by Studio.

## Generation Rules

- Do not invent Feishu MCP addresses, provider IDs, or tool IDs. Query the Base and use entries marked `已上线`.
- If a required domain or tool is `待上线`, do not generate an active tool node that pretends it is available. Add a placeholder/warning or ask the user whether to use an HTTP fallback.
- For workflows that combine Feishu actions, model the domains explicitly in the spec. Example: "read Base records then send group notification" requires `bitable` plus `im`; if `im` is not deployed, the DSL should expose that gap.
- For direct Feishu OpenAPI HTTP nodes, prefer internal MCP services when available. Use raw OpenAPI token flows only when the user explicitly asks for direct HTTP or the needed MCP domain is unavailable.
- After selecting MCP/tool resources, still validate normal Studio DSL rules: runtime-safe node IDs, canvas-safe graph fields, model provider/name, and selectors/templates.
