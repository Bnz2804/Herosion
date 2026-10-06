"""End-to-end check of auth, UI serving, plot matching and rate limiting against a RUNNING stack.
Usage: python scripts/e2e_plots.py http://localhost:5000 user:password"""
import base64, json, sys, urllib.error, urllib.request

B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
AUTH = "Basic " + base64.b64encode((sys.argv[2] if len(sys.argv) > 2 else "u:p").encode()).decode()


def call(method, path, body=None, auth=True, raw=False):
    h = {"content-type": "application/json"}
    if auth:
        h["authorization"] = AUTH
    r = urllib.request.Request(B + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=120) as x:
            d = x.read()
            return x.status, (d.decode() if raw else json.loads(d or b"null"))
    except urllib.error.HTTPError as e:
        d = e.read()
        try:
            return e.code, json.loads(d)
        except Exception:
            return e.code, d.decode()


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, extra if not cond else "")
    if not cond:
        check.failed = True


check.failed = False
check("healthz open without login", call("GET", "/api/healthz", auth=False)[0] == 200)
check("api closed without login", call("GET", "/api/clusters", auth=False)[0] == 401)
s, html = call("GET", "/", raw=True)
check("UI served from API container", s == 200 and 'id="root"' in html)
check("manifest served", call("GET", "/manifest.webmanifest", raw=True)[0] == 200)
s, plots = call("GET", "/api/clusters/GLZ-001/plots")
p7 = next(p for p in plots if p["plotId"] == "PL-GLZ001-007")
check("plot 007 is village-only", p7["locationPrecision"] == "village_centroid" and p7["geometry"] is None)
s, cand = call("GET", "/api/plots/PL-GLZ001-007/candidates")
top = cand["candidates"][0]
check("candidates ranked, best is FC-GLZ-0001", top["candidateId"] == "FC-GLZ-0001")
check("short officer name rejected", call("POST", "/api/plots/PL-GLZ001-007/match", {"candidateId": top["candidateId"], "officerName": "A"})[0] == 400)
s, m = call("POST", "/api/plots/PL-GLZ001-007/match", {"candidateId": top["candidateId"], "officerName": "Aminata Soglo"})
check("match accepted", s == 200 and m["verificationLevel"] == "officer_matched", m)
p7 = next(p for p in call("GET", "/api/clusters/GLZ-001/plots")[1] if p["plotId"] == "PL-GLZ001-007")
check("plot list refreshed immediately (cache invalidated)", p7["locationPrecision"] == "polygon" and p7["verificationLevel"] == "officer_matched")
check("same field to another plot -> 409", call("POST", "/api/plots/PL-GLZ001-003/match", {"candidateId": top["candidateId"], "officerName": "Aminata Soglo"})[0] == 409)
check("surveyed plot protected -> 409", call("POST", "/api/plots/PL-GLZ001-001/match", {"candidateId": "FC-GLZ-0002", "officerName": "Aminata Soglo"})[0] == 409)
check("audit has plot_matched", any(a["eventType"] == "plot_matched" for a in call("GET", "/api/audit")[1]))
q = {"clusterId": "GLZ-001", "question": "Which maize households in GLZ-001 should consider delaying planting?"}
s, run = call("POST", "/api/agent/runs", q)
check("agent run works", s == 201 and run["workflowMode"] == "agent_driven", run if s != 201 else "")
call("POST", "/api/agent/runs", q)
check("rate limit kicks in (429)", call("POST", "/api/agent/runs", q)[0] == 429)
sys.exit(1 if check.failed else 0)
