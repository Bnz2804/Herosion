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


class ExtensionAdvice(BaseModel):
    conclusion: str = Field(description="2-4 sentence evidence-backed answer for the extension officer")
    household_recommendations: list[HouseholdRecommendation]
    data_gaps: list[str] = Field(default_factory=list, description="Evidence that was missing or weak")
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["DRAFT_PENDING_HUMAN_APPROVAL"] = "DRAFT_PENDING_HUMAN_APPROVAL"


@dataclass
class RunState:
    call_ids: set[str] = field(default_factory=set)
    households: dict[str, dict] = field(default_factory=dict)
    tool_calls: list[str] = field(default_factory=list)


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
            if r.recommendation != "not_applicable" and not r.evidence_ids:
                problems.append(f"{r.household_id} has no evidence_ids")
            bad = [e for e in r.evidence_ids if e not in st.call_ids]
            if bad:
                problems.append(f"{r.household_id} cites unknown evidence ids {bad}")
        bad = [e for e in out.evidence_ids if e not in st.call_ids]
        if bad:
            problems.append(f"unknown top-level evidence ids {bad}")
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
                            for h in res.get("households", []) or []:
                                state.households[h["household_id"]] = h
                            emit("tool_result", f"[{res.get('audit_call_id', '?')}] {res.get('summary', '(no summary)')}")
                        else:
                            emit("tool_result", str(res)[:300])
        assert run.result is not None
        return run.result.output, session_id, state
