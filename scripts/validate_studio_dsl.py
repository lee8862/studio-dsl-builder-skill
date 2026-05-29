#!/usr/bin/env python3
"""Lightweight structural validator for internal KURO AI Studio DSL YAML.

This catches the common "parseable but not runnable/importable" mistakes that
show up in generated DSL files and real Studio exports. The default profile is
export-friendly: runtime breakages are errors, while canvas decoration drift and
static uncertainty are warnings. Use --profile generated for stricter checks on
newly generated DSL files before delivery.
"""

from __future__ import annotations

import json
import re
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

RUNTIME_NODE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]{1,50}$")
RUNTIME_TEMPLATE_PATTERN = re.compile(r"\{\{#([a-zA-Z0-9_]{1,50}(?:\.[a-zA-Z_][a-zA-Z0-9_]{0,29}){1,10})#\}\}")
LOCAL_TEMPLATE_PATTERN = re.compile(r"\{\{#([a-zA-Z_][a-zA-Z0-9_]{0,50})#\}\}")
LOOSE_TEMPLATE_PATTERN = re.compile(r"\{\{#([^#\n]+)#\}\}")
SELECTOR_KEYS = {"value_selector", "variable_selector", "query_variable_selector", "iterator_selector", "output_selector"}
TOOL_REQUIRED_FIELDS = {
    "provider_id",
    "provider_type",
    "provider_name",
    "tool_name",
    "tool_label",
    "tool_configurations",
    "tool_parameters",
}
CODE_OUTPUT_CAPS = {
    "array[string]": "30 items",
    "array[object]": "30 items",
    "array[number]": "1000 items",
}
TERMINAL_NODE_TYPES = {"answer", "end"}
CANVAS_PROFILES = {"generated"}


def add_issue(
    *,
    errors: list[str],
    warnings: list[str],
    message: str,
    as_error: bool,
) -> None:
    if as_error:
        errors.append(message)
    else:
        warnings.append(message)


def load_dsl(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig")
    try:
        import yaml  # type: ignore
    except Exception:
        return json.loads(text)
    return yaml.safe_load(text)


def node_title(node: dict[str, Any]) -> str:
    data = node.get("data") or {}
    return str(data.get("title") or node.get("id") or "<unknown>")


def selector_text(value: Any) -> str:
    if isinstance(value, list):
        return ".".join(str(x) for x in value)
    return str(value)


def iter_strings(value: Any, path: str = "$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_strings(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from iter_strings(item, f"{path}.{key}")


def iter_selectors(value: Any, path: str = "$"):
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_selectors(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            current_path = f"{path}.{key}"
            if key in SELECTOR_KEYS and isinstance(item, list) and item:
                yield current_path, item
            yield from iter_selectors(item, current_path)


def collect_output_types(node: dict[str, Any]) -> dict[str, str]:
    data = node.get("data") or {}
    outputs = data.get("outputs") or {}
    if isinstance(outputs, dict):
        result: dict[str, str] = {}
        for key, value in outputs.items():
            if isinstance(value, dict):
                result[str(key)] = str(value.get("type") or "")
            else:
                result[str(key)] = ""
        return result
    if isinstance(outputs, list):
        result = {}
        for item in outputs:
            if isinstance(item, dict) and item.get("variable"):
                result[str(item["variable"])] = str(item.get("type") or "")
        return result
    return {}


def collect_code_outputs(node: dict[str, Any]) -> set[str]:
    return set(collect_output_types(node))


def condition_value_required(operator: str) -> str:
    array_ops = {"in", "not in", "all of", "exists in", "not exists in"}
    empty_ops = {"empty", "not empty", "null", "not null", "exists", "not exists"}
    if operator in array_ops:
        return "array"
    if operator in empty_ops:
        return "none"
    return "scalar"


def validate(path: Path, profile: str = "base") -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    strict_canvas = profile in CANVAS_PROFILES

    try:
        dsl = load_dsl(path)
    except Exception as exc:
        return [f"parse failed: {exc}"], warnings

    if not isinstance(dsl, dict):
        return ["root must be a mapping/object"], warnings

    app = dsl.get("app")
    workflow = dsl.get("workflow")
    if not isinstance(app, dict):
        errors.append("missing app mapping")
        app = {}
    if dsl.get("kind") != "app":
        errors.append("kind must be app")
    if "version" not in dsl:
        errors.append("missing version")
    if not isinstance(workflow, dict):
        errors.append("missing workflow mapping")
        workflow = {}

    mode = app.get("mode")
    if mode not in {"advanced-chat", "workflow", "agent-chat", "chat"}:
        errors.append(f"unexpected app.mode: {mode!r}")

    graph = workflow.get("graph") if isinstance(workflow, dict) else None
    if not isinstance(graph, dict):
        if mode == "agent-chat":
            return errors, warnings
        errors.append("missing workflow.graph")
        graph = {}

    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not isinstance(nodes, list):
        errors.append("workflow.graph.nodes must be an array")
        nodes = []
    if not isinstance(edges, list):
        errors.append("workflow.graph.edges must be an array")
        edges = []

    by_id: dict[str, dict[str, Any]] = {}
    node_type_by_id: dict[str, str] = {}
    type_counts: dict[str, int] = {}
    output_by_node: dict[str, set[str]] = {}
    iteration_output_nodes: set[str] = set()

    if mode != "agent-chat" and not isinstance(graph.get("viewport"), dict):
        add_issue(
            errors=errors,
            warnings=warnings,
            message="workflow.graph.viewport should be present for generated/canvas-safe imports",
            as_error=strict_canvas,
        )

    for node in nodes:
        if not isinstance(node, dict):
            errors.append("node entry is not an object")
            continue
        node_id = str(node.get("id") or "")
        data = node.get("data") or {}
        node_type = str(data.get("type") or node.get("type") or "")
        if not node_id:
            errors.append(f"node without id: {node}")
            continue
        if not RUNTIME_NODE_ID_PATTERN.fullmatch(node_id):
            add_issue(
                errors=errors,
                warnings=warnings,
                message=(
                    f"node id '{node_id}' is not runtime-template safe if referenced in {{#node.output#}}; "
                    "prefer letters, numbers, or underscores"
                ),
                as_error=strict_canvas,
            )
        if node_id in by_id:
            errors.append(f"duplicate node id: {node_id}")
        by_id[node_id] = node
        node_type_by_id[node_id] = node_type
        type_counts[node_type] = type_counts.get(node_type, 0) + 1

        if node_type == "iteration":
            data_output_selector = data.get("output_selector")
            if isinstance(data_output_selector, list) and data_output_selector:
                iteration_output_nodes.add(str(data_output_selector[0]))

        if mode != "agent-chat":
            if node.get("type") != "custom":
                add_issue(
                    errors=errors,
                    warnings=warnings,
                    message=f"node '{node_title(node)}' top-level type should be custom for generated canvas DSL",
                    as_error=strict_canvas,
                )
            for key in ("position", "positionAbsolute"):
                if not isinstance(node.get(key), dict):
                    add_issue(
                        errors=errors,
                        warnings=warnings,
                        message=f"node '{node_title(node)}' missing canvas field {key}",
                        as_error=strict_canvas,
                    )
            for key in ("sourcePosition", "targetPosition", "selected", "width", "height"):
                if key not in node:
                    add_issue(
                        errors=errors,
                        warnings=warnings,
                        message=f"node '{node_title(node)}' missing canvas field {key}",
                        as_error=strict_canvas,
                    )
            if "zIndex" not in node:
                add_issue(
                    errors=errors,
                    warnings=warnings,
                    message=f"node '{node_title(node)}' missing top-level zIndex; preserve/export or set 0/1002",
                    as_error=strict_canvas,
                )
            for key in ("desc", "selected"):
                if key not in data:
                    add_issue(
                        errors=errors,
                        warnings=warnings,
                        message=f"node '{node_title(node)}' data missing canvas field {key}",
                        as_error=strict_canvas,
                    )

        outputs = collect_code_outputs(node)
        if node_type == "llm":
            outputs.add("text")
        elif node_type == "knowledge-retrieval":
            outputs.add("result")
        elif node_type == "http-request":
            outputs.update({"body", "status_code", "headers", "files"})
        elif node_type == "tool":
            outputs.update({"text", "files", "json"})
        elif node_type in {"template-transform", "variable-aggregator"}:
            outputs.add("output")
        elif node_type == "question-classifier":
            outputs.add("class_name")
        elif node_type == "iteration":
            outputs.update({"output", "item"})
        elif node_type == "start":
            for var in data.get("variables") or []:
                if isinstance(var, dict) and var.get("variable"):
                    outputs.add(str(var["variable"]))
        output_by_node[node_id] = outputs

        if node_type == "start":
            for var in data.get("variables") or []:
                if not isinstance(var, dict):
                    continue
                var_type = var.get("type")
                var_name = var.get("variable") or var.get("label") or "<unnamed>"
                if var_type in {"number", "select", "file", "file-list"} and var.get("max_length") is not None:
                    errors.append(f"start variable {var_name!r} type {var_type!r} must use max_length: null")
                if var_type == "select":
                    options = var.get("options")
                    if not isinstance(options, list) or not options:
                        errors.append(f"start select variable {var_name!r} must have a non-empty string options array")
                    elif any(not isinstance(option, str) for option in options):
                        errors.append(f"start select variable {var_name!r} options must be plain strings, not objects")

        if node_type == "code":
            for output_name, output_type in collect_output_types(node).items():
                cap = CODE_OUTPUT_CAPS.get(output_type)
                if cap:
                    warnings.append(
                        f"code node '{node_title(node)}' output {output_name!r} type {output_type} is capped by "
                        f"runtime config (current default {cap})"
                    )

        if node_type == "tool":
            missing = sorted(field for field in TOOL_REQUIRED_FIELDS if field not in data)
            if missing:
                errors.append(f"tool node '{node_title(node)}' missing runtime fields: {', '.join(missing)}")
            if not isinstance(data.get("tool_configurations"), dict):
                errors.append(f"tool node '{node_title(node)}' tool_configurations must be a mapping")
            if not isinstance(data.get("tool_parameters"), dict):
                errors.append(f"tool node '{node_title(node)}' tool_parameters must be a mapping")
            provider_id = str(data.get("provider_id") or "")
            provider_type = str(data.get("provider_type") or "")
            if "PLEASE_FILL" in provider_id or provider_id.startswith("__REPLACE"):
                warnings.append(f"tool node '{node_title(node)}' contains provider_id placeholder")
            if provider_type == "plugin":
                errors.append(
                    f"tool node '{node_title(node)}' uses provider_type 'plugin'; installed plugin workflow nodes "
                    "should normally use provider_type 'builtin' with plugin metadata preserved"
                )
            if provider_type == "mcp":
                for optional_field in ("is_team_authorization", "plugin_id", "plugin_unique_identifier"):
                    if optional_field not in data:
                        warnings.append(
                            f"MCP tool node '{node_title(node)}' missing exported provider metadata {optional_field!r}; "
                            "copy a full tool node from the same workspace when possible"
                        )
                if not any(field in data for field in ("provider_icon", "icon")):
                    warnings.append(
                        f"MCP tool node '{node_title(node)}' missing exported provider icon metadata; "
                        "copy a full tool node from the same workspace when possible"
                    )
            if isinstance(data.get("output_schema"), dict):
                warnings.append(
                    f"tool node '{node_title(node)}' has output_schema; downstream selectors should still use "
                    "'json', 'text', or explicit streamed variables, not output_schema.properties directly"
                )

        if node_type == "llm":
            model = data.get("model") or {}
            if not model.get("provider") or not model.get("name"):
                errors.append(f"LLM node '{node_title(node)}' must set internal Studio model provider/name")
            memory = data.get("memory")
            if isinstance(memory, dict) and ("enabled" in memory or "role_prefix" in memory):
                warnings.append(f"LLM node '{node_title(node)}' uses legacy memory shape; prefer query_prompt_template/window")
            if mode == "workflow":
                if "memory" in data:
                    errors.append(f"workflow LLM node '{node_title(node)}' must not contain memory")
                text = json.dumps(data.get("prompt_template") or "", ensure_ascii=False)
                if "{{#sys.query#}}" in text:
                    errors.append(f"workflow LLM node '{node_title(node)}' references {{#sys.query#}}")

        if node_type == "knowledge-retrieval":
            dataset_ids = data.get("dataset_ids")
            if not isinstance(dataset_ids, list) or not dataset_ids:
                errors.append(f"KR node '{node_title(node)}' must have non-empty dataset_ids array")
            elif any(str(x).startswith("PLEASE_FILL") for x in dataset_ids):
                warnings.append(f"KR node '{node_title(node)}' contains dataset placeholder")
            selector = data.get("query_variable_selector")
            if not selector:
                errors.append(f"KR node '{node_title(node)}' missing query_variable_selector")

        if node_type == "http-request":
            url = str(data.get("url") or "")
            if not url:
                errors.append(f"HTTP node '{node_title(node)}' missing url")
            if re.search(r"\s(--|#|请|填|说明|TODO)", url):
                errors.append(f"HTTP node '{node_title(node)}' url contains prose/instructions")
            if "PLEASE_FILL" in url:
                warnings.append(f"HTTP node '{node_title(node)}' contains URL placeholder")
            if "retry" in data:
                errors.append(f"HTTP node '{node_title(node)}' uses legacy retry; use retry_config")
            auth = data.get("authorization") or {}
            if isinstance(auth, dict) and auth.get("type") not in {"no-auth", "api-key"}:
                errors.append(f"HTTP node '{node_title(node)}' has unsupported authorization.type {auth.get('type')!r}")

        if node_type == "if-else":
            if "conditions" in data or "else_id" in data:
                errors.append(f"if-else node '{node_title(node)}' uses legacy conditions/else_id; use cases plus false edge")
            if not isinstance(data.get("cases"), list) or not data.get("cases"):
                errors.append(f"if-else node '{node_title(node)}' must have non-empty cases array")
            for case in data.get("cases") or []:
                if not isinstance(case, dict):
                    continue
                if not case.get("case_id"):
                    errors.append(f"if-else node '{node_title(node)}' case missing case_id")
                if not case.get("id"):
                    errors.append(f"if-else node '{node_title(node)}' case missing id")
                if not case.get("logical_operator"):
                    errors.append(f"if-else node '{node_title(node)}' case missing logical_operator")
                for condition in case.get("conditions") or []:
                    if not isinstance(condition, dict):
                        continue
                    if not condition.get("id"):
                        errors.append(f"if-else node '{node_title(node)}' condition missing id")
                    if not condition.get("varType"):
                        errors.append(f"if-else node '{node_title(node)}' condition missing varType")
                    op = str(condition.get("comparison_operator") or "")
                    want = condition_value_required(op)
                    has_value = "value" in condition and condition.get("value") is not None
                    value = condition.get("value")
                    if want == "array" and not isinstance(value, list):
                        errors.append(f"if-else node '{node_title(node)}' operator {op!r} requires array value")
                    if want == "none" and has_value:
                        errors.append(f"if-else node '{node_title(node)}' operator {op!r} should omit value")

        if node_type == "end":
            outputs_cfg = data.get("outputs") or []
            if not isinstance(outputs_cfg, list):
                errors.append(f"end node '{node_title(node)}' outputs must be an array")
            else:
                for out in outputs_cfg:
                    if not isinstance(out, dict):
                        continue
                    selector = out.get("value_selector")
                    if not isinstance(selector, list) or len(selector) < 2:
                        errors.append(f"end node '{node_title(node)}' output {out.get('variable')!r} has invalid value_selector")
                        continue
                    src_id = str(selector[0])
                    src_key = str(selector[1])
                    if src_id not in by_id:
                        errors.append(f"end output selector references missing node {selector_text(selector)}")
                    elif src_key not in output_by_node.get(src_id, set()) and output_by_node.get(src_id):
                        warnings.append(f"end output selector {selector_text(selector)} not declared in upstream outputs")

    for string_path, text in iter_strings(dsl):
        for match in LOOSE_TEMPLATE_PATTERN.finditer(text):
            full = match.group(0)
            inner = match.group(1)
            local_match = LOCAL_TEMPLATE_PATTERN.fullmatch(full)
            runtime_match = RUNTIME_TEMPLATE_PATTERN.fullmatch(full)
            if local_match:
                continue
            if not runtime_match:
                add_issue(
                    errors=errors,
                    warnings=warnings,
                    message=(
                        f"template variable {full!r} at {string_path} is not a standard node selector; "
                        "verify it is intentionally escaped or generated at runtime"
                    ),
                    as_error=strict_canvas and ".data.code" not in string_path,
                )
                continue
            selector = inner.split(".")
            src_id = selector[0]
            src_key = selector[1] if len(selector) > 1 else ""
            in_code_string = ".data.code" in string_path
            if src_id in {"sys", "env", "conversation"}:
                continue
            if src_id not in by_id:
                add_issue(
                    errors=errors,
                    warnings=warnings,
                    message=f"template variable {full!r} at {string_path} references missing node {src_id}",
                    as_error=not in_code_string,
                )
            else:
                source_type = node_type_by_id.get(src_id)
                invalid_tool_data_selector = False
                if source_type == "tool" and src_key == "data":
                    invalid_tool_data_selector = True
                    add_issue(
                        errors=errors,
                        warnings=warnings,
                        message=f"template variable {full!r} at {string_path} selects tool output 'data'; use 'json' instead",
                        as_error=not in_code_string,
                    )
                if source_type == "iteration" and src_key == "item" and len(selector) > 2:
                    add_issue(
                        errors=errors,
                        warnings=warnings,
                        message=(
                            f"template variable {full!r} at {string_path} deep-selects iteration item; "
                            "destructure item fields in a Code node"
                        ),
                        as_error=not in_code_string,
                    )
                if (
                    not invalid_tool_data_selector
                    and src_key not in output_by_node.get(src_id, set())
                    and output_by_node.get(src_id)
                ):
                    warnings.append(f"template variable {full!r} at {string_path} not declared in upstream outputs")

    checked_selectors: set[tuple[str, str]] = set()
    for selector_path, selector in iter_selectors(dsl):
        if len(selector) < 2:
            continue
        src_id = str(selector[0])
        src_key = str(selector[1])
        if src_id in {"", "sys", "env", "conversation"}:
            continue
        selector_key = (selector_path, selector_text(selector))
        if selector_key in checked_selectors:
            continue
        checked_selectors.add(selector_key)
        if src_id not in by_id:
            errors.append(f"selector {selector_text(selector)} at {selector_path} references missing node {src_id}")
            continue
        source_type = node_type_by_id.get(src_id)
        invalid_tool_data_selector = False
        if source_type == "tool" and src_key == "data":
            invalid_tool_data_selector = True
            errors.append(f"selector {selector_text(selector)} at {selector_path} selects tool output 'data'; use 'json'")
        if source_type == "iteration" and src_key == "item" and len(selector) > 2:
            errors.append(
                f"selector {selector_text(selector)} at {selector_path} deep-selects iteration item; "
                "destructure item fields in a Code node"
            )
        if (
            not invalid_tool_data_selector
            and src_key not in output_by_node.get(src_id, set())
            and output_by_node.get(src_id)
        ):
            warnings.append(f"selector {selector_text(selector)} at {selector_path} not declared in upstream outputs")

    if mode == "workflow" and type_counts.get("answer", 0):
        errors.append("workflow mode must not use answer nodes")
    if mode == "workflow" and not type_counts.get("end", 0):
        errors.append("workflow mode must include at least one end node")
    if mode == "advanced-chat" and type_counts.get("end", 0):
        errors.append("advanced-chat mode must not use end nodes")
    if mode == "advanced-chat" and not type_counts.get("answer", 0):
        errors.append("advanced-chat mode must include at least one answer node")

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    in_degree: dict[str, int] = {node_id: 0 for node_id in by_id}
    out_degree: dict[str, int] = {node_id: 0 for node_id in by_id}

    for edge in edges:
        if not isinstance(edge, dict):
            errors.append("edge entry is not an object")
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in by_id:
            errors.append(f"edge {edge.get('id')} references missing source {source}")
        if target not in by_id:
            errors.append(f"edge {edge.get('id')} references missing target {target}")
        if source in by_id and target in by_id:
            adjacency.setdefault(source, []).append(target)
            out_degree[source] = out_degree.get(source, 0) + 1
            in_degree[target] = in_degree.get(target, 0) + 1
        if mode != "agent-chat":
            if edge.get("type") != "custom":
                add_issue(
                    errors=errors,
                    warnings=warnings,
                    message=f"edge {edge.get('id')} type should be custom for generated canvas DSL",
                    as_error=strict_canvas,
                )
            for key in ("sourceHandle", "targetHandle", "zIndex"):
                if key not in edge:
                    add_issue(
                        errors=errors,
                        warnings=warnings,
                        message=f"edge {edge.get('id')} missing canvas field {key}",
                        as_error=strict_canvas,
                    )
            edge_data = edge.get("data")
            if not isinstance(edge_data, dict):
                add_issue(
                    errors=errors,
                    warnings=warnings,
                    message=f"edge {edge.get('id')} missing canvas data mapping",
                    as_error=strict_canvas,
                )
            else:
                for key in ("isInIteration", "isInLoop", "sourceType", "targetType"):
                    if key not in edge_data:
                        add_issue(
                            errors=errors,
                            warnings=warnings,
                            message=f"edge {edge.get('id')} data missing canvas field {key}",
                            as_error=strict_canvas,
                        )

    if mode != "agent-chat":
        executable_nodes = {
            node_id
            for node_id, node in by_id.items()
            if node.get("type") != "custom-note" and node_type_by_id.get(node_id)
        }
        start_ids = [node_id for node_id in executable_nodes if node_type_by_id.get(node_id) == "start"]
        if not start_ids:
            errors.append("graph must include a start node")
        else:
            reachable: set[str] = set()
            queue = list(start_ids)
            while queue:
                current = queue.pop(0)
                if current in reachable:
                    continue
                reachable.add(current)
                current_node = by_id.get(current) or {}
                current_data = current_node.get("data") or {}
                if node_type_by_id.get(current) == "iteration" and current_data.get("start_node_id"):
                    queue.append(str(current_data["start_node_id"]))
                queue.extend(adjacency.get(current, []))

            for node_id in sorted(executable_nodes - reachable):
                warnings.append(f"node '{node_title(by_id[node_id])}' is unreachable from start")

            for node_id in sorted(reachable & executable_nodes):
                node_type = node_type_by_id.get(node_id, "")
                if node_type in TERMINAL_NODE_TYPES or node_id in iteration_output_nodes:
                    continue
                if in_degree.get(node_id, 0) > 0 and out_degree.get(node_id, 0) == 0:
                    add_issue(
                        errors=errors,
                        warnings=warnings,
                        message=(
                            f"reachable non-terminal node '{node_title(by_id[node_id])}' has no outgoing edge; "
                            "connect it to a terminal node or an iteration output"
                        ),
                        as_error=strict_canvas,
                    )

    for node_id, node in by_id.items():
        data = node.get("data") or {}
        if data.get("type") != "if-else":
            continue
        handles = {str(edge.get("sourceHandle")) for edge in edges if isinstance(edge, dict) and edge.get("source") == node_id}
        for case in data.get("cases") or []:
            case_id = str(case.get("case_id") or "")
            if case_id and case_id not in handles:
                warnings.append(f"if-else node '{node_title(node)}' case {case_id!r} has no outgoing edge")
        if "false" not in handles:
            warnings.append(f"if-else node '{node_title(node)}' has no false/default outgoing edge")

    return errors, warnings


def main(argv: list[str]) -> int:
    parser = ArgumentParser(description="Validate internal KURO AI Studio DSL YAML.")
    parser.add_argument("path", help="Path to a Studio/Dify DSL YAML file")
    parser.add_argument(
        "--profile",
        choices=("base", "exported", "generated"),
        default="base",
        help=(
            "base/exported keep canvas decoration drift as warnings; "
            "generated treats generated-DSL canvas omissions as errors"
        ),
    )
    args = parser.parse_args(argv[1:])

    path = Path(args.path)
    errors, warnings = validate(path, profile=args.profile)
    result = {
        "path": str(path),
        "profile": args.profile,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
