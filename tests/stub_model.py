"""TEST DOUBLE ONLY - a deterministic stand-in for the LLM so the plumbing can be tested offline.

It chooses its next tool by inspecting previous tool results (so the tool sequence differs between
scenarios), but it is NOT the real agent and is never used by the CLI.
"""
from __future__ import annotations

import re

from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


def _results(messages):
    out = {}
    for m in messages:
        for p in m.parts:
            if p.part_kind == "tool-return" and isinstance(p.content, dict):
                out[p.tool_name] = p.content
    return out


def _prompt(messages) -> str:
    return " ".join(p.content for m in messages for p in m.parts
                    if p.part_kind == "user-prompt" and isinstance(p.content, str))


def _final(info: AgentInfo, res: dict, bad_household: bool = False) -> ModelResponse:
    hh = res["get_household_cluster"]["households"]
    rain = res.get("get_rainfall_evidence")
    ids = [r["audit_call_id"] for r in res.values()]
    insufficient = rain is None or rain["evidence_sufficiency"] == "insufficient"
    first_wet = rain and rain["forecast"]["first_wet_day"]
    recs = []
    for h in hh:
        if h["crop"] != "maize":
            rec, why, miss = "not_applicable", "Not maize.", []
        elif h["planting_status"] == "planted":
            rec, why, miss = "already_planted_monitor", f"Planted {h['planting_date']}; check establishment.", []
        elif insufficient:
            rec, why, miss = "insufficient_evidence", "Rainfall evidence insufficient.", ["rainfall"]
        elif h["planned_planting_date"] is None:
            rec, why, miss = "insufficient_evidence", "No planned date.", ["planned_planting_date"]
        elif h["has_irrigation"]:
            rec, why, miss = "proceed_with_planting", "Irrigated.", []
        elif first_wet is None or h["planned_planting_date"] < first_wet:
            rec, why, miss = "delay_planting", f"Planned {h['planned_planting_date']} before first forecast wet day {first_wet}.", []
        else:
            rec, why, miss = "proceed_with_planting", "Planned after forecast rain returns.", []
        recs.append({"household_id": h["household_id"], "recommendation": rec, "rationale": why,
                     "evidence_ids": ids, "missing_data": miss})
    if bad_household:
        recs.append({"household_id": "HH-FAKE-999", "recommendation": "delay_planting", "rationale": "x",
                     "evidence_ids": ids, "missing_data": []})
    args = {"conclusion": "Stub conclusion.", "household_recommendations": recs,
            "data_gaps": ["rainfall evidence insufficient"] if insufficient else [], "evidence_ids": ids}
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])


def make_stub(bad_household_first: bool = False) -> FunctionModel:
    state = {"sent_bad": False}

    def fn(messages, info: AgentInfo) -> ModelResponse:
        res = _results(messages)
        cluster = re.search(r"[A-Z]{3}-\d{3}", _prompt(messages)).group(0)
        if "get_household_cluster" not in res:
            return ModelResponse(parts=[TextPart("Decision: I need to know which households exist first."),
                                        ToolCallPart("get_household_cluster", {"cluster_id": cluster, "crop": "maize"})])
        if "get_rainfall_evidence" not in res:
            return ModelResponse(parts=[TextPart("Decision: households known; whether to delay depends on rain, so check rainfall."),
                                        ToolCallPart("get_rainfall_evidence", {"cluster_id": cluster})])
        if res["get_rainfall_evidence"]["evidence_sufficiency"] == "insufficient":
            return _final(info, res)  # nothing more can be established -> stop
        if "get_crop_context" not in res:
            return ModelResponse(parts=[TextPart("Decision: rain evidence usable; I need the maize onset/dry-spell rules to interpret it."),
                                        ToolCallPart("get_crop_context", {"crop": "maize", "cluster_id": cluster})])
        hh = res["get_household_cluster"]["households"]
        if any(h["planting_status"] == "planted" for h in hh) and "get_pest_reports" not in res:
            return ModelResponse(parts=[TextPart("Decision: some maize is already planted; check pest pressure on seedlings."),
                                        ToolCallPart("get_pest_reports", {"cluster_id": cluster, "crop": "maize"})])
        if bad_household_first and not state["sent_bad"]:
            state["sent_bad"] = True
            return _final(info, res, bad_household=True)
        return _final(info, res)

    return FunctionModel(fn)
