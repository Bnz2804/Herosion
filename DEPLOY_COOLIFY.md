# Deploy on Coolify (test deployment, before buying a domain)

Three containers from one repo: `db` (Postgres), `agent` (Python; internal only), `web` (API + mobile UI; the only public service).

## 1. Create the resource
1. Coolify -> **Projects -> New Resource -> Docker Compose** (Git repository; private repo: connect via GitHub App/deploy key).
2. Branch `main`, **Compose file location:** `/docker-compose.coolify.yml`.
3. **Environment variables** (see `.env.example`): `POSTGRES_PASSWORD`, `AGENT_SERVICE_TOKEN`, `APP_BASIC_AUTH`, `MISTRAL_API_KEY`. Compose refuses to deploy if a required one is empty.
4. **Domains:** open service `web` and set its domain with port `5000`. Do **not** give `agent` or `db` a domain.
   - No domain yet: let Coolify generate its default URL for the server (an `sslip.io` address). It usually gets HTTPS automatically; verify on your server.
   - Plain IP fallback: uncomment `ports: "8080:5000"` in the compose file and open `http://<VPS-IP>:8080`. HTTP only; fine for a quick check, not for install-to-home-screen or GPS capture (both need HTTPS).
5. **Deploy.** First build takes a few minutes (it compiles the UI and type-checks the shared libraries).

## 2. Check it
- Open the URL on your phone; the browser asks for the `APP_BASIC_AUTH` user/password.
- Header chip "Model": should read **Configured**. If "Agent service offline", open the `agent` logs. If "Not configured", `MISTRAL_API_KEY` is missing.
- Pick GLZ-001, ask the demo question. Open a household, tap **Find and confirm this field**.
- On Android Chrome / iOS Safari use "Add to Home Screen" (needs HTTPS).

## 3. Weather
Out of the box the demo uses a fixed synthetic date (2026-04-10) and synthetic rain. To use real weather:
- In Coolify add a **Scheduled Task** on service `agent`, e.g. every 6 h: `extension-agent sync-weather --live`.
- This fetches Open-Meteo rainfall per ~5 km cell for every plot and switches the "as of" date to today. Past rain is **model analysis, not a gauge**; every result says so. Check Open-Meteo's terms before production use.
- Back to demo mode: `extension-agent set-mode synthetic`.
- Synthetic scout reports and crop calendar stay synthetic; the agent will report old/missing evidence rather than use it.

## 4. Bring in existing data (run in the `agent` container terminal)
```
extension-agent import-fields /data/fields.geojson --source ftw-2025        # candidate fields (GeoJSON/GeoJSONL; GeoParquet needs the geo extra)
extension-agent import-plots /data/farmers.csv --geometry-source cooperative_file --cluster GLZ-001 --mapping /data/map.json
```
Both print a quality report (rejected rows with reasons). Owner names/phones are stored only with a consent flag, in a separate database (`/data/identity.sqlite`) that the agent never opens. Put files into `/data` via a Coolify file mount.
**Not built yet:** importing clusters and the crop calendar, so a database with real data still needs those created by hand. Keep `SEED_SYNTHETIC=true` for this test deployment.

## 5. Safety defaults
- `web` refuses to start without `APP_BASIC_AUTH` in production. `agent` has no public route and requires `AGENT_SERVICE_TOKEN`.
- Agent runs are capped (`MAX_AGENT_RUNS_PER_HOUR`) so a leaked URL cannot drain your model credits.
- The seed command refuses to overwrite an existing database (`--force` is required).
- Do not load real farmer data until consent capture and hosting/data-protection obligations are settled (check Benin's rules with the data-protection authority).

## 6. Operations
- Backups: Coolify scheduled backup for Postgres; the SQLite volume `agentdata` (`/data`) holds the evidence, plot matches and tool audit log; back it up too.
- Redeploy on push: enable Coolify's auto-deploy for the branch.
- Schema changes: `web` runs a non-destructive `drizzle push` on start; if a change would lose data it stops and logs why instead of applying it.

## 7. Login troubleshooting
On start the `web` log prints `Login enabled for user '<name>' (password length N)`. Every refused login logs
`login refused` with a reason (no header yet, wrong user, wrong password with the lengths). Quotes or spaces around
`APP_BASIC_AUTH` are tolerated; a value without `username:` makes `web` refuse to start with an explanatory error.
