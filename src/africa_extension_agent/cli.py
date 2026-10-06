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
def seed(db: str = typer.Option(None, help="SQLite path (default: ./data/extension.sqlite)"),
         force: bool = typer.Option(False, help="Overwrite an existing database (DESTROYS its data)")) -> None:
    """Create the SQLite database and load the synthetic Benin dataset."""
    if db:
        config.DB_PATH = type(config.DB_PATH)(db)
    if config.DB_PATH.exists() and not force:
        console.print(f"[red]{config.DB_PATH} already exists. Refusing to overwrite; use --force to destroy it.[/red]")
        raise typer.Exit(1)
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


@app.command("import-fields")
def import_fields_cmd(file: str, source: str = typer.Option(..., help="Label, e.g. ftw-2025 or andf-pfr"),
                      id_property: str = typer.Option(None), bbox: str = typer.Option(None, help="lon_min,lat_min,lon_max,lat_max (GeoParquet filter)")) -> None:
    """Import field polygons (GeoJSON/GeoJSONL/GeoParquet) as CANDIDATES for officer matching."""
    from .db.connection import connect, ensure_schema
    from .importers import import_fields
    ensure_schema()
    conn = connect()
    console.print(import_fields(conn, file, source, id_property, tuple(map(float, bbox.split(","))) if bbox else None))


@app.command("import-plots")
def import_plots_cmd(file: str, geometry_source: str = typer.Option(..., help="cadastre_andf | officer_gps | cooperative_file | satellite_field"),
                     mapping: str = typer.Option(None, help="JSON file mapping canonical fields to your CSV columns"),
                     cluster: str = typer.Option(None, help="Default cluster id if the file has no cluster column"),
                     crop: str = "maize") -> None:
    """Import a farmer+plot list (CSV). Owner details go to a separate, consent-gated database."""
    import json as _json
    from .db.connection import connect, ensure_schema
    from .importers import import_plots_csv
    ensure_schema()
    conn = connect()
    mp = _json.load(open(mapping)) if mapping else None
    console.print(import_plots_csv(conn, file, geometry_source, mp, cluster, crop))


@app.command("sync-weather")
def sync_weather_cmd(live: bool = typer.Option(False, help="Also switch the dataset clock to 'today' (live mode)")) -> None:
    """Fetch rain for every plot's grid cell from Open-Meteo. Failures leave existing data untouched."""
    from .db.connection import connect, ensure_schema
    from .weather_sync import OpenMeteo, sync
    ensure_schema()
    conn = connect()
    if live:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('as_of_mode','live')"); conn.commit()
    for r in sync(conn, OpenMeteo()):
        console.print(r)


@app.command("set-mode")
def set_mode(mode: str = typer.Argument(..., help="live | synthetic")) -> None:
    """live: 'as of' = today. synthetic: fixed demo date (2026-04-10)."""
    from .db.connection import connect, ensure_schema
    ensure_schema()
    conn = connect()
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('as_of_mode', ?)", ("live" if mode == "live" else "synthetic",)); conn.commit()
    console.print(f"mode = {mode}")


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
