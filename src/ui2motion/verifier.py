from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

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


def check_tsc_syntax(patched_tsx: str, tsc_bin: str | None = None) -> list[str]:
    """Run TypeScript compiler check on standalone TSX if tsc is available."""
    if not tsc_bin:
        return []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_file = Path(tmpdir) / "Component.tsx"
        tmp_file.write_text(patched_tsx, encoding="utf-8")
        proc = subprocess.run(
            [tsc_bin, "--noEmit", "--jsx", "react-jsx", "--target", "ES2022", str(tmp_file)],
            capture_output=True,
            text=True,
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
) -> VerificationResult:
    errors: list[str] = []
    errors.extend(check_contract_preservation(original_tsx, patched_tsx))
    errors.extend(check_motion_rules(patched_tsx, runtime))
    errors.extend(check_tsc_syntax(patched_tsx, tsc_bin=tsc_bin))
    return VerificationResult(passed=len(errors) == 0, errors=errors)
