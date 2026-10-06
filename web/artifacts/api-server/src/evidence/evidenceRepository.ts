import { eq } from "drizzle-orm";
import { db, advisoriesTable } from "@workspace/db";
import {
  GetClusterEvidenceResponse,
  GetClusterPlotsResponse,
  GetClustersResponse,
} from "@workspace/api-zod";
import { agentService, AgentServiceError } from "../agent/agentServiceClient";

/**
 * Read-side views of cluster/plot/evidence records. The single source of truth is the agent
 * service's SQLite database (the same data the MCP tools read), so what the officer inspects is
 * exactly what the agent can cite.
 */
export type ClusterRow = ReturnType<typeof GetClustersResponse.parse>[number];
export type PlotRow = ReturnType<typeof GetClusterPlotsResponse.parse>[number];
export type EvidenceBundle = ReturnType<typeof GetClusterEvidenceResponse.parse>;
export type EvidenceItem = EvidenceBundle["evidence"][number];

const DATA_TIER = "local_test_data" as const;

// Short-lived cache: listing advisories would otherwise fetch the same cluster evidence repeatedly.
const TTL_MS = 15_000;
const cache = new Map<string, { at: number; value: unknown }>();
async function cached<T>(key: string, load: () => Promise<T>): Promise<T> {
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.value as T;
  const value = await load();
  cache.set(key, { at: Date.now(), value });
  return value;
}

export async function listClusters(): Promise<ClusterRow[]> {
  return cached("clusters", async () => GetClustersResponse.parse(await agentService.clusters()));
}

export async function findCluster(clusterId: string): Promise<ClusterRow | undefined> {
  return (await listClusters()).find((cluster) => cluster.clusterId === clusterId);
}

export async function listPlots(clusterId: string): Promise<PlotRow[]> {
  return cached(`plots:${clusterId}`, async () =>
    GetClusterPlotsResponse.parse(await agentService.plots(clusterId)),
  );
}

export async function getEvidenceBundle(clusterId: string): Promise<EvidenceBundle | undefined> {
  try {
    return await cached(`evidence:${clusterId}`, async () =>
      GetClusterEvidenceResponse.parse(await agentService.evidence(clusterId)),
    );
  } catch (err) {
    if (err instanceof AgentServiceError && err.code === "not_found") return undefined;
    throw err;
  }
}

export async function getEvidenceItems(clusterId: string): Promise<EvidenceItem[]> {
  return (await getEvidenceBundle(clusterId))?.evidence ?? [];
}

export async function getAdvisoryEvidence(evidenceIds: string[], clusterId: string) {
  const byId = new Map((await getEvidenceItems(clusterId)).map((item) => [item.evidenceId, item]));
  return evidenceIds
    .map((evidenceId) => byId.get(evidenceId))
    .filter((evidence): evidence is EvidenceItem => evidence !== undefined);
}

export async function getOverviewCounts() {
  const [clusters, pending, approved] = await Promise.all([
    listClusters(),
    db.select({ id: advisoriesTable.id }).from(advisoriesTable).where(eq(advisoriesTable.status, "draft")),
    db.select({ id: advisoriesTable.id }).from(advisoriesTable).where(eq(advisoriesTable.status, "approved")),
  ]);
  return {
    clusters: clusters.length,
    plots: clusters.reduce((sum, c) => sum + c.plotCount, 0),
    pendingAdvisories: pending.length,
    approvedAdvisories: approved.length,
    dataTier: DATA_TIER,
    lastUpdated: new Date().toISOString(),
  };
}
