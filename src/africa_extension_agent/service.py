"""HTTP service that lets the Herosion workbench (Express) use this project.

  GET  /healthz                       liveness
  GET  /status                        model + data-source capabilities
  GET  /clusters, /clusters/{id}/plots, /clusters/{id}/evidence    read views (SQLite = single source of truth)
  POST /runs                          run the tool-using agent; returns an EvidenceRun-compatible payload

The agent itself still only touches data through the MCP server (and so every call is audit-logged).
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from pydantic_ai.models import Model

import json
import sqlite3 as _sqlite3

from . import BUILD_ID, audit, config, plot_matching
from . import evidence_catalog as ec
from .agent import run_agent
from .db.connection import connect_readonly

STANDING_LIMITATIONS = [
    "All records are synthetic test data, not verified operational field evidence.",
    "Recommendations are drafts. Nothing is sent to farmers; a named human officer must approve.",
    "No live weather provider is connected; the forecast is a synthetic fixture.",
]


class RunInput(BaseModel):
    clusterId: str = Field(min_length=1)
    question: str = Field(min_length=3, max_length=500)


class MatchInput(BaseModel):
    candidateId: str = Field(min_length=1)
    officerName: str = Field(min_length=2, max_length=120)


def model_info(model: str | Model) -> dict[str, Any]:
    if not isinstance(model, str):
        return {"provider": "injected", "name": type(model).__name__, "configured": True}
    provider, _, name = model.partition(":")
    configured = {"mistral": bool(os.environ.get("MISTRAL_API_KEY")),
                  "ollama": True}.get(provider, True)  # ollama reachability is checked at call time
    return {"provider": provider, "name": name or model, "configured": configured}


def create_app(model_override: str | Model | None = None) -> FastAPI:
    app = FastAPI(title="africa-extension-agent service", version="0.1.0")
    try:  # upgrade older databases in place (idempotent)
        from .db.connection import ensure_schema
        ensure_schema()
    except Exception:
        pass

    def current_model() -> str | Model:
        return model_override or config.DEFAULT_MODEL

    def guard(x_agent_service_token: str | None = Header(default=None)) -> None:
        expected = os.environ.get("AGENT_SERVICE_TOKEN")
        if expected and x_agent_service_token != expected:
            raise HTTPException(401, "invalid service token")

    def conn() -> sqlite3.Connection:
        try:
            return connect_readonly()
        except FileNotFoundError as e:
            raise HTTPException(503, str(e))

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/status", dependencies=[Depends(guard)])
    def status():
        m = model_info(current_model())
        return {"modelProvider": m["provider"], "modelName": m["name"], "modelConfigured": m["configured"],
                "advisoryGenerationAvailable": m["configured"], "weatherProvider": "synthetic_fixture",
                "weatherLive": False, "identityMode": "self_attested_prototype", "farmerDeliveryEnabled": False,
                "agentBuild": BUILD_ID}

    @app.get("/clusters", dependencies=[Depends(guard)])
    def clusters():
        c = conn()
        try:
            return ec.list_clusters(c)
        finally:
            c.close()

    @app.get("/clusters/{cluster_id}/plots", dependencies=[Depends(guard)])
    def plots(cluster_id: str):
        c = conn()
        try:
            if not any(x["clusterId"] == cluster_id for x in ec.list_clusters(c)):
                raise HTTPException(404, "Cluster not found")
            return ec.list_plots(c, cluster_id)
        finally:
            c.close()

    @app.get("/clusters/{cluster_id}/evidence", dependencies=[Depends(guard)])
    def evidence(cluster_id: str):
        c = conn()
        try:
            items = ec.build_evidence(c, cluster_id)
            if items is None:
                raise HTTPException(404, "Cluster not found")
            return {"clusterId": cluster_id, "evidence": items, "sourceSummary": ec.SOURCE_SUMMARY,
                    "dataTier": ec.TIER}
        finally:
            c.close()

    @app.get("/plots/{plot_id}/candidates", dependencies=[Depends(guard)])
    def candidates(plot_id: str, radius_km: float = 2.0, limit: int = 8):
        c = conn()
        try:
            res = plot_matching.candidates_for(c, plot_id, max(0.2, min(radius_km, 10)), max(1, min(limit, 20)))
            if res is None:
                raise HTTPException(404, "Plot not found")
            return res
        finally:
            c.close()

    @app.post("/plots/{plot_id}/match", dependencies=[Depends(guard)])
    def match(plot_id: str, body: MatchInput):
        w = _sqlite3.connect(config.DB_PATH, timeout=10)
        w.row_factory = _sqlite3.Row
        try:
            return plot_matching.confirm_match(w, plot_id, body.candidateId, body.officerName)
        except plot_matching.MatchError as e:
            raise HTTPException(e.status, str(e))
        finally:
            w.close()

    @app.post("/runs", status_code=201, dependencies=[Depends(guard)])
    async def runs(body: RunInput):
        m = model_info(current_model())
        if not m["configured"]:
            raise HTTPException(503, {"error": "model_not_configured",
                                      "message": f"Model provider '{m['provider']}' has no credentials configured."})
        c = conn()
        try:
            catalog = ec.build_evidence(c, body.clusterId)
        finally:
            c.close()
        if catalog is None:
            raise HTTPException(404, "Cluster not found")

        decisions: list[str | None] = []
        pending: list[str | None] = [None]

        def emit(kind: str, text: str) -> None:
            if kind == "decision":
                pending[0] = text
            elif kind == "tool_selected":
                decisions.append(pending[0])
                pending[0] = None

        prompt = f"Officer's selected cluster: {body.clusterId}.\nQuestion: {body.question}"
        try:
            advice, session, state = await run_agent(prompt, model=current_model(), emit=emit)
        except Exception as exc:  # surfaced to the workbench and audit trail; never silently swallowed
            raise HTTPException(502, {"error": "agent_failed", "message": f"{type(exc).__name__}: {exc}"})

        log = audit.read_log(session)
        tool_by_call = {r["call_id"]: r["tool_name"] for r in log}
        tool_calls = [{
            "toolName": r["tool_name"], "status": "success" if r["status"] == "ok" else "error",
            "resultCount": r["result_count"] or 0, "arguments": r["arguments_json"], "auditCallId": r["call_id"],
            "summary": r["result_summary"], "decision": decisions[i] if len(decisions) == len(log) else None,
        } for i, r in enumerate(log)]
        c = conn()
        try:
            cells = ec.plot_cells(c, body.clusterId)
            crops = ec.plot_crops(c, body.clusterId)
        finally:
            c.close()
        per_call = {r["call_id"]: ec.evidence_for_call(catalog, r["tool_name"], json.loads(r["arguments_json"]),
                                                       body.clusterId, cells, crops) for r in log}
        used = {e for ids in per_call.values() for e in ids}
        evidence_items = [i for i in catalog if i["evidenceId"] in used]
        by_id = {e["evidenceId"]: e for e in evidence_items}

        recs = []
        for r in advice.household_recommendations:
            h = state.households.get(r.household_id, {})
            pid = ec.plot_id(r.household_id)
            ids: list[str] = []
            for cid in r.evidence_ids:
                for e in per_call.get(cid, []):
                    if not e.startswith("plot:") or e == f"plot:{pid}":
                        ids.append(e)
            own_cell = cells.get(pid)   # a household's own weather: drop other cells' items pulled in by multi-plot calls
            other = set(cells.values()) - {own_cell}
            ids = [e for e in ids if not (e.split(":")[0] in ("rainfall", "forecast") and e.split(":")[1] in other)]
            recs.append({"householdId": r.household_id, "plotId": pid, "crop": h.get("crop"),
                         "recommendation": r.recommendation, "rationale": r.rationale,
                         "evidenceIds": [i for i in dict.fromkeys(ids) if i in by_id],
                         "auditCallIds": [e for e in r.evidence_ids if e in tool_by_call],
                         "missingData": r.missing_data})

        return {"runId": session, "agentSessionId": session, "clusterId": body.clusterId,
                "question": body.question, "status": "completed", "workflowMode": "agent_driven",
                "modelStatus": "configured", "modelName": f"{m['provider']}:{m['name']}",
                "toolCalls": tool_calls, "evidence": evidence_items, "conclusion": advice.conclusion,
                "householdRecommendations": recs,
                "limitations": [*advice.data_gaps, *STANDING_LIMITATIONS],
                "createdAt": datetime.now(timezone.utc).isoformat()}

    return app


app = create_app()
