"""MCP server (stdio) exposing four read-only tools. Every call is audit-logged.

Run standalone:  python -m africa_extension_agent.mcp_server
"""
from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from . import tools
from .audit import audited
from .db.connection import connect_readonly

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(
    "africa-extension-agent",
    instructions="Read-only evidence tools for agricultural extension officers in Benin. All data is synthetic.",
)


def _run(fn, **kwargs) -> dict[str, Any]:
    conn = connect_readonly()
    try:
        return fn(conn, **kwargs)
    finally:
        conn.close()


@mcp.tool(annotations=READ_ONLY)
def get_household_cluster(
    cluster_id: Annotated[str, Field(description="Cluster code, e.g. 'GLZ-001'")],
    crop: Annotated[str | None, Field(description="Filter by crop, e.g. 'maize'")] = None,
    planting_status: Annotated[str | None, Field(description="'planted' or 'not_planted'")] = None,
) -> dict[str, Any]:
    """List the households in a cluster (synthetic farmer IDs only) with crop, variety, soil, drainage,
    irrigation, planting status and planned/actual planting dates. Fields that are unknown are listed
    in `missing_fields`. Contains NO weather, calendar or pest information."""
    return audited("get_household_cluster")(
        lambda **kw: _run(tools.get_household_cluster, **kw))(cluster_id=cluster_id, crop=crop,
                                                              planting_status=planting_status)


@mcp.tool(annotations=READ_ONLY)
def get_rainfall_evidence(
    cluster_id: Annotated[str, Field(description="Cluster code, e.g. 'GLZ-001'")],
    as_of: Annotated[str | None, Field(description="ISO date; defaults to the dataset reference date")] = None,
    lookback_days: Annotated[int, Field(description="Days of observed rain to analyse (7-60)")] = 21,
    forecast_days: Annotated[int, Field(description="Days of forecast to include (1-14)")] = 14,
) -> dict[str, Any]:
    """Observed rainfall totals, current dry-spell length, strongest 3-day event, data gaps, and the
    short-range forecast for a cluster, plus an `evidence_sufficiency` rating. Does NOT interpret what
    the weather means for any crop."""
    return audited("get_rainfall_evidence")(
        lambda **kw: _run(tools.get_rainfall_evidence, **kw))(
        cluster_id=cluster_id, as_of=as_of, lookback_days=lookback_days, forecast_days=forecast_days)


@mcp.tool(annotations=READ_ONLY)
def get_crop_context(
    crop: Annotated[str, Field(description="Crop name, e.g. 'maize'")],
    cluster_id: Annotated[str, Field(description="Cluster code; used to look up its agro-ecological zone")],
    as_of: Annotated[str | None, Field(description="ISO date; defaults to the dataset reference date")] = None,
) -> dict[str, Any]:
    """Agronomic rules for a crop in the cluster's agro-ecological zone: planting-window dates and whether
    today is inside/before/after it, the rainfall onset rule, the maximum safe dry spell after sowing,
    the establishment period, and variety maturity/drought tolerance. Contains NO observed weather."""
    return audited("get_crop_context")(
        lambda **kw: _run(tools.get_crop_context, **kw))(crop=crop, cluster_id=cluster_id, as_of=as_of)


@mcp.tool(annotations=READ_ONLY)
def get_pest_reports(
    cluster_id: Annotated[str, Field(description="Cluster code, e.g. 'GLZ-001'")],
    crop: Annotated[str | None, Field(description="Filter by crop")] = None,
    since_days: Annotated[int, Field(description="How many days back to look (1-180)")] = 30,
    as_of: Annotated[str | None, Field(description="ISO date; defaults to the dataset reference date")] = None,
) -> dict[str, Any]:
    """Recent scout pest reports for a cluster, aggregated by pest (incidence %, trend, sample-size
    caveat). No reports means no data, not absence of pests."""
    return audited("get_pest_reports")(
        lambda **kw: _run(tools.get_pest_reports, **kw))(cluster_id=cluster_id, crop=crop,
                                                         since_days=since_days, as_of=as_of)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
