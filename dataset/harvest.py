from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from ui2motion.slicer import slice_tsx_file
from ui2motion.tokens import extract_repo_context

app = typer.Typer(help="Harvest real TSX component slices from local React/Next.js repos.")
console = Console()


@app.command()
def collect(
    repos: list[Path] = typer.Argument(..., help="Paths to local React/Next.js repositories"),
    out: Path = typer.Option(Path("dataset/harvested_seeds.json"), "--out", "-o"),
    min_lines: int = typer.Option(18, "--min-lines"),
    max_lines: int = typer.Option(180, "--max-lines"),
) -> None:
    """Scan local repositories and extract valid TSX component slices as distillation seeds."""
    harvested: list[dict] = []

    for repo in repos:
        repo_path = repo.expanduser().resolve()
        if not repo_path.exists():
            console.print(f"[yellow]Skipping missing path: {repo_path}[/yellow]")
            continue

        ctx = extract_repo_context(repo_path)
        tsx_files = [
            p
            for p in Path(ctx.frontend_root).rglob("*.tsx")
            if "node_modules" not in p.parts and ".next" not in p.parts and "dist" not in p.parts
        ]

        for tsx_file in sorted(tsx_files):
            try:
                sliced = slice_tsx_file(tsx_file)
                line_count = len(sliced.component_code.splitlines())
                if not (min_lines <= line_count <= max_lines):
                    continue

                harvested.append(
                    {
                        "name": sliced.component_name,
                        "file": tsx_file.name,
                        "intent": f"Upgrade {sliced.component_name} with cohesive visual hierarchy, repo token alignment, and GPU-safe motion choreography.",
                        "source": sliced.component_code,
                        "imports": sliced.imports,
                        "prop_types": sliced.prop_types,
                        "helper_components": sliced.helper_components,
                        "is_whole_file": sliced.is_whole_file,
                        "repo_context": ctx.to_prompt_dict(),
                    }
                )
            except Exception:
                continue

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(harvested, indent=2), encoding="utf-8")
    console.print(f"[bold green]✓ Harvested {len(harvested)} real component slices[/bold green] -> {out}")


if __name__ == "__main__":
    app()
