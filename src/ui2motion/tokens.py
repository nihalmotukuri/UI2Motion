from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

FRONTEND_SUBDIRS = ("", "client", "frontend", "web", "app", "apps/web", "packages/ui")


@dataclass
class RepoDesignContext:
    repo_root: str
    frontend_root: str
    motion_runtime: str  # "framer-motion" | "gsap" | "css-only"
    installed_packages: list[str] = field(default_factory=list)
    css_variables: dict[str, str] = field(default_factory=dict)
    tailwind_tokens: dict[str, list[str]] = field(default_factory=dict)
    tsc_bin: str | None = None

    def to_prompt_dict(self) -> dict:
        return {
            "frontend_root": self.frontend_root,
            "motion_runtime": self.motion_runtime,
            "installed_packages": self.installed_packages,
            "css_variables": self.css_variables,
            "tailwind_tokens": self.tailwind_tokens,
        }


def _resolve_frontend_root(repo_path: Path) -> Path:
    """Locate the package.json that owns React/Next/Vite frontend dependencies."""
    for sub in FRONTEND_SUBDIRS:
        candidate = (repo_path / sub).resolve() if sub else repo_path
        pkg_file = candidate / "package.json"
        if not pkg_file.exists():
            continue
        try:
            data = json.loads(pkg_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        if any(k in deps for k in ("react", "next", "vite", "tailwindcss")):
            return candidate
    return repo_path


def _detect_stack(frontend_path: Path) -> tuple[str, list[str]]:
    """Inspect package.json to determine the installed animation runtime and UI utilities."""
    pkg_file = frontend_path / "package.json"
    if not pkg_file.exists():
        return "css-only", []

    try:
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "css-only", []

    deps: dict[str, str] = {}
    deps.update(data.get("dependencies", {}))
    deps.update(data.get("devDependencies", {}))

    tracked = [
        pkg
        for pkg in (
            "framer-motion",
            "motion",
            "gsap",
            "@gsap/react",
            "lucide-react",
            "tailwindcss",
            "clsx",
            "tailwind-merge",
        )
        if pkg in deps
    ]

    if "framer-motion" in deps or "motion" in deps:
        runtime = "framer-motion"
    elif "gsap" in deps:
        runtime = "gsap"
    else:
        runtime = "css-only"

    return runtime, tracked


def _extract_css_variables(frontend_path: Path) -> dict[str, str]:
    """Scan CSS files for :root / @theme CSS custom properties."""
    var_pattern = re.compile(r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;}{]+);")
    variables: dict[str, str] = {}

    css_files = [
        p
        for p in frontend_path.rglob("*.css")
        if "node_modules" not in p.parts and ".next" not in p.parts and "dist" not in p.parts
    ]

    for css_file in sorted(css_files):
        content = css_file.read_text(encoding="utf-8", errors="ignore")
        for match in var_pattern.finditer(content):
            name, value = match.group(1).strip(), match.group(2).strip()
            if len(variables) < 40:
                variables[name] = value

    return variables


def _extract_tailwind_tokens(frontend_path: Path) -> dict[str, list[str]]:
    """Extract custom color/font/radius keys from tailwind.config.(ts|js|mjs)."""
    tokens: dict[str, list[str]] = {}
    for ext in ("ts", "js", "mjs", "cjs"):
        cfg = frontend_path / f"tailwind.config.{ext}"
        if not cfg.exists():
            continue
        text = cfg.read_text(encoding="utf-8", errors="ignore")
        for section in ("colors", "fontFamily", "borderRadius", "boxShadow"):
            block_match = re.search(rf"\b{section}\s*:\s*\{{([^}}]+)\}}", text, re.DOTALL)
            if block_match:
                keys = re.findall(r"""['"]?([a-zA-Z0-9_-]+)['"]?\s*:""", block_match.group(1))
                if keys:
                    tokens[section] = list(dict.fromkeys(keys))[:20]
        break
    return tokens


def _find_local_tsc(repo_path: Path, frontend_path: Path) -> str | None:
    for base in (frontend_path, repo_path):
        local_tsc = base / "node_modules" / ".bin" / "tsc"
        if local_tsc.exists():
            return str(local_tsc)
    return None


def extract_repo_context(repo_root: str | Path) -> RepoDesignContext:
    """Build complete design token & runtime context for a target React/Next.js repository."""
    repo_path = Path(repo_root).expanduser().resolve()
    frontend_path = _resolve_frontend_root(repo_path)
    runtime, installed = _detect_stack(frontend_path)
    css_vars = _extract_css_variables(frontend_path)
    tw_tokens = _extract_tailwind_tokens(frontend_path)
    tsc_bin = _find_local_tsc(repo_path, frontend_path)

    return RepoDesignContext(
        repo_root=str(repo_path),
        frontend_root=str(frontend_path),
        motion_runtime=runtime,
        installed_packages=installed,
        css_variables=css_vars,
        tailwind_tokens=tw_tokens,
        tsc_bin=tsc_bin,
    )
