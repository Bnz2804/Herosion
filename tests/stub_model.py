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


def make_plot_stub(wrong_cell_first: bool = False, wrong_facts_first: bool = False, target: str = "HH-GLZ001-001",
                   delay_wrongly_first: bool = False, skip_assess_first: bool = False) -> FunctionModel:
    """TEST DOUBLE: judges ONE household with plot-level rainfall and the planting assessment.
    wrong_cell_first   - first cites a rainfall call for a plot in another cell
    wrong_facts_first  - first misreads the cell's dry-spell number
    delay_wrongly_first- first gives the opposite of the assessment's suggestion
    skip_assess_first  - first answers without having called assess_planting_window
    Each mistake is only corrected after the validator pushes back."""
    other = "PL-GLZ001-009"

    def fn(messages, info: AgentInfo) -> ModelResponse:
        calls = [(p.tool_name, p.content) for m in messages for p in m.parts
                 if p.part_kind == "tool-return" and isinstance(p.content, dict)]
        retried = any(p.part_kind == "retry-prompt" for m in messages for p in m.parts)
        names = [n for n, _ in calls]
        if "get_household_cluster" not in names:
            return ModelResponse(parts=[TextPart("Decision: list households and their plots first."),
                                        ToolCallPart("get_household_cluster", {"cluster_id": "GLZ-001", "crop": "maize"})])
        rain = {c["location"]["cell_id"]: c for n, c in calls if n == "get_rainfall_evidence"}
        hh = next(c for n, c in calls if n == "get_household_cluster")
        mine = next(h for h in hh["households"] if h["household_id"] == target)
        want = other if (wrong_cell_first and not retried) else f"PL-{target[3:]}"
        if want == other and not rain:
            return ModelResponse(parts=[TextPart("Decision: check rainfall for a plot."),
                                        ToolCallPart("get_rainfall_evidence", {"plot_id": other})])
        if want != other and mine["plot"]["weather_cell_id"] not in rain:
            return ModelResponse(parts=[TextPart("Decision: need the rainfall for this household's own cell."),
                                        ToolCallPart("get_rainfall_evidence", {"plot_id": want})])
        if "get_crop_context" not in names:
            return ModelResponse(parts=[ToolCallPart("get_crop_context", {"crop": "maize", "cluster_id": "GLZ-001"})])
        skipping = skip_assess_first and not retried
        if "assess_planting_window" not in names and not skipping:
            return ModelResponse(parts=[TextPart("Decision: compute the planting risk in code."),
                                        ToolCallPart("assess_planting_window", {"plot_ids": [f"PL-{target[3:]}"]})])
        used = next(iter(rain.values())) if want == other else rain[mine["plot"]["weather_cell_id"]]
        assess = next((c for n, c in calls if n == "assess_planting_window"), None)
        suggestion = assess["assessments"][0]["rule_based_suggestion"] if assess else "delay_planting"
        rec = suggestion
        if delay_wrongly_first and not retried:
            rec = "delay_planting" if suggestion != "delay_planting" else "proceed_with_planting"
        ids = [hh["audit_call_id"], used["audit_call_id"]] + ([assess["audit_call_id"]] if assess else [])
        o = used["observed"]
        facts = {"cell_id": used["location"]["cell_id"], "rainfall_call_id": used["audit_call_id"],
                 "current_dry_spell_days": o["current_dry_spell_days"], "rain_last_7d_mm": o["total_last_7d"]["mm"],
                 "forecast_first_wet_day": used["forecast"]["first_wet_day"], "onset_rule_met_in_window": None}
        if wrong_facts_first and not retried:
            facts["current_dry_spell_days"] = 8 if o["current_dry_spell_days"] != 8 else 1   # a misread
        args = {"cell_facts": [facts], "conclusion": "Plot-level check.", "data_gaps": [], "evidence_ids": ids,
                "household_recommendations": [{"household_id": target, "recommendation": rec,
                                               "rationale": f"Dry spell {o['current_dry_spell_days']} d in its own cell; assessment: {suggestion}.",
                                               "evidence_ids": ids, "missing_data": []}]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])
    return FunctionModel(fn)
