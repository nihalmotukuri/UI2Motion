from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Literal

import httpx
import typer
from rich.console import Console
from rich.progress import track

from dataset.seeds import SEED_COMPONENTS
from ui2motion.client import SYSTEM_PROMPT, UI2MotionResponse
from ui2motion.verifier import verify_patch

app = typer.Typer(help="Generate quality-gated ChatML dataset for UI2Motion-8B.")
console = Console()

AESTHETIC_PROFILES: dict[str, dict] = {
    "dark-glass": {
        "css_variables": {
            "--background": "#0f111a",
            "--surface": "rgba(255, 255, 255, 0.03)",
            "--border": "rgba(255, 255, 255, 0.10)",
            "--accent": "#e3ff04",
            "--accent-secondary": "#602bf8",
            "--foreground": "#f8fafc",
            "--muted-foreground": "#94a3b8",
            "--radius": "0.875rem",
        },
        "surface_desc": "Layered translucent glass cards (bg-white/[0.03] backdrop-blur-md) with 1px inner rim highlight (ring-1 ring-white/10) and #e3ff04 accent highlights",
    },
    "neo-brutalist": {
        "css_variables": {
            "--background": "#fafaf9",
            "--surface": "#ffffff",
            "--border": "#09090b",
            "--accent": "#facc15",
            "--foreground": "#09090b",
            "--muted-foreground": "#52525b",
            "--radius": "0.25rem",
        },
        "surface_desc": "High-contrast crisp cards with 2px solid #09090b borders, hard offset drop shadows (shadow-[4px_4px_0px_#09090b]), and bold #facc15 accent badges",
    },
    "minimal-editorial": {
        "css_variables": {
            "--background": "#fcfcfc",
            "--surface": "#f4f4f5",
            "--border": "#e4e4e7",
            "--accent": "#18181b",
            "--foreground": "#09090b",
            "--muted-foreground": "#71717a",
            "--radius": "0.5rem",
        },
        "surface_desc": "Clean editorial surfaces with hairline 1px zinc borders, generous breathing room, and subtle tonal hover shifts",
    },
    "cyber-tactile": {
        "css_variables": {
            "--background": "#090d16",
            "--surface": "#111827",
            "--border": "#1f2937",
            "--accent": "#38bdf8",
            "--foreground": "#f1f5f9",
            "--muted-foreground": "#94a3b8",
            "--radius": "0.75rem",
        },
        "surface_desc": "Precision dark-slate panels with subtle cyan border luminance on hover and crisp tabular telemetry readouts",
    },
    "shadcn-v4-theme": {
        "css_variables": {
            "--color-background": "var(--background)",
            "--color-foreground": "var(--foreground)",
            "--color-card": "var(--card)",
            "--color-card-foreground": "var(--card-foreground)",
            "--color-primary": "var(--primary)",
            "--color-primary-foreground": "var(--primary-foreground)",
            "--color-muted": "var(--muted)",
            "--color-muted-foreground": "var(--muted-foreground)",
            "--color-accent": "var(--accent)",
            "--color-border": "var(--border)",
            "--radius-lg": "var(--radius)",
        },
        "surface_desc": "Semantic Tailwind v4 token surfaces (bg-[var(--color-card)] text-[var(--color-card-foreground)] border-[var(--color-border)]) with elevated hover contrast",
    },
}


def _call_teacher(
    teacher_url: str,
    teacher_model: str,
    messages: list[dict[str, str]],
    api_key: str | None = None,
) -> UI2MotionResponse | None:
    """Query either Ollama (/api/chat) or an OpenAI-compatible (/v1/chat/completions) endpoint."""
    base = teacher_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        if base.endswith("/v1") or api_key:
            url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
            resp = httpx.post(
                url,
                headers=headers,
                json={
                    "model": teacher_model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "temperature": 0.4,
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        else:
            resp = httpx.post(
                f"{base}/api/chat",
                headers=headers,
                json={
                    "model": teacher_model,
                    "messages": messages,
                    "format": UI2MotionResponse.model_json_schema(),
                    "stream": False,
                    "options": {"num_ctx": 4096, "temperature": 0.4},
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]

        return UI2MotionResponse.model_validate_json(content)
    except Exception:
        return None


def _distill_with_verification(
    seed: dict[str, str],
    user_prompt: str,
    runtime: str,
    teacher_url: str,
    teacher_model: str,
    api_key: str | None = None,
    max_retries: int = 2,
) -> UI2MotionResponse | None:
    """Generate from teacher and feed verifier errors back if a rule is violated."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    for _ in range(max_retries + 1):
        candidate = _call_teacher(teacher_url, teacher_model, messages, api_key=api_key)
        if candidate is None:
            continue

        verdict = verify_patch(seed["source"], candidate.patched_tsx, runtime=runtime)
        if verdict.passed:
            return candidate

        messages.append({"role": "assistant", "content": candidate.model_dump_json()})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Your previous output failed deterministic verification:\n"
                    + "\n".join(f"- {e}" for e in verdict.errors)
                    + "\nFix every listed issue while preserving all exported components and prop interfaces."
                ),
            }
        )

    return None


@app.command()
def build(
    out: Path = typer.Option(Path("dataset/train.jsonl"), "--out", "-o", help="Output JSONL path"),
    count: int = typer.Option(500, "--count", "-n", help="Target number of verified samples"),
    teacher_url: str = typer.Option(
        "http://localhost:11434",
        "--teacher-url",
        help="Ollama URL (http://localhost:11434) or OpenAI-compatible base URL (https://.../v1)",
    ),
    teacher_model: str = typer.Option(
        "qwen2.5-coder:7b",
        "--teacher-model",
        help="Teacher model ID for distilling high-craft TSX upgrades",
    ),
    api_key_env: str = typer.Option(
        "TEACHER_API_KEY",
        "--api-key-env",
        help="Environment variable holding API key if using a hosted OpenAI-compatible teacher",
    ),
) -> None:
    """Distill and quality-gate ChatML training examples for UI2Motion-8B."""
    out.parent.mkdir(parents=True, exist_ok=True)
    api_key = os.getenv(api_key_env)

    runtimes: list[Literal["framer-motion", "gsap", "css-only"]] = ["framer-motion", "gsap", "css-only"]
    modes: list[Literal["full_upgrade", "style_only", "motion_only"]] = ["full_upgrade", "style_only", "motion_only"]
    profile_names = list(AESTHETIC_PROFILES.keys())

    accepted = 0
    rejected = 0

    with out.open("a", encoding="utf-8") as f:
        for _ in track(range(count), description="Distilling & verifying dataset..."):
            seed = random.choice(SEED_COMPONENTS)
            profile_name = random.choice(profile_names)
            runtime = random.choice(runtimes)
            mode = random.choice(modes)
            profile = AESTHETIC_PROFILES[profile_name]

            installed = (
                ["motion", "lucide-react", "tailwindcss"]
                if runtime == "framer-motion"
                else (["gsap", "@gsap/react", "tailwindcss"] if runtime == "gsap" else ["tailwindcss"])
            )

            user_payload = {
                "mode": mode,
                "repo_context": {
                    "aesthetic_profile": profile_name,
                    "motion_runtime": runtime,
                    "installed_packages": installed,
                    "css_variables": profile["css_variables"],
                    "tailwind_tokens": {},
                },
                "target_component": {
                    "file_path": seed["file"],
                    "component_name": seed["name"],
                    "is_whole_file": True,
                    "source_tsx": seed["source"],
                },
                "intent": seed["intent"],
            }
            user_prompt = (
                "Compile the visual and motion upgrade for this React/TypeScript component.\n"
                "Respond with a single JSON object containing `visual_plan`, `motion_plan`, and `patched_tsx`.\n\n"
                + json.dumps(user_payload, indent=2)
            )

            candidate = _distill_with_verification(
                seed=seed,
                user_prompt=user_prompt,
                runtime=runtime,
                teacher_url=teacher_url,
                teacher_model=teacher_model,
                api_key=api_key,
            )

            if candidate is None:
                rejected += 1
                continue

            row = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": candidate.model_dump_json()},
                ]
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            accepted += 1

    console.print(f"[bold green]✓ Appended {accepted} verified rows[/bold green] to {out} (rejected: {rejected})")


if __name__ == "__main__":
    app()
