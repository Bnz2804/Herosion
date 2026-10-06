> **Merged into africa-extension-agent.** Evidence + agent now come from the Python service; see the root README for what changed.

# Herosion

Herosion is an evidence-first workbench for agricultural extension officers in Benin to inspect local records, prepare advisory drafts, and record named human approval.

## Run & Operate

- `pnpm --filter @workspace/extension-backlog run dev` — run the officer workbench
- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required env: `DATABASE_URL` — Postgres connection string
- Coolify frontend build env: `VITE_API_ORIGIN` — API server origin (for example, `https://api.example.com`); generated routes already include `/api`, so do not append `/api`. Leave unset to use same-origin `/api`. This is embedded during the Vite build.
- `OPENROUTER_API_KEY` is not configured; model-generated drafts remain disabled.

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

- `artifacts/extension-backlog` — officer-facing React workbench
- `artifacts/api-server/src/agent` — evidence-collection orchestrator
- `artifacts/api-server/src/mcp_server` — stateless MCP JSON-RPC tools and in-process client
- `artifacts/api-server/src/evidence` — CSV evidence readers and weather adapter interface
- `artifacts/api-server/src/audit` — audit event persistence
- `artifacts/api-server/data` — clearly labeled local test CSV fixtures
- `lib/api-spec/openapi.yaml` — API contract source of truth
- `lib/db/src/schema` — PostgreSQL advisory and audit schemas

## Architecture decisions

- Evidence runs call the internal MCP tools but do not generate advice while no model is configured.
- Weather is behind a provider interface; only local test fixtures are enabled, and they are not AccuWeather data.
- Drafts must cite evidence and are officer-authored in this build; a different named officer must approve them.
- Approval changes the record state and creates an audit event. No farmer-delivery channel exists.
- Names entered for author and approver are self-attested in this prototype; they are not authenticated identities.

## Product

Herosion lets officers review plot and household records alongside rainfall, crop-calendar, pest, and weather evidence; run evidence collection through MCP tools; write source-linked drafts; and record distinct-officer approval. Every local fixture is labeled as test data.

## User preferences

No farmer chatbot, generic chat, WhatsApp integration, payment, drone control, or direct farmer messaging.

## Gotchas

- All rows in the shipped CSVs are synthetic local test fixtures and must not be presented as operational field evidence.
- The public API is mounted under `/api`; the MCP JSON-RPC endpoint is `/api/mcp`.
- The initial model setup was declined, so do not claim AI-generated recommendations or enable draft generation without a real model integration.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
