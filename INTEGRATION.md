# Integration guide

## 1. Repo layout (target)
```
your-repo/
  pyproject.toml, README.md, INTEGRATION.md, .env.example, .gitignore
  src/africa_extension_agent/   Python: MCP server, agent, service, SQLite seed
  tests/  scripts/              offline tests, dev.sh, e2e_web.py
  web/                          Herosion (UI + Express API + OpenAPI), already merged
  .github/workflows/ci.yml
```
If you already pushed Herosion's raw files at the repo root, move them into `web/` first:
`git mv <each Herosion file/folder> web/` (artifacts, lib, scripts, package.json, pnpm-*.yaml,
tsconfig*.json, replit.md, .npmrc), then unzip this package over the repo root and let it
overwrite. **Files in `web/` from this package supersede your raw copies.**

## 2. Commit
```bash
unzip africa-extension-agent.zip && cp -r africa-extension-agent/. /path/to/your-repo/
cd /path/to/your-repo && git add -A && git commit -m "Merge Herosion workbench with Python extension agent"
git push
```
Do not commit `.env`, `data/`, `node_modules/` (all in `.gitignore`).

## 3. First run on a fresh machine
```bash
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
extension-agent seed && pytest                    # must pass before anything else
cp .env.example .env                              # set DATABASE_URL, MISTRAL_API_KEY (or ollama model)
scripts/dev.sh                                    # agent :8000, API :5000, UI :5173
```
Existing Postgres from an older Herosion run: `pnpm --filter @workspace/db run push` adds the
`agent_runs` table and the new advisory columns (run from `web/`).

## 4. Verify it is wired correctly
1. `curl localhost:5000/api/agent/status` → `agentServiceReachable: true`, `modelConfigured: true`.
2. `extension-agent demo` → full trace, GLZ-001 households with delay/proceed/insufficient.
3. In the UI: pick GLZ-001, ask the demo question, select recommendations, submit as a named
   officer, then approve as a *different* officer.
4. `extension-agent audit` and the UI audit view both show the run and each tool call.
5. `python scripts/e2e_web.py` runs the journey automatically (uses whatever model the service has).

## 5. Known gaps
- Never run against real Mistral yet; send the first trace if the agent's reasoning needs prompt tuning.
- `web/tsconfig.base.json` was reconstructed (missing from the upload).
- Synthetic data only; the as-of date is fixed at 2026-04-10 in the seed.
- Not built yet: authenticated identity, live weather, SMS/USSD, deployment.
