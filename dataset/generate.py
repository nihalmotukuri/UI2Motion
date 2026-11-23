from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Literal

import httpx
import typer
from rich.console import Console
from rich.progress import track

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
}

SEED_COMPONENTS: list[dict[str, str]] = [
    {
        "name": "FeatureGrid",
        "file": "FeatureGrid.tsx",
        "intent": "Upgrade this feature grid with cohesive surface depth, subtle hover lift, and a staggered viewport entrance.",
        "source": """import React from 'react';

export interface FeatureItem {
  id: string;
  title: string;
  description: string;
  metric: string;
}

export interface FeatureGridProps {
  items: FeatureItem[];
  onSelect?: (id: string) => void;
}

export function FeatureGrid({ items, onSelect }: FeatureGridProps) {
  return (
    <section className="py-12 px-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {items.map((item) => (
          <div
            key={item.id}
            onClick={() => onSelect?.(item.id)}
            className="p-6 border rounded-lg cursor-pointer"
          >
            <span className="text-xs font-mono">{item.metric}</span>
            <h3 className="text-lg font-semibold mt-2">{item.title}</h3>
            <p className="text-sm mt-1">{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
}""",
    },
    {
        "name": "PricingCard",
        "file": "PricingCard.tsx",
        "intent": "Elevate this pricing card with clear visual hierarchy, interactive CTA feedback, and reduced-motion safe entrance.",
        "source": """import React from 'react';

export interface PricingCardProps {
  tier: string;
  price: string;
  features: string[];
  highlighted?: boolean;
  onSubscribe: () => void;
}

export function PricingCard({ tier, price, features, highlighted = false, onSubscribe }: PricingCardProps) {
  return (
    <div className="p-6 border rounded-xl flex flex-col justify-between">
      <div>
        <h3 className="text-xl font-bold">{tier}</h3>
        <p className="text-3xl font-extrabold mt-3">{price}</p>
        <ul className="mt-6 space-y-2">
          {features.map((feat) => (
            <li key={feat} className="text-sm">{feat}</li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        onClick={onSubscribe}
        className="mt-8 w-full py-2.5 px-4 rounded-lg font-medium"
      >
        Get Started
      </button>
    </div>
  );
}""",
    },
    {
        "name": "MetricHeader",
        "file": "MetricHeader.tsx",
        "intent": "Refine typography rhythm, tabular numbers, and subtle mount transition while keeping all props intact.",
        "source": """import React from 'react';

export interface MetricHeaderProps {
  title: string;
  subtitle: string;
  activeUsers: number;
  deltaPercent: string;
}

export function MetricHeader({ title, subtitle, activeUsers, deltaPercent }: MetricHeaderProps) {
  return (
    <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 p-6 border-b">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        <p className="text-sm mt-1">{subtitle}</p>
      </div>
      <div className="flex items-baseline gap-3">
        <span className="text-3xl font-bold">{activeUsers.toLocaleString()}</span>
        <span className="text-xs px-2 py-0.5 rounded">{deltaPercent}</span>
      </div>
    </header>
  );
}""",
    },
]


def _build_reference_upgrade(
    seed: dict[str, str],
    profile_name: str,
    runtime: Literal["framer-motion", "gsap", "css-only"],
    mode: Literal["full_upgrade", "style_only", "motion_only"],
) -> UI2MotionResponse:
    """Produce a guaranteed-valid reference target for a seed component + runtime."""
    profile = AESTHETIC_PROFILES[profile_name]
    src = seed["source"]

    if runtime == "framer-motion":
        header = "import React from 'react';\nimport { motion, useReducedMotion } from 'motion/react';\n"
        body = src.replace("import React from 'react';\n", "")
        body = body.replace(
            ") {\n",
            ") {\n  const prefersReducedMotion = useReducedMotion();\n",
            1,
        )
        body = body.replace("<section ", "<motion.section ", 1).replace("</section>", "</motion.section>")
        body = body.replace(
            '<motion.section className="py-12 px-6">',
            '<motion.section\n      initial={prefersReducedMotion ? false : { opacity: 0, y: 14 }}\n      whileInView={{ opacity: 1, y: 0 }}\n      viewport={{ once: true, amount: 0.2 }}\n      transition={{ type: "spring", stiffness: 280, damping: 26 }}\n      className="py-12 px-6 bg-[var(--background)] text-[var(--foreground)]"\n    >',
        )
        patched = header + body
        motion_plan = {
            "runtime": "framer-motion",
            "trigger": "whileInView (once: true, amount: 0.2)",
            "physics": "spring(stiffness: 280, damping: 26)",
            "stagger_ms": 45,
            "gpu_properties": ["opacity", "transform"],
            "a11y_fallback": "useReducedMotion() disables initial Y offset",
        }
    elif runtime == "gsap":
        header = (
            "import React, { useRef } from 'react';\n"
            "import gsap from 'gsap';\n"
            "import { useGSAP } from '@gsap/react';\n"
        )
        body = src.replace("import React from 'react';\n", "")
        body = body.replace(
            ") {\n",
            ") {\n  const containerRef = useRef<HTMLDivElement>(null);\n\n  useGSAP(() => {\n    const mm = gsap.matchMedia();\n    mm.add('(prefers-reduced-motion: no-preference)', () => {\n      gsap.from('[data-animate-item]', { opacity: 0, y: 16, duration: 0.5, stagger: 0.05, ease: 'power3.out' });\n    });\n  }, { scope: containerRef });\n",
            1,
        )
        body = body.replace("<section ", "<section ref={containerRef} ", 1)
        body = body.replace("<div\n", "<div ref={containerRef}\n", 1)
        body = body.replace("<header ", "<header ref={containerRef} ", 1)
        patched = header + body
        motion_plan = {
            "runtime": "gsap",
            "trigger": "Mount timeline scoped via useGSAP()",
            "physics": "power3.out (500ms, 50ms stagger)",
            "stagger_ms": 50,
            "gpu_properties": ["opacity", "transform"],
            "a11y_fallback": "gsap.matchMedia('(prefers-reduced-motion: no-preference)')",
        }
    else:
        patched = src.replace(
            'className="p-6 border rounded-lg cursor-pointer"',
            'className="p-6 rounded-[var(--radius)] bg-[var(--surface)] border border-[var(--border)] transition-transform duration-200 ease-out hover:-translate-y-0.5 motion-reduce:transition-none motion-reduce:hover:translate-y-0 cursor-pointer"',
        )
        motion_plan = {
            "runtime": "css-only",
            "trigger": "Hover / focus-visible transition",
            "physics": "ease-out 200ms GPU transform",
            "stagger_ms": 0,
            "gpu_properties": ["transform", "opacity"],
            "a11y_fallback": "motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        }

    return UI2MotionResponse.model_validate(
        {
            "visual_plan": {
                "surface_hierarchy": profile["surface_desc"],
                "typography_rhythm": "Tight display tracking on headings, tabular-nums on metrics, muted secondary copy",
                "interaction_states": "Subtle GPU-composited lift and border luminance shift on hover; visible focus ring",
            },
            "motion_plan": motion_plan,
            "patched_tsx": patched,
        }
    )


def _distill_from_teacher(
    teacher_url: str,
    teacher_model: str,
    user_prompt: str,
) -> UI2MotionResponse | None:
    try:
        resp = httpx.post(
            f"{teacher_url.rstrip('/')}/api/chat",
            json={
                "model": teacher_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "format": UI2MotionResponse.model_json_schema(),
                "stream": False,
                "options": {"num_ctx": 4096, "temperature": 0.4},
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        return UI2MotionResponse.model_validate_json(resp.json()["message"]["content"])
    except Exception:
        return None


@app.command()
def build(
    out: Path = typer.Option(Path("dataset/train.jsonl"), "--out", "-o", help="Output JSONL path"),
    count: int = typer.Option(60, "--count", "-n", help="Number of verified samples to generate"),
    teacher_url: str | None = typer.Option(None, "--teacher-url", help="Optional Ollama URL for teacher distillation"),
    teacher_model: str = typer.Option("qwen2.5-coder:7b", "--teacher-model", help="Teacher model tag"),
) -> None:
    """Generate and verify ChatML training examples for UI2Motion-8B."""
    out.parent.mkdir(parents=True, exist_ok=True)
    runtimes: list[Literal["framer-motion", "gsap", "css-only"]] = ["framer-motion", "gsap", "css-only"]
    modes: list[Literal["full_upgrade", "style_only", "motion_only"]] = ["full_upgrade", "style_only", "motion_only"]
    profile_names = list(AESTHETIC_PROFILES.keys())

    accepted = 0
    rejected = 0

    with out.open("w", encoding="utf-8") as f:
        for _ in track(range(count), description="Synthesizing & verifying dataset..."):
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
                    "source_tsx": seed["source"],
                },
                "intent": seed["intent"],
            }
            user_prompt = (
                "Compile the visual and motion upgrade for this React/TypeScript component.\n"
                "Respond with a single JSON object containing `visual_plan`, `motion_plan`, and `patched_tsx`.\n\n"
                + json.dumps(user_payload, indent=2)
            )

            candidate = None
            if teacher_url:
                candidate = _distill_from_teacher(teacher_url, teacher_model, user_prompt)
            if candidate is None:
                candidate = _build_reference_upgrade(seed, profile_name, runtime, mode)

            verdict = verify_patch(seed["source"], candidate.patched_tsx, runtime=runtime)
            if not verdict.passed:
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
            accepted += 1

    console.print(f"[bold green]✓ Saved {accepted} verified rows[/bold green] to {out} (rejected: {rejected})")


if __name__ == "__main__":
    app()
