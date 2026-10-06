import { Router, type IRouter } from "express";
import {
  CreateEvidenceRunBody,
  CreateEvidenceRunResponse,
  GetAgentStatusResponse,
  GetClusterEvidenceParams,
  GetClusterEvidenceResponse,
  GetClusterPlotsParams,
  GetClusterPlotsResponse,
  GetClustersResponse,
  GetOverviewResponse,
} from "@workspace/api-zod";
import { runAgent } from "../agent/orchestrator";
import { agentService, AgentServiceError } from "../agent/agentServiceClient";
import {
  findCluster,
  getEvidenceBundle,
  getOverviewCounts,
  listClusters,
  listPlots,
} from "../evidence/evidenceRepository";

const router: IRouter = Router();

router.get("/overview", async (_req, res): Promise<void> => {
  res.json(GetOverviewResponse.parse(await getOverviewCounts()));
});

router.get("/clusters", async (_req, res): Promise<void> => {
  res.json(GetClustersResponse.parse(await listClusters()));
});

router.get("/clusters/:clusterId/plots", async (req, res): Promise<void> => {
  const params = GetClusterPlotsParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  if (!(await findCluster(params.data.clusterId))) {
    res.status(404).json({ error: "Cluster not found" });
    return;
  }
  res.json(GetClusterPlotsResponse.parse(await listPlots(params.data.clusterId)));
});

router.get("/clusters/:clusterId/evidence", async (req, res): Promise<void> => {
  const params = GetClusterEvidenceParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const bundle = await getEvidenceBundle(params.data.clusterId);
  if (!bundle) {
    res.status(404).json({ error: "Cluster not found" });
    return;
  }
  res.json(GetClusterEvidenceResponse.parse(bundle));
});

router.get("/agent/status", async (_req, res): Promise<void> => {
  try {
    const status = await agentService.status();
    res.json(GetAgentStatusResponse.parse({ ...status, agentServiceReachable: true }));
  } catch {
    // Report the outage honestly instead of pretending a model is available.
    res.json(
      GetAgentStatusResponse.parse({
        modelProvider: "none",
        modelName: null,
        modelConfigured: false,
        advisoryGenerationAvailable: false,
        weatherProvider: "synthetic_fixture",
        weatherLive: false,
        identityMode: "self_attested_prototype",
        farmerDeliveryEnabled: false,
        agentServiceReachable: false,
      }),
    );
  }
});

router.post("/agent/runs", async (req, res): Promise<void> => {
  const parsed = CreateEvidenceRunBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  try {
    if (!(await findCluster(parsed.data.clusterId))) {
      res.status(404).json({ error: "Cluster not found" });
      return;
    }
    const run = await runAgent(parsed.data);
    res.status(201).json(CreateEvidenceRunResponse.parse(run));
  } catch (err) {
    if (err instanceof AgentServiceError) {
      res.status(err.httpStatus).json({ error: err.message, code: err.code });
      return;
    }
    throw err;
  }
});

export default router;
