from __future__ import annotations

import re
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Node, Parser

TSX_LANGUAGE = Language(tstypescript.language_tsx())

FORBIDDEN_ANIMATED_PROPS = (
    "width",
    "height",
    "top",
    "left",
    "right",
    "bottom",
    "margin",
    "padding",
)


@dataclass
class VerificationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_motion_rules(tsx_code: str, runtime: str) -> list[str]:
    """Enforce GPU-composited animations, lifecycle cleanup, and reduced-motion guards."""
    errors: list[str] = []

    prop_pattern = re.compile(
        r"""(?:animate|initial|exit|whileHover|whileTap|to|from|fromTo)\s*[:(]\s*\{[^}]*\b("""
        + "|".join(FORBIDDEN_ANIMATED_PROPS)
        + r""")\s*:""",
        re.DOTALL,
    )
    for match in prop_pattern.finditer(tsx_code):
        errors.append(
            f"Layout-thrashing animation property detected: '{match.group(1)}'. "
            "Use GPU-composited transform (x, y, scale, rotate) or opacity instead."
        )

    if runtime == "gsap" and "gsap." in tsx_code:
        if "useGSAP" not in tsx_code and "gsap.context" not in tsx_code:
            errors.append(
                "GSAP animations must be wrapped in useGSAP() or gsap.context() with ctx.revert() cleanup."
            )

    if runtime in ("framer-motion", "gsap"):
        has_a11y_guard = any(
            token in tsx_code
            for token in (
                "useReducedMotion",
                "prefers-reduced-motion",
                "matchMedia",
                "MotionConfig",
            )
        )
        if not has_a11y_guard:
            errors.append(
                "Missing reduced-motion accessibility guard (useReducedMotion / gsap.matchMedia / prefers-reduced-motion)."
            )

    return errors


def check_contract_preservation(original_tsx: str, patched_tsx: str) -> list[str]:
    """Ensure exported component signatures and prop interfaces remain intact."""
    errors: list[str] = []

    export_pattern = re.compile(
        r"export\s+(?:default\s+)?(?:function|const)\s+([A-Z][A-Za-z0-9_]*)"
    )
    original_exports = set(export_pattern.findall(original_tsx))
    patched_exports = set(export_pattern.findall(patched_tsx))

    missing_exports = original_exports - patched_exports
    if missing_exports:
        errors.append(f"Removed exported component(s): {', '.join(sorted(missing_exports))}")

    interface_pattern = re.compile(r"(?:interface|type)\s+([A-Z][A-Za-z0-9_]*Props)\b")
    original_props = set(interface_pattern.findall(original_tsx))
    patched_props = set(interface_pattern.findall(patched_tsx))

    missing_props = original_props - patched_props
    if missing_props:
        errors.append(f"Removed Props type definition(s): {', '.join(sorted(missing_props))}")

    return errors


def _collect_jsx_texts(tsx_code: str) -> Counter[str]:
    """Extract normalized non-empty JSX text literals using Tree-sitter."""
    source_bytes = tsx_code.encode("utf-8")
    tree = Parser(TSX_LANGUAGE).parse(source_bytes)
    counts: Counter[str] = Counter()

    def _walk(node: Node) -> None:
        if node.type == "jsx_text":
            txt = " ".join(
                source_bytes[node.start_byte : node.end_byte]
                .decode("utf-8", errors="replace")
                .split()
            )
            if len(txt) >= 3:
                counts[txt] += 1
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return counts


def check_jsx_structure_preservation(original_tsx: str, patched_tsx: str) -> list[str]:
    """Ensure JSX text nodes were neither dropped nor duplicated during upgrade."""
    errors: list[str] = []
    orig_texts = _collect_jsx_texts(original_tsx)
    patched_texts = _collect_jsx_texts(patched_tsx)

    dropped = [txt for txt, cnt in orig_texts.items() if patched_texts[txt] < cnt]
    duplicated = [txt for txt, cnt in patched_texts.items() if cnt > orig_texts[txt]]

    if dropped:
        sample = ", ".join(f"'{t}'" for t in dropped[:4])
        errors.append(f"JSX text/elements were removed during upgrade: {sample}. Preserve all existing copy.")
    if duplicated:
        sample = ", ".join(f"'{t}'" for t in duplicated[:4])
        errors.append(f"JSX text/subtree was duplicated during upgrade: {sample}. Do not duplicate existing sections.")

    return errors


def check_tsc_syntax(patched_tsx: str, tsc_bin: str | None = None, project_root: str | None = None) -> list[str]:
    """Run TypeScript compiler check on standalone TSX if tsc is available."""
    if not tsc_bin:
        return []

    tmp_dir_ctx = tempfile.TemporaryDirectory(dir=project_root) if project_root else tempfile.TemporaryDirectory()
    with tmp_dir_ctx as tmpdir:
        tmp_file = Path(tmpdir) / "Component.tsx"
        tmp_file.write_text(patched_tsx, encoding="utf-8")
        proc = subprocess.run(
            [tsc_bin, "--noEmit", "--jsx", "react-jsx", "--target", "ES2022", "--moduleResolution", "bundler", str(tmp_file)],
            capture_output=True,
            text=True,
            cwd=project_root or None,
            timeout=15,
        )
        if proc.returncode != 0:
            real_errors = [
                line.strip()
                for line in proc.stdout.splitlines()
                if "TS2307" not in line and line.strip()
            ]
            return real_errors[:5]
    return []


def verify_patch(
    original_tsx: str,
    patched_tsx: str,
    runtime: str,
    tsc_bin: str | None = None,
    project_root: str | None = None,
) -> VerificationResult:
    errors: list[str] = []
    errors.extend(check_contract_preservation(original_tsx, patched_tsx))
    errors.extend(check_jsx_structure_preservation(original_tsx, patched_tsx))
    errors.extend(check_motion_rules(patched_tsx, runtime))
    errors.extend(check_tsc_syntax(patched_tsx, tsc_bin=tsc_bin, project_root=project_root))
    return VerificationResult(passed=len(errors) == 0, errors=errors)
