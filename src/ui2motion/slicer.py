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

    # Prefer exported component matching file stem, then exported component, then largest component
    selected_name, selected_node = max(
        components,
        key=lambda item: (
            item[0].lower() == path.stem.lower(),
            "export " in _node_text(item[1], source_bytes)[:30],
            item[1].end_byte - item[1].start_byte,
        ),
    )
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

    whole_file = len(source_code.splitlines()) <= 180
    return ComponentSlice(
        file_path=str(path),
        component_name=selected_name,
        start_line=1 if whole_file else selected_node.start_point[0] + 1,
        end_line=len(source_code.splitlines()) if whole_file else selected_node.end_point[0] + 1,
        imports=imports,
        prop_types=prop_types,
        helper_components=[] if whole_file else helper_components,
        component_code=source_code if whole_file else selected_code,
        full_file_code=source_code,
        is_whole_file=whole_file,
    )


def _extract_imported_symbols_by_source(import_stmts: list[str]) -> dict[str, set[str]]:
    """Map module specifier -> set of imported local/named identifiers."""
    by_source: dict[str, set[str]] = {}
    for stmt in import_stmts:
        src_match = re.search(r"""from\s+['"]([^'"]+)['"]""", stmt)
        if not src_match:
            continue
        mod = src_match.group(1)
        syms = by_source.setdefault(mod, set())
        named = re.search(r"\{([^}]*)\}", stmt)
        if named:
            for item in named.group(1).split(","):
                tok = item.strip()
                if not tok:
                    continue
                tok = re.sub(r"^type\s+", "", tok)
                local = tok.split(" as ")[-1].strip()
                if local:
                    syms.add(local)
        default_match = re.match(r"^import\s+(?:type\s+)?([A-Za-z0-9_$]+)\s*(?:,|from)", stmt.strip())
        if default_match:
            syms.add(default_match.group(1))
    return by_source


def _filter_duplicate_imports(existing_imports: list[str], candidate_imports: list[str]) -> list[str]:
    """Drop candidate imports whose symbols are already imported from the same module."""
    existing_map = _extract_imported_symbols_by_source(existing_imports)
    filtered: list[str] = []
    for stmt in candidate_imports:
        if stmt in existing_imports:
            continue
        src_match = re.search(r"""from\s+['"]([^'"]+)['"]""", stmt)
        if not src_match:
            filtered.append(stmt)
            continue
        mod = src_match.group(1)
        already = existing_map.get(mod, set())
        cand_map = _extract_imported_symbols_by_source([stmt]).get(mod, set())
        if cand_map and cand_map.issubset(already):
            continue
        # Strip individual duplicate named specifiers if partially overlapping
        named = re.search(r"\{([^}]*)\}", stmt)
        if named and already:
            kept_items = []
            for item in named.group(1).split(","):
                tok = item.strip()
                if not tok:
                    continue
                clean = re.sub(r"^type\s+", "", tok).split(" as ")[-1].strip()
                if clean not in already:
                    kept_items.append(tok)
                    already.add(clean)
            if not kept_items:
                continue
            stmt = re.sub(r"\{[^}]*\}", "{ " + ", ".join(kept_items) + " }", stmt, count=1)
        else:
            already.update(cand_map)
        filtered.append(stmt)
    return filtered


def _sanitize_motion_on_router_links(code: str) -> str:
    """Strip Framer Motion gesture/animation props if placed directly on react-router <Link>."""
    motion_props = r"(?:whileHover|whileTap|whileInView|initial|animate|exit|variants|viewport|transition)"
    def _clean_link_open_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        # Remove motion_prop={...} attributes from <Link ...>
        cleaned = re.sub(
            rf"\s+{motion_props}=\{{(?:[^{{}}]|\{{(?:[^{{}}]|\{{[^{{}}]*\}})*\}})*\}}",
            "",
            tag,
        )
        return cleaned

    return re.sub(r"<Link\b[^>]*>", _clean_link_open_tag, code, flags=re.DOTALL)


def _sanitize_motion_on_router_links(code: str) -> str:
    """Strip Framer Motion gesture/animation props if placed directly on react-router <Link>."""
    motion_props = r"(?:whileHover|whileTap|whileInView|initial|animate|exit|variants|viewport|transition)"
    def _clean_link_open_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        # Remove motion_prop={...} attributes from <Link ...>
        cleaned = re.sub(
            rf"\s+{motion_props}=\{{(?:[^{{}}]|\{{(?:[^{{}}]|\{{[^{{}}]*\}})*\}})*\}}",
            "",
            tag,
        )
        return cleaned

    return re.sub(r"<Link\b[^>]*>", _clean_link_open_tag, code, flags=re.DOTALL)


def splice_component_back(sliced: ComponentSlice, patched_tsx: str) -> str:
    """Merge patched component code and any newly added imports back into the full file."""
    patched_tsx = _sanitize_motion_on_router_links(patched_tsx)
    patched_tsx = _sanitize_motion_on_router_links(patched_tsx)
    if sliced.is_whole_file:
        return patched_tsx

    source_bytes = patched_tsx.encode("utf-8")
    parser = Parser(TSX_LANGUAGE)
    tree = parser.parse(source_bytes)

    new_imports: list[str] = []
    target_node: Node | None = None

    raw_candidate_imports: list[str] = []
    for child in tree.root_node.children:
        if child.type == "import_statement":
            raw_candidate_imports.append(_node_text(child, source_bytes))
        elif _extract_component_name(child, source_bytes) == sliced.component_name:
            target_node = child

    new_imports = _filter_duplicate_imports(sliced.imports, raw_candidate_imports)

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
