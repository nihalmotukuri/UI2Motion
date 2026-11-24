from __future__ import annotations

import difflib
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from ui2motion.client import generate_upgrade
from ui2motion.slicer import slice_tsx_file, splice_component_back
from ui2motion.tokens import extract_repo_context
from ui2motion.verifier import verify_patch

app = typer.Typer(help="Token-grounded UI visual profile & motion choreography compiler.")
console = Console()


@app.command()
def inspect(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to target React/Next.js repository"),
) -> None:
    """Inspect detected motion runtime, installed UI libraries, and design tokens."""
    ctx = extract_repo_context(repo)

    table = Table(title=f"UI2Motion Context — {Path(ctx.repo_root).name}")
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Detected Value", style="white")

    table.add_row("Frontend Root", ctx.frontend_root)
    table.add_row("Motion Runtime", f"[bold green]{ctx.motion_runtime}[/bold green]")
    table.add_row("Installed Packages", ", ".join(ctx.installed_packages) or "None")
    table.add_row("CSS Variables", f"{len(ctx.css_variables)} tokens")
    table.add_row("Tailwind Config Keys", ", ".join(ctx.tailwind_tokens.keys()) or "None (CSS/v4)")
    table.add_row("TypeScript Compiler", ctx.tsc_bin or "Not found")

    console.print(table)


@app.command()
def upgrade(
    file: Path = typer.Argument(..., help="Target .tsx component file"),
    intent: str = typer.Option(..., "--intent", "-i", help="Visual and/or motion upgrade goal"),
    repo: Path | None = typer.Option(None, "--repo", "-r", help="Repository root (auto-detected if omitted)"),
    component: str | None = typer.Option(None, "--component", "-c", help="Specific PascalCase component name"),
    mode: Literal["full_upgrade", "style_only", "motion_only"] = typer.Option(
        "full_upgrade", "--mode", "-m", help="Upgrade scope"
    ),
    model: str = typer.Option("ui2motion-7b:latest", "--model", help="Ollama model tag"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply verified patch without prompting"),
) -> None:
    """Upgrade a React/TSX component's visual hierarchy and motion choreography."""
    target_file = file.expanduser().resolve()
    repo_path = repo.expanduser().resolve() if repo else _infer_repo_root(target_file)

    ctx = extract_repo_context(repo_path)
    sliced = slice_tsx_file(target_file, component_name=component)

    console.print(
        f"[bold cyan]Target:[/bold cyan] {sliced.component_name} ({target_file.name}:L{sliced.start_line}-L{sliced.end_line}) "
        f"| [bold green]Runtime:[/bold green] {ctx.motion_runtime} | [bold magenta]Mode:[/bold magenta] {mode}"
    )

    with console.status(f"[bold yellow]Compiling visual & motion plan with {model}...[/bold yellow]"):
        result = generate_upgrade(ctx, sliced, intent=intent, mode=mode, model=model)

    merged_tsx = splice_component_back(sliced, result.patched_tsx)

    console.print(
        Panel(
            f"[bold]Surface:[/bold] {result.visual_plan.surface_hierarchy}\n"
            f"[bold]Typography:[/bold] {result.visual_plan.typography_rhythm}\n"
            f"[bold]Interactions:[/bold] {result.visual_plan.interaction_states}\n\n"
            f"[bold]Trigger:[/bold] {result.motion_plan.trigger} | "
            f"[bold]Physics:[/bold] {result.motion_plan.physics} | "
            f"[bold]Stagger:[/bold] {result.motion_plan.stagger_ms}ms\n"
            f"[bold]A11y Fallback:[/bold] {result.motion_plan.a11y_fallback}",
            title="Choreography & Visual Plan",
            border_style="bright_blue",
        )
    )

    verification = verify_patch(
        original_tsx=sliced.full_file_code,
        patched_tsx=merged_tsx,
        runtime=ctx.motion_runtime,
        tsc_bin=ctx.tsc_bin,
    )

    if not verification.passed:
        console.print("[bold red]Verification Failed:[/bold red]")
        for err in verification.errors:
            console.print(f"  • {err}")
        raise typer.Exit(code=1)

    diff_lines = list(
        difflib.unified_diff(
            sliced.full_file_code.splitlines(),
            merged_tsx.splitlines(),
            fromfile=f"a/{target_file.name}",
            tofile=f"b/{target_file.name}",
            lineterm="",
        )
    )

    if not diff_lines:
        console.print("[yellow]No changes generated.[/yellow]")
        return

    console.print(Syntax("\n".join(diff_lines), "diff", theme="monokai", line_numbers=False))

    if yes or Confirm.ask(f"Apply verified upgrade to [bold]{target_file.name}[/bold]?", default=False):
        target_file.write_text(merged_tsx, encoding="utf-8")
        console.print(f"[bold green]✓ Updated {target_file}[/bold green]")


def _infer_repo_root(file_path: Path) -> Path:
    for parent in [file_path.parent, *file_path.parents]:
        if (parent / ".git").exists():
            return parent
    return file_path.parent
