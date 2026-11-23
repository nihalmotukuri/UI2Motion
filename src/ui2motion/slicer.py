from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Node, Parser

TSX_LANGUAGE = Language(tstypescript.language_tsx())


@dataclass
class ComponentSlice:
    file_path: str
    component_name: str
    start_line: int
    end_line: int
    imports: list[str] = field(default_factory=list)
    prop_types: list[str] = field(default_factory=list)
    helper_components: list[str] = field(default_factory=list)
    component_code: str = ""
    full_file_code: str = ""
    is_whole_file: bool = False


def _node_text(node: Node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _extract_component_name(node: Node, source_bytes: bytes) -> str | None:
    """Return PascalCase component identifier if top-level node defines a React component."""
    target = node.child_by_field_name("declaration") if node.type == "export_statement" else node
    if target is None:
        return None

    if target.type == "function_declaration":
        name_node = target.child_by_field_name("name")
        if name_node:
            name = _node_text(name_node, source_bytes)
            if name and name[0].isupper():
                return name

    if target.type == "lexical_declaration":
        for child in target.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node and value_node and value_node.type in (
                    "arrow_function",
                    "function_expression",
                    "call_expression",
                ):
                    name = _node_text(name_node, source_bytes)
                    if name and name[0].isupper():
                        return name

    return None


def _is_type_declaration(node: Node) -> bool:
    target = node.child_by_field_name("declaration") if node.type == "export_statement" else node
    if target is None:
        return False
    return target.type in ("interface_declaration", "type_alias_declaration")


def slice_tsx_file(file_path: str | Path, component_name: str | None = None) -> ComponentSlice:
    """Parse a TSX/JSX file with Tree-sitter and isolate the target React component + types."""
    path = Path(file_path).expanduser().resolve()
    source_code = path.read_text(encoding="utf-8")
    source_bytes = source_code.encode("utf-8")

    parser = Parser(TSX_LANGUAGE)
    tree = parser.parse(source_bytes)
    root = tree.root_node

    imports: list[str] = []
    prop_types: list[str] = []
    components: list[tuple[str, Node]] = []

    for child in root.children:
        if child.type == "import_statement":
            imports.append(_node_text(child, source_bytes))
        elif _is_type_declaration(child):
            prop_types.append(_node_text(child, source_bytes))
        else:
            comp_name = _extract_component_name(child, source_bytes)
            if comp_name:
                components.append((comp_name, child))

    if not components:
        lines = source_code.splitlines()
        return ComponentSlice(
            file_path=str(path),
            component_name=path.stem,
            start_line=1,
            end_line=max(1, len(lines)),
            imports=imports,
            prop_types=prop_types,
            component_code=source_code,
            full_file_code=source_code,
            is_whole_file=True,
        )

    selected_name, selected_node = components[0]
    if component_name:
        for name, node in components:
            if name == component_name:
                selected_name, selected_node = name, node
                break
        else:
            available = ", ".join(n for n, _ in components)
            raise ValueError(
                f"Component '{component_name}' not found in {path.name}. Available: {available}"
            )

    selected_code = _node_text(selected_node, source_bytes)

    # Include any same-file helper components referenced via JSX (<HelperName ...)
    jsx_refs = set(re.findall(r"<([A-Z][A-Za-z0-9_]*)\b", selected_code))
    helper_components = [
        _node_text(node, source_bytes)
        for name, node in components
        if name != selected_name and name in jsx_refs
    ]

    return ComponentSlice(
        file_path=str(path),
        component_name=selected_name,
        start_line=selected_node.start_point[0] + 1,
        end_line=selected_node.end_point[0] + 1,
        imports=imports,
        prop_types=prop_types,
        helper_components=helper_components,
        component_code=selected_code,
        full_file_code=source_code,
        is_whole_file=(len(components) == 1 and len(source_code.splitlines()) <= 160),
    )


def splice_component_back(sliced: ComponentSlice, patched_tsx: str) -> str:
    """Merge patched component code and any newly added imports back into the full file."""
    if sliced.is_whole_file:
        return patched_tsx

    source_bytes = patched_tsx.encode("utf-8")
    parser = Parser(TSX_LANGUAGE)
    tree = parser.parse(source_bytes)

    new_imports: list[str] = []
    target_node: Node | None = None

    for child in tree.root_node.children:
        if child.type == "import_statement":
            imp_text = _node_text(child, source_bytes)
            if imp_text not in sliced.imports:
                new_imports.append(imp_text)
        elif _extract_component_name(child, source_bytes) == sliced.component_name:
            target_node = child

    if target_node is None:
        return patched_tsx

    updated_component = _node_text(target_node, source_bytes)
    lines = sliced.full_file_code.splitlines()

    # Replace target component lines (1-indexed inclusive)
    lines[sliced.start_line - 1 : sliced.end_line] = updated_component.splitlines()

    # Insert any newly added motion/GSAP imports right after the last existing import
    if new_imports:
        last_import_idx = 0
        for idx, line in enumerate(lines):
            if line.lstrip().startswith("import "):
                last_import_idx = idx + 1
        lines[last_import_idx:last_import_idx] = new_imports

    return "\n".join(lines) + ("\n" if sliced.full_file_code.endswith("\n") else "")
