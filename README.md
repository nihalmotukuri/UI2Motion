# UI2Motion

Token-grounded UI visual profile & motion choreography compiler powered by **UI2Motion-8B** (`Qwen/Qwen3-8B` 4-bit QLoRA).

## Features
- **Automatic Repo Grounding:** Extracts CSS custom properties (`:root` / `@theme`), Tailwind config tokens, and installed motion runtimes (`motion/react`, `framer-motion`, `gsap`, or `css-only`).
- **Tree-Sitter TSX Slicing:** Isolates target React components, imports, and TypeScript prop interfaces without overflowing local `4096` context windows.
- **Deterministic Quality Gate:** Verifies TypeScript compilation (`tsc --noEmit`), contract preservation, GPU-composited properties (`transform`/`opacity`), GSAP lifecycle cleanup (`useGSAP`), and reduced-motion fallbacks (`useReducedMotion`).

## Quickstart

```bash
uv sync
uv run ui2motion inspect --repo /path/to/react-app
uv run ui2motion upgrade path/to/Component.tsx --intent "Upgrade to dark glassmorphism with staggered spring reveal"
