from __future__ import annotations

import json
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from ui2motion.slicer import ComponentSlice
from ui2motion.tokens import RepoDesignContext

SYSTEM_PROMPT = """You are UI2Motion-7B, a token-grounded UI visual profile and motion choreography compiler for React and TypeScript applications.

Given a target TSX component, its existing imports/prop types, repository design tokens, installed motion runtime, and user intent:
1. Preserve all exported component names, TypeScript prop interfaces, local constants/variants objects (e.g. `valueItemVariants`), state hooks, data bindings, and event handlers. NEVER attach Framer Motion props (`whileHover`, `whileTap`, `initial`, `animate`, `variants`) directly to third-party components like `<Link>`—wrap `<Link>` inside a `<motion.span>` or `<motion.div>` instead.
2. Ground all styling in the repository's existing CSS variables, Tailwind tokens, and aesthetic profile.
3. Use ONLY the detected motion runtime ("framer-motion", "gsap", or "css-only"). Note: if "motion" is in installed_packages instead of "framer-motion", import from "motion/react". For Framer Motion, NEVER pass react-spring config objects (`{ from, to, config }`) to `useSpring(source, { stiffness, damping, mass })`, and always preserve existing `useScroll`, `useTransform`, `useSpring`, and `AnimatePresence` hooks verbatim (never pass a `RefObject` like `previewRef` to `useTransform`—its first argument must be a `MotionValue` like `scrollYProgress`) while layering new motion onto un-animated JSX elements.
4. Choreograph multi-layered, purposeful motion across the full component hierarchy—never settle for a single trivial fade-in when upgrading a section or page:
   - Hero & above-the-fold focal elements: orchestrate staggered parent/child `variants` (`staggerChildren` / `delayChildren`) combining directional `y`/`x` translation, subtle `scale` settle (`0.96 -> 1`), and opacity.
   - Below-the-fold sections, cards, and feature lists: add scroll-triggered `whileInView` reveals (`viewport={{ once: true, amount: 0.2 }}`) with staggered sibling entrances so content reveals progressively as the user scrolls.
   - Interactive cards, buttons, and pills: add tactile spring `whileHover` (e.g. `y: -3, scale: 1.015`) and `whileTap` (`scale: 0.98`) micro-interactions, and wrap conditional UI toggles/modals in `AnimatePresence`.
   - When the user asks for advanced or expressive motion, also leverage scroll-linked parallax/progress (`useScroll` + `useTransform`) or shared-element transitions (`layoutId`) where structurally appropriate.
5. Animate ONLY GPU-composited properties (transform: x, y, scale, rotate; opacity). Never animate width, height, top, left, margin, or padding.
6. For GSAP, wrap animations in useGSAP() or gsap.context() with ctx.revert() cleanup and ScrollTrigger for viewport reveals.
7. Always include a reduced-motion accessibility fallback (useReducedMotion, gsap.matchMedia, or prefers-reduced-motion) that bypasses non-essential motion cleanly.
8. Return strictly valid JSON matching the required schema with complete, compilable TSX in `patched_tsx`."""


class VisualPlan(BaseModel):
    surface_hierarchy: str = Field(description="Surface layering, borders, blur, and elevation strategy")
    typography_rhythm: str = Field(description="Type scale, tracking, contrast, and numeric alignment")
    interaction_states: str = Field(description="Hover, active, and focus-visible micro-interactions")


class MotionPlan(BaseModel):
    runtime: Literal["framer-motion", "gsap", "css-only"]
    trigger: str = Field(description="Mount, hover, or viewport trigger configuration")
    physics: str = Field(description="Spring constants or cubic-bezier easing parameters")
    stagger_ms: int = Field(default=0, description="Stagger delay between sibling elements in ms")
    gpu_properties: list[str] = Field(default_factory=list)
    a11y_fallback: str = Field(description="Reduced-motion fallback implementation")


class UI2MotionResponse(BaseModel):
    visual_plan: VisualPlan
    motion_plan: MotionPlan
    patched_tsx: str = Field(description="Updated TSX code (including any new imports) ready to splice or write")


def build_user_prompt(
    context: RepoDesignContext,
    component: ComponentSlice,
    intent: str,
    mode: Literal["full_upgrade", "style_only", "motion_only"] = "full_upgrade",
) -> str:
    payload = {
        "mode": mode,
        "repo_context": context.to_prompt_dict(),
        "target_component": {
            "file_path": component.file_path,
            "component_name": component.component_name,
            "is_whole_file": component.is_whole_file,
            "imports": component.imports,
            "prop_types": component.prop_types,
            "helper_components": component.helper_components,
            "source_tsx": component.component_code,
        },
        "intent": intent,
    }
    return (
        "Compile the visual and motion upgrade for this React/TypeScript component.\n"
        "Respond with a single JSON object containing `visual_plan`, `motion_plan`, and `patched_tsx`.\n\n"
        + json.dumps(payload, indent=2)
    )


def generate_upgrade(
    context: RepoDesignContext,
    component: ComponentSlice,
    intent: str,
    mode: Literal["full_upgrade", "style_only", "motion_only"] = "full_upgrade",
    model: str = "ui2motion-7b:latest",
    ollama_url: str = "http://localhost:11434",
    num_ctx: int = 4096,
) -> UI2MotionResponse:
    user_prompt = build_user_prompt(context, component, intent, mode=mode)

    response = httpx.post(
        f"{ollama_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "format": UI2MotionResponse.model_json_schema(),
            "stream": False,
            "options": {
                "num_ctx": 8192,
                "num_predict": 8192,
                "temperature": 0.45,
            },
        },
        timeout=httpx.Timeout(300.0, connect=10.0),
    )
    response.raise_for_status()
    raw_content = response.json()["message"]["content"]
    return UI2MotionResponse.model_validate_json(raw_content)
