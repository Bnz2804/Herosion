"""Pydantic AI agent that discovers and calls MCP tools on its own.

There is NO scripted tool sequence in this file. The model sees the four tool descriptions via MCP,
chooses which to call, reads each result, and decides what to do next.
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Callable, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, FunctionToolResultEvent, ModelRetry, RunContext
from pydantic_ai.mcp import MCPToolset, StdioTransport
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from . import config

INSTRUCTIONS = """\
You are a decision-support agent for an agricultural extension officer in Benin. All data is synthetic.
You advise the officer; you never act. Every recommendation is a DRAFT that a human must approve.

You have four read-only tools (discovered via MCP). They return different kinds of evidence:
household/farm facts, observed+forecast rainfall, crop-calendar rules, and pest scouting reports.
YOU decide which tools are relevant to the question, in what order, and when you have enough.
Call a tool only if its result could change an answer. Reuse earlier results; do not repeat a call
with the same arguments.

BEFORE EVERY TOOL CALL, write one short sentence beginning "Decision:" saying what you just learned
(or what is missing) and why you are calling that tool next.

Evidence rules (strict):
- Use only values that appear in tool results. Never invent rainfall, dates, households, rules or pest data.
- If a tool says evidence is insufficient/partial, a field is in `missing_fields`, a forecast is
  unavailable, or no calendar entry exists, say so and use `insufficient_evidence` for the affected
  households. Absence of pest reports is not absence of pests.
- Cite the `audit_call_id` values (e.g. call-1a2b3c) of the tool results behind each conclusion.
- Judge each household individually: planting status, planned date, irrigation, soil/drainage,
  variety and seed availability can all change the answer. Households already planted are not
  "delay" candidates; flag their establishment risk instead. Households of other crops than the one
  asked about are `not_applicable`.
- Compare observed rainfall and forecast against the crop's onset rule and maximum safe dry spell
  from the crop-calendar tool; do not rely on general knowledge of thresholds.
- Compare each household's planned_planting_date with its cell's forecast first_wet_day. A household that already
  plans to plant AFTER the rain returns does not need to delay; do not recommend delay_planting for it.
- Weather varies between ~5 km grid cells. Each household has a `plot` block with a `weather_cell_id`.
  For a question about specific households, call get_rainfall_evidence with plot_id (any plot in the cell)
  once per distinct weather_cell_id among the households you judge, and judge every household with ITS OWN
  cell's result. Use the cluster-level call (cluster_id only) only when no plot is available.
- Never restate or re-derive weather numbers yourself. Put each cell's numbers into `cell_facts` EXACTLY as the
  tool returned them (and set onset_rule_met_in_window by comparing observed.max_3day_total.mm with the crop's
  onset_rain_mm_3d). Your conclusion and rationales may only describe a cell using what is in its cell_facts.
  Different cells can differ: never say one cell's conditions apply to another without checking its numbers.
  The answer is rejected if the numbers differ from the tool results.
- State how well each plot's location is known (`verification_level`, `location_confidence`). For
  `village_centroid` precision or an unconfirmed `satellite_candidate`, say the weather is for an
  approximate location and lower your certainty; mention an `area_check` mismatch. Never present
  location as certain when it is not.
- You only ever see household/plot IDs. Never guess or mention an owner's name.
- Give no pesticide product or dosage advice.
Finish with the structured answer only after you have the evidence you need (or have established it is unavailable).
"""


class HouseholdRecommendation(BaseModel):
    household_id: str
    recommendation: Literal[
        "delay_planting", "proceed_with_planting", "already_planted_monitor",
        "insufficient_evidence", "not_applicable"]
    rationale: str = Field(description="Specific reasoning using values from the tool results")
    evidence_ids: list[str] = Field(default_factory=list, description="audit_call_id values supporting this")
    missing_data: list[str] = Field(default_factory=list)


class CellFacts(BaseModel):
    """Numbers per weather cell, copied from the tool result. Checked against the real result."""
    cell_id: str
    rainfall_call_id: str = Field(description="audit_call_id of the get_rainfall_evidence call for this cell")
    current_dry_spell_days: int | None = Field(description="from observed.current_dry_spell_days, null if unknown")
    rain_last_7d_mm: float | None = Field(description="from observed.total_last_7d.mm, null if no data")
    forecast_first_wet_day: str | None = Field(description="from forecast.first_wet_day, null if none")
    onset_rule_met_in_window: bool | None = Field(
        description="true if observed.max_3day_total.mm >= the crop's onset_rain_mm_3d from get_crop_context; "
                    "null if the crop rule was not retrieved or there is no data")


class ExtensionAdvice(BaseModel):
    conclusion: str = Field(description="2-4 sentence evidence-backed answer for the extension officer")
    household_recommendations: list[HouseholdRecommendation]
    cell_facts: list[CellFacts] = Field(default_factory=list,
                                        description="One entry per weather cell you retrieved rainfall for")
    data_gaps: list[str] = Field(default_factory=list, description="Evidence that was missing or weak")
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["DRAFT_PENDING_HUMAN_APPROVAL"] = "DRAFT_PENDING_HUMAN_APPROVAL"


@dataclass
class RunState:
    call_ids: set[str] = field(default_factory=set)
    households: dict[str, dict] = field(default_factory=dict)
    tool_calls: list[str] = field(default_factory=list)
    call_cells: dict[str, str] = field(default_factory=dict)
    rain: dict[str, dict] = field(default_factory=dict)   # audit_call_id -> numbers from a plot-level rainfall result
    cluster_wet: str | None = None                          # first forecast wet day from a cluster-level rainfall call
    onset_mm: float | None = None                           # crop onset rule from get_crop_context  # audit_call_id -> weather cell of plot-level rainfall calls


Emit = Callable[[str, str], None]  # (kind, text)


def build_agent(model: str | Model, session_id: str, db_path: str) -> Agent[RunState, ExtensionAdvice]:
    env = {**os.environ, "EXTENSION_AGENT_DB": db_path, "EXTENSION_AGENT_SESSION": session_id}
    toolset = MCPToolset(StdioTransport(sys.executable, ["-m", "africa_extension_agent.mcp_server"], env=env))
    agent = Agent(model, deps_type=RunState, output_type=ExtensionAdvice, instructions=INSTRUCTIONS,
                  toolsets=[toolset], retries=2)

    @agent.output_validator
    async def no_fabrication(ctx: RunContext[RunState], out: ExtensionAdvice) -> ExtensionAdvice:
        st = ctx.deps
        problems: list[str] = []
        for r in out.household_recommendations:
            h = st.households.get(r.household_id)
            if h is None:
                problems.append(f"{r.household_id} never appeared in a get_household_cluster result")
                continue
            if r.recommendation == "delay_planting" and h["planting_status"] == "planted":
                problems.append(f"{r.household_id} is already planted; use already_planted_monitor")
            # A household that already plans to plant AFTER the forecast rain returns has nothing to delay.
            if r.recommendation == "delay_planting" and h.get("planned_planting_date"):
                cell = (h.get("plot") or {}).get("weather_cell_id")
                wets = [v["wet"] for v in st.rain.values() if v["cell"] == cell and v["wet"]] or (
                    [st.cluster_wet] if st.cluster_wet else [])
                if wets and h["planned_planting_date"] > min(wets):
                    problems.append(f"{r.household_id} plans to plant on {h['planned_planting_date']}, after the forecast rain "
                                    f"returns on {min(wets)}; delay_planting is not supported. Use proceed_with_planting "
                                    f"(and say its planned date is after the rain returns)")
            if r.recommendation != "not_applicable" and not r.evidence_ids:
                problems.append(f"{r.household_id} has no evidence_ids")
            bad = [e for e in r.evidence_ids if e not in st.call_ids]
            if bad:
                problems.append(f"{r.household_id} cites unknown evidence ids {bad}")
            own = ((h.get("plot") or {}).get("weather_cell_id"))
            wrong = [e for e in r.evidence_ids if e in st.call_cells and own and st.call_cells[e] != own]
            if wrong:
                problems.append(f"{r.household_id} is in weather cell {own} but cites rainfall for another cell ({wrong}); "
                                f"call get_rainfall_evidence with this household's plot_id")
        bad = [e for e in out.evidence_ids if e not in st.call_ids]
        if bad:
            problems.append(f"unknown top-level evidence ids {bad}")
        # --- numbers must match the tool results exactly (the model may not restate or re-derive them) ---
        stated = {f.cell_id for f in out.cell_facts}
        for f in out.cell_facts:
            real = st.rain.get(f.rainfall_call_id)
            if real is None or real["cell"] != f.cell_id:
                problems.append(f"cell_facts for {f.cell_id}: {f.rainfall_call_id} is not the rainfall call for that cell")
                continue
            if f.current_dry_spell_days != real["dry"]:
                problems.append(f"{f.cell_id}: current_dry_spell_days is {real['dry']}, not {f.current_dry_spell_days}")
            if (f.rain_last_7d_mm is None) != (real["last7"] is None) or (
                    f.rain_last_7d_mm is not None and abs(f.rain_last_7d_mm - real["last7"]) > 0.05):
                problems.append(f"{f.cell_id}: rain_last_7d_mm is {real['last7']}, not {f.rain_last_7d_mm}")
            if f.forecast_first_wet_day != real["wet"]:
                problems.append(f"{f.cell_id}: forecast_first_wet_day is {real['wet']}, not {f.forecast_first_wet_day}")
            if f.onset_rule_met_in_window is not None:
                if st.onset_mm is None:
                    problems.append(f"{f.cell_id}: onset_rule_met_in_window must be null; get_crop_context was not called")
                elif real["max3"] is None:
                    problems.append(f"{f.cell_id}: no complete 3-day window of data, onset_rule_met_in_window must be null")
                elif f.onset_rule_met_in_window != (real["max3"] >= st.onset_mm):
                    problems.append(f"{f.cell_id}: strongest 3-day total is {real['max3']} mm against a {st.onset_mm} mm rule, "
                                    f"so onset_rule_met_in_window is {real['max3'] >= st.onset_mm}")
        for r in out.household_recommendations:
            own = (st.households.get(r.household_id, {}).get("plot") or {}).get("weather_cell_id")
            if own and st.rain and r.recommendation not in ("not_applicable", "insufficient_evidence") and own not in stated:
                problems.append(f"{r.household_id}: no cell_facts for its weather cell {own}")
        if problems:
            raise ModelRetry("Fix these issues using only real tool results: " + "; ".join(problems))
        return out

    return agent


async def run_agent(question: str, model: str | Model | None = None, db_path: str | None = None,
                    session_id: str | None = None, emit: Emit | None = None) -> tuple[ExtensionAdvice, str, RunState]:
    emit = emit or (lambda kind, text: None)
    session_id = session_id or "sess-" + uuid.uuid4().hex[:8]
    db_path = str(db_path or config.DB_PATH.resolve())
    agent = build_agent(model or config.DEFAULT_MODEL, session_id, db_path)
    state = RunState()
    emit("agent", f"question: {question}")
    emit("meta", f"session {session_id}; audit trail in {db_path} (table audit_log)")

    async with agent.iter(question, deps=state, usage_limits=UsageLimits(tool_calls_limit=config.MAX_TOOL_CALLS)) as run:
        async for node in run:
            if not Agent.is_call_tools_node(node):
                continue
            parts = node.model_response.parts
            texts = [p.content.strip() for p in parts if p.part_kind == "text" and p.content.strip()]
            calls = [p for p in parts if p.part_kind == "tool-call" and not p.tool_name.startswith("final_result")]
            if texts:
                emit("decision", " ".join(texts))
            elif calls:
                emit("decision", "(model gave no stated rationale for this step)")
            for c in calls:
                state.tool_calls.append(c.tool_name)
                emit("tool_selected", f"{c.tool_name} {c.args_as_json_str()}")
            if not calls:
                continue
            async with node.stream(run.ctx) as stream:
                async for ev in stream:
                    if isinstance(ev, FunctionToolResultEvent) and ev.part.part_kind == "tool-return":
                        res = ev.part.content
                        if isinstance(res, dict):
                            if cid := res.get("audit_call_id"):
                                state.call_ids.add(cid)
                                if (res.get("location") or {}).get("basis") == "plot_grid_cell":
                                    state.call_cells[cid] = res["location"]["cell_id"]
                                    o = res["observed"]
                                    state.rain[cid] = {"cell": res["location"]["cell_id"], "dry": o["current_dry_spell_days"],
                                                       "last7": o["total_last_7d"]["mm"], "wet": res["forecast"]["first_wet_day"],
                                                       "max3": (o["max_3day_total"] or {}).get("mm")}
                            if (res.get("location") or {}).get("basis") == "cluster_series":
                                state.cluster_wet = (res.get("forecast") or {}).get("first_wet_day")
                            if isinstance(res.get("relevant_season"), dict):
                                state.onset_mm = res["relevant_season"].get("onset_rain_mm_3d")
                            for h in res.get("households", []) or []:
                                state.households[h["household_id"]] = h
                            emit("tool_result", f"[{res.get('audit_call_id', '?')}] {res.get('summary', '(no summary)')}")
                        else:
                            emit("tool_result", str(res)[:300])
        assert run.result is not None
        return run.result.output, session_id, state
