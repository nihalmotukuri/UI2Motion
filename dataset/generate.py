from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Literal

# Ensure repo root is on sys.path whether invoked as `python dataset/generate.py` or `python -m dataset.generate`
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx
import typer
from rich.console import Console
from rich.progress import track

from dataset.seeds import SEED_COMPONENTS
from ui2motion.client import SYSTEM_PROMPT, UI2MotionResponse
from ui2motion.verifier import verify_patch

app = typer.Typer(help="Generate quality-gated ChatML dataset for UI2Motion-7B.")
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
    },
}


def _load_all_seeds(harvested_path: Path) -> list[dict]:
    seeds: list[dict] = list(SEED_COMPONENTS)
    if harvested_path.exists():
        try:
            harvested = json.loads(harvested_path.read_text(encoding="utf-8"))
            if isinstance(harvested, list):
                seeds.extend(harvested)
        except Exception:
            pass
    return seeds


def _call_teacher(
    teacher_url: str,
    teacher_model: str,
    messages: list[dict[str, str]],
    api_key: str | None = None,
) -> UI2MotionResponse | None:
    """Query an OpenAI-compatible or local Ollama endpoint with automatic 429 rate-limit backoff."""
    base = teacher_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    is_local_ollama = ("localhost" in base or "127.0.0.1" in base) and "/v1" not in base
    is_openai_compat = (not is_local_ollama) and (
        any(token in base for token in ("/v1", "/openai", "groq.com", "openrouter.ai", "googleapis.com"))
        or bool(api_key)
    )

    for attempt in range(4):
        try:
            if is_openai_compat:
                url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
                payload: dict = {
                    "model": teacher_model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 4096,
                    "temperature": 0.4,
                }
                if "gpt-oss" in teacher_model:
                    payload["reasoning_effort"] = "low"
                resp = httpx.post(url, headers=headers, json=payload, timeout=120.0)
            else:
                resp = httpx.post(
                    f"{base}/api/chat",
                    headers=headers,
                    json={
                        "model": teacher_model,
                        "messages": messages,
                        "format": UI2MotionResponse.model_json_schema(),
                        "stream": False,
                        "options": {"num_ctx": 8192, "temperature": 0.4},
                    },
                    timeout=300.0,
                )

            if resp.status_code in (429, 503):
                wait_s = float(resp.headers.get("retry-after", 8 * (attempt + 1)))
                console.print(f"[dim yellow]HTTP {resp.status_code} — backing off {wait_s:.0f}s...[/dim yellow]")
                time.sleep(min(wait_s, 60.0))
                continue

            if resp.status_code >= 400:
                console.print(f"[dim red]HTTP {resp.status_code}: {resp.text[:300]}[/dim red]")
            if resp.status_code >= 400:
                console.print(f"[dim red]HTTP {resp.status_code}: {resp.text[:300]}[/dim red]")
            resp.raise_for_status()
            data = resp.json()
            content = (
                data["choices"][0]["message"]["content"]
                if is_openai_compat
                else data["message"]["content"]
            )
            return UI2MotionResponse.model_validate_json(content)
        except Exception as exc:
            console.print(f"[dim red]Teacher call error (attempt {attempt + 1}): {exc}[/dim red]")
            time.sleep(2.0 * (attempt + 1))
    return None


def _distill_with_verification(
    seed: dict,
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

        if candidate.patched_tsx.strip() == seed["source"].strip():
            messages.append({"role": "assistant", "content": candidate.model_dump_json()})
            messages.append(
                {
                    "role": "user",
                    "content": "Your previous output left `patched_tsx` completely unchanged. Apply meaningful visual hierarchy and motion upgrades according to the prompt.",
                }
            )
            continue

        if candidate.patched_tsx.strip() == seed["source"].strip():
            messages.append({"role": "assistant", "content": candidate.model_dump_json()})
            messages.append(
                {
                    "role": "user",
                    "content": "Your previous output left `patched_tsx` completely unchanged. Apply meaningful visual hierarchy and motion upgrades according to the prompt.",
                }
            )
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
    harvested: Path = typer.Option(Path("dataset/harvested_seeds.json"), "--harvested", help="Harvested repo seeds JSON"),
    count: int = typer.Option(250, "--count", "-n", help="Number of verified samples to append"),
    teacher_url: str = typer.Option(
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "--teacher-url",
        help="Free-tier OpenAI-compatible base URL or local Ollama URL",
    ),
    teacher_model: str = typer.Option(
        "gemini-3.5-flash-lite",
        "--teacher-model",
        help="Teacher model ID",
    ),
    api_key_env: str = typer.Option(
        "TEACHER_API_KEY",
        "--api-key-env",
        help="Environment variable holding API key",
    ),
    delay: float = typer.Option(4.5, "--delay", help="Seconds to pause between samples for free-tier limits"),
) -> None:
    """Distill and quality-gate ChatML training examples for UI2Motion-7B."""
    out.parent.mkdir(parents=True, exist_ok=True)
    api_key = os.getenv(api_key_env)
    if not api_key and "localhost" not in teacher_url:
        console.print(f"[bold red]Missing {api_key_env} environment variable.[/bold red]")
        raise typer.Exit(code=1)

    all_seeds = _load_all_seeds(harvested)
    console.print(f"[cyan]Loaded {len(all_seeds)} seed components ({len(SEED_COMPONENTS)} built-in + {len(all_seeds) - len(SEED_COMPONENTS)} harvested)[/cyan]")

    runtimes: list[Literal["framer-motion", "gsap", "css-only"]] = ["framer-motion", "gsap", "css-only"]
    modes: list[Literal["full_upgrade", "style_only", "motion_only"]] = ["full_upgrade", "style_only", "motion_only"]
    profile_names = list(AESTHETIC_PROFILES.keys())

    accepted = 0
    rejected = 0

    with out.open("a", encoding="utf-8") as f:
        for _ in track(range(count), description="Distilling & verifying dataset..."):
            seed = random.choice(all_seeds)
            profile_name = random.choice(profile_names)
            runtime = random.choice(runtimes)
            mode = random.choice(modes)
            profile = AESTHETIC_PROFILES[profile_name]

            installed = (
                ["motion", "lucide-react", "tailwindcss"]
                if runtime == "framer-motion"
                else (["gsap", "@gsap/react", "tailwindcss"] if runtime == "gsap" else ["tailwindcss"])
            )

            repo_ctx = {
                "aesthetic_profile": profile_name,
                "motion_runtime": runtime,
                "installed_packages": installed,
                "css_variables": profile["css_variables"],
                "tailwind_tokens": seed.get("repo_context", {}).get("tailwind_tokens", {}),
            }

            user_payload = {
                "mode": mode,
                "repo_context": repo_ctx,
                "target_component": {
                    "file_path": seed["file"],
                    "component_name": seed["name"],
                    "is_whole_file": seed.get("is_whole_file", True),
                    "imports": seed.get("imports", []),
                    "prop_types": seed.get("prop_types", []),
                    "helper_components": seed.get("helper_components", []),
                    "source_tsx": seed["source"],
                },
                "intent": seed["intent"],
            }
            user_prompt = (
                "Compile the visual and motion upgrade for this React/TypeScript component.\n"
                "Respond with a single JSON object matching this exact schema:\n"
                "{\n"
                '  "visual_plan": {"surface_hierarchy": "...", "typography_rhythm": "...", "interaction_states": "..."},\n'
                '  "motion_plan": {"runtime": "framer-motion|gsap|css-only", "trigger": "...", "physics": "...", "stagger_ms": 50, "gpu_properties": ["opacity", "transform"], "a11y_fallback": "..."},\n'
                '  "patched_tsx": "complete valid TSX string"\n'
                "}\n\n"
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
            else:
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

            if delay > 0:
                time.sleep(delay)

    console.print(f"[bold green]✓ Appended {accepted} verified rows[/bold green] to {out} (rejected: {rejected})")


if __name__ == "__main__":
    app()
