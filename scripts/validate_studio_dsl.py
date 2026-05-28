#!/usr/bin/env python3
"""Lightweight structural validator for internal KURO AI Studio DSL YAML.

This catches the common "parseable but not runnable/importable" mistakes that
show up in generated DSL files. It is intentionally conservative: warnings are
allowed for placeholders, errors indicate issues to fix before delivery.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


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


def collect_code_outputs(node: dict[str, Any]) -> set[str]:
    data = node.get("data") or {}
    outputs = data.get("outputs") or {}
    if isinstance(outputs, dict):
        return set(outputs.keys())
    if isinstance(outputs, list):
        return {str(item.get("variable")) for item in outputs if isinstance(item, dict) and item.get("variable")}
    return set()


def condition_value_required(operator: str) -> str:
    array_ops = {"in", "not in", "all of", "exists in", "not exists in"}
    empty_ops = {"empty", "not empty", "null", "not null", "exists", "not exists"}
    if operator in array_ops:
        return "array"
    if operator in empty_ops:
        return "none"
    return "scalar"


def validate(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

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
    type_counts: dict[str, int] = {}
    output_by_node: dict[str, set[str]] = {}

    if mode != "agent-chat" and not isinstance(graph.get("viewport"), dict):
        errors.append("workflow.graph.viewport must be present for canvas import")

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
        if node_id in by_id:
            errors.append(f"duplicate node id: {node_id}")
        by_id[node_id] = node
        type_counts[node_type] = type_counts.get(node_type, 0) + 1

        if mode != "agent-chat":
            if node.get("type") != "custom":
                errors.append(f"node '{node_title(node)}' top-level type must be custom for canvas rendering")
            for key in ("position", "positionAbsolute"):
                if not isinstance(node.get(key), dict):
                    errors.append(f"node '{node_title(node)}' missing {key}")
            for key in ("sourcePosition", "targetPosition", "selected", "width", "height"):
                if key not in node:
                    errors.append(f"node '{node_title(node)}' missing canvas field {key}")
            for key in ("desc", "selected"):
                if key not in data:
                    errors.append(f"node '{node_title(node)}' data missing canvas field {key}")

        outputs = collect_code_outputs(node)
        if node_type == "llm":
            outputs.add("text")
        elif node_type == "knowledge-retrieval":
            outputs.add("result")
        elif node_type == "http-request":
            outputs.update({"body", "status_code", "headers", "files"})
        elif node_type == "start":
            for var in data.get("variables") or []:
                if isinstance(var, dict) and var.get("variable"):
                    outputs.add(str(var["variable"]))
        output_by_node[node_id] = outputs

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

    if mode == "workflow" and type_counts.get("answer", 0):
        errors.append("workflow mode must not use answer nodes")
    if mode == "workflow" and not type_counts.get("end", 0):
        errors.append("workflow mode must include at least one end node")
    if mode == "advanced-chat" and type_counts.get("end", 0):
        errors.append("advanced-chat mode must not use end nodes")
    if mode == "advanced-chat" and not type_counts.get("answer", 0):
        errors.append("advanced-chat mode must include at least one answer node")

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
        if mode != "agent-chat":
            if edge.get("type") != "custom":
                errors.append(f"edge {edge.get('id')} type must be custom for canvas rendering")
            for key in ("sourceHandle", "targetHandle", "zIndex"):
                if key not in edge:
                    errors.append(f"edge {edge.get('id')} missing canvas field {key}")
            edge_data = edge.get("data")
            if not isinstance(edge_data, dict):
                errors.append(f"edge {edge.get('id')} missing data mapping")
            else:
                for key in ("isInIteration", "isInLoop", "sourceType", "targetType"):
                    if key not in edge_data:
                        errors.append(f"edge {edge.get('id')} data missing {key}")

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
    if len(argv) != 2:
        print("usage: validate_studio_dsl.py <path-to-yml>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    errors, warnings = validate(path)
    result = {
        "path": str(path),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
