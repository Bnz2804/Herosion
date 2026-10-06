import json, urllib.request, urllib.error
B="http://localhost:5000/api"
def call(method, path, body=None):
    req=urllib.request.Request(B+path, method=method, data=json.dumps(body).encode() if body is not None else None, headers={"content-type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"null")

st, run = call("POST","/agent/runs",{"clusterId":"GLZ-001","question":"Which maize households in GLZ-001 should consider delaying planting?"})
print("RUN", st, run["workflowMode"], run["modelStatus"], [t["toolName"] for t in run["toolCalls"]])
print("decision[0]:", run["toolCalls"][0]["decision"], "| id:", run["toolCalls"][0]["auditCallId"])
delay=[r["householdId"] for r in run["householdRecommendations"] if r["recommendation"]=="delay_planting"]
print("delay:", delay)
print("insufficient submit ->", call("POST",f"/agent/runs/{run['runId']}/advisories",{"officerName":"Aminata Soglo","householdIds":["HH-GLZ001-007"]}))
print("fake household ->", call("POST",f"/agent/runs/{run['runId']}/advisories",{"officerName":"Aminata Soglo","householdIds":["HH-FAKE-1"]})[1])
st, drafts = call("POST",f"/agent/runs/{run['runId']}/advisories",{"officerName":"Aminata Soglo","householdIds":delay[:2]})
print("SUBMIT", st, [(d["origin"],d["status"],d["authoredBy"],d["submittedBy"],len(d["evidence"])) for d in drafts])
print("dup ->", call("POST",f"/agent/runs/{run['runId']}/advisories",{"officerName":"Aminata Soglo","householdIds":delay[:1]}))
aid=drafts[0]["advisoryId"]
print("self-approve (submitter) ->", call("POST",f"/advisories/{aid}/approve",{"officerName":"aminata soglo"}))
print("approve as agent name ->", call("POST",f"/advisories/{aid}/approve",{"officerName":drafts[0]["authoredBy"]})[0])
st, ok = call("POST",f"/advisories/{aid}/approve",{"officerName":"Koffi Adjovi","approvalNote":"Checked with field scout"})
print("APPROVE", st, ok["status"], ok["approvedBy"])
print("again ->", call("POST",f"/advisories/{aid}/approve",{"officerName":"Koffi Adjovi"})[0])
print("overview", call("GET","/overview")[1])
st, audit = call("GET","/audit")
print("AUDIT", st, len(audit))
for a in reversed(audit): print("  ", a["eventType"], "|", a["actor"][:26], "|", a["summary"][:100])
print("unknown cluster ->", call("POST","/agent/runs",{"clusterId":"NOPE-9","question":"anything here"})[0])
print("GLZ-002 run:", [t["toolName"] for t in call("POST","/agent/runs",{"clusterId":"GLZ-002","question":"Which maize households in GLZ-002 should consider delaying planting?"})[1]["toolCalls"]])
