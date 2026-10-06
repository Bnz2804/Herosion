"""CLI: extension-agent seed | demo | ask | audit"""
from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import audit, config
from .agent import ExtensionAdvice, run_agent
from .db.seed import seed as seed_db

app = typer.Typer(add_completion=False, help="Benin agricultural extension agent (foundation).")
console = Console()

DEMO_QUESTION = "Which maize households in GLZ-001 should consider delaying planting?"

STYLE = {
    "agent": ("AGENT", "bold cyan"),
    "meta": ("      ", "dim"),
    "decision": ("  AGENT DECISION", "yellow"),
    "tool_selected": ("  → TOOL SELECTED", "bold green"),
    "tool_result": ("  ← TOOL RESULT", "blue"),
}


def _emit(kind: str, text: str) -> None:
    label, style = STYLE[kind]
    console.print(f"[{style}]{label}[/{style}] {escape(text)}")


def render_final(advice: ExtensionAdvice) -> None:
    console.rule("[bold magenta]FINAL EVIDENCE-BACKED CONCLUSION")
    console.print(escape(advice.conclusion))
    t = Table(show_lines=True, expand=True)
    for col in ("Household", "Recommendation", "Rationale", "Evidence"):
        t.add_column(col, overflow="fold")
    order = {"delay_planting": 0, "already_planted_monitor": 1, "insufficient_evidence": 2,
             "proceed_with_planting": 3, "not_applicable": 4}
    for r in sorted(advice.household_recommendations, key=lambda r: (order[r.recommendation], r.household_id)):
        t.add_row(r.household_id, r.recommendation, escape(r.rationale) + (
            f"\n[dim]Missing: {escape(', '.join(r.missing_data))}[/dim]" if r.missing_data else ""),
            ", ".join(r.evidence_ids))
    console.print(t)
    if advice.data_gaps:
        console.print("[bold]Data gaps / uncertainty:[/bold]")
        for g in advice.data_gaps:
            console.print(f"  • {escape(g)}")
    console.print(f"[bold red]STATUS: {advice.status}[/bold red] - nothing is actioned until a human approves.")


@app.command()
def seed(db: str = typer.Option(None, help="SQLite path (default: ./data/extension.sqlite)")) -> None:
    """Create the SQLite database and load the synthetic Benin dataset."""
    if db:
        config.DB_PATH = type(config.DB_PATH)(db)
    path = seed_db(config.DB_PATH)
    console.print(f"[green]Seeded synthetic data into {path}[/green]")


def _run(question: str, model: str | None) -> None:
    advice, session, state = asyncio.run(run_agent(question, model=model, emit=_emit))
    render_final(advice)
    console.print(f"[dim]Tools called (in order): {' → '.join(state.tool_calls)}[/dim]")
    console.print(f"[dim]Audit: extension-agent audit --session {session}[/dim]")


@app.command()
def demo(model: str = typer.Option(None, help="Pydantic AI model string, e.g. mistral:mistral-large-latest")) -> None:
    """Run the first demo question."""
    console.print(f"[bold]Demo question:[/bold] {DEMO_QUESTION}\n")
    _run(DEMO_QUESTION, model)


@app.command()
def ask(question: str, model: str = typer.Option(None)) -> None:
    """Ask the agent any question (it decides which tools to use)."""
    _run(question, model)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the HTTP service that the Herosion workbench calls (agent + evidence views)."""
    import uvicorn
    uvicorn.run("africa_extension_agent.service:app", host=host, port=port)


@app.command("audit")
def audit_cmd(session: str = typer.Option(None, help="Filter by session id"), limit: int = 30) -> None:
    """Show the audit log of MCP tool calls."""
    rows = audit.read_log(session, limit)
    t = Table("call_id", "session", "time (UTC)", "tool", "status", "ms", "arguments", show_lines=False)
    for r in rows:
        t.add_row(r["call_id"], r["session_id"], r["ts_utc"][11:23], r["tool_name"], r["status"],
                  str(r["duration_ms"]), r["arguments_json"])
    console.print(t)


if __name__ == "__main__":
    app()
