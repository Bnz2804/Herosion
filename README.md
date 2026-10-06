# africa-extension-agent

Decision support for agricultural extension officers in Benin. **All data is synthetic**; no real farmer data.

```
Officer UI (React, web/artifacts/extension-backlog)
   │  REST  (OpenAPI contract: web/lib/api-spec)
Web API (Express + Postgres, web/artifacts/api-server)   owns: officers, drafts, approval, audit events
   │  HTTP  (AGENT_SERVICE_URL, optional token)
Agent service (FastAPI, src/africa_extension_agent/service.py)
   │  Pydantic AI agent  ──MCP/stdio──►  MCP server (4 read-only tools, each audit-logged)
SQLite (synthetic Benin data + tool-call audit log)       single source of truth for evidence
```

## Run it
```bash
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
extension-agent seed && pytest                      # offline tests (stub model, no key)
export MISTRAL_API_KEY=... # or EXTENSION_AGENT_MODEL=ollama:mistral-nemo
extension-agent demo                                # CLI trace: AGENT → tool → result → decision → ...
cp .env.example .env && scripts/dev.sh              # full stack (needs Postgres)
python scripts/e2e_web.py                           # officer journey against a running stack
```

## How the pieces fit
- The agent decides which MCP tools to call; neither service scripts the order.
- Agent output is a **draft**. An officer selects household recommendations and submits them; a
  *different* named officer must approve (not the agent, not the submitter). Nothing reaches farmers.
- Two audit layers: the tool log (SQLite, one row per MCP call, result hash) and web audit events
  (run, each tool call with the agent's stated reason, submission, approval). They cross-reference by call id.
- Missing/stale data is surfaced, never filled: GLZ-002 has a rain-station outage and the agent stops with
  "insufficient evidence"; no model key → 503, not made-up advice.

## Changes made to the Herosion app when merging (web/)
- Removed its CSV fixtures, its 7 filter-wrapper MCP tools and its fixed parallel orchestrator; evidence now
  comes from the Python service. Added `agent_runs` table and `submitted_by` / `agent_run_id` /
  `evidence_snapshot` columns on advisories (run `pnpm --filter @workspace/db run push`).
- `web/tsconfig.base.json` was **missing from the upload**; it is reconstructed (standard strict ESM config).
