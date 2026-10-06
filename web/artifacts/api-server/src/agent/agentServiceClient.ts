import type { CreateEvidenceRunResponse, GetAgentStatusResponse } from "@workspace/api-zod";

/**
 * Client for the Python agent service (africa-extension-agent). That service owns the SQLite data,
 * the MCP evidence tools and the tool-using agent; this API owns officers, drafts, approval and audit.
 */
type Json = Record<string, unknown>;
export type AgentRunPayload = ReturnType<typeof CreateEvidenceRunResponse.parse>;
export type AgentStatusPayload = Omit<ReturnType<typeof GetAgentStatusResponse.parse>, "agentServiceReachable">;

export class AgentServiceError extends Error {
  constructor(
    message: string,
    readonly httpStatus: number,
    readonly code: "unreachable" | "model_not_configured" | "agent_failed" | "not_found" | "bad_response",
  ) {
    super(message);
    this.name = "AgentServiceError";
  }
}

const baseUrl = () => (process.env["AGENT_SERVICE_URL"] ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function call<T>(path: string, init?: { method?: string; body?: Json; timeoutMs?: number }): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  const token = process.env["AGENT_SERVICE_TOKEN"];
  if (token) headers["x-agent-service-token"] = token;

  let res: Response;
  try {
    res = await fetch(`${baseUrl()}${path}`, {
      method: init?.method ?? "GET",
      headers,
      body: init?.body ? JSON.stringify(init.body) : undefined,
      signal: AbortSignal.timeout(init?.timeoutMs ?? 10_000),
    });
  } catch (err) {
    throw new AgentServiceError(
      `Agent service unreachable at ${baseUrl()}: ${err instanceof Error ? err.message : String(err)}`,
      503,
      "unreachable",
    );
  }
  const text = await res.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    throw new AgentServiceError("Agent service returned a non-JSON response", 502, "bad_response");
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | undefined)?.detail;
    const d = typeof detail === "object" && detail !== null ? (detail as { error?: string; message?: string }) : {};
    const message = d.message ?? (typeof detail === "string" ? detail : `Agent service error ${res.status}`);
    if (res.status === 404) throw new AgentServiceError(message, 404, "not_found");
    if (d.error === "model_not_configured") throw new AgentServiceError(message, 503, "model_not_configured");
    throw new AgentServiceError(message, res.status === 503 ? 503 : 502, d.error === "agent_failed" ? "agent_failed" : "unreachable");
  }
  return data as T;
}

export const agentService = {
  status: () => call<AgentStatusPayload>("/status"),
  clusters: () => call<unknown[]>("/clusters"),
  plots: (clusterId: string) => call<unknown[]>(`/clusters/${encodeURIComponent(clusterId)}/plots`),
  evidence: (clusterId: string) => call<Json>(`/clusters/${encodeURIComponent(clusterId)}/evidence`),
  /** Agent runs call a language model and several tools; allow two minutes. */
  run: (clusterId: string, question: string) =>
    call<unknown>("/runs", { method: "POST", body: { clusterId, question }, timeoutMs: 120_000 }),
};
