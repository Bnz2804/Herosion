import { CreateEvidenceRunBody, CreateEvidenceRunResponse } from "@workspace/api-zod";
import { agentRunsTable, auditEventsTable, db } from "@workspace/db";
import { randomUUID } from "node:crypto";
import { recordAuditEvent } from "../audit/auditRepository";
import { agentService, AgentServiceError } from "./agentServiceClient";

type RunInput = ReturnType<typeof CreateEvidenceRunBody.parse>;

/**
 * Runs the tool-using agent (in the agent service) for one cluster question.
 *
 * Deliberately NOT a scripted pipeline: this function does not choose or order tools. The model
 * picks them over MCP; we only record what it actually did. Every tool call appears twice in the
 * audit trail: in the agent service's append-only tool log (referenced by auditCallId) and as an
 * audit event here, next to the officer actions.
 */
export async function runAgent(input: RunInput) {
  let run: ReturnType<typeof CreateEvidenceRunResponse.parse>;
  try {
    const raw = await agentService.run(input.clusterId, input.question);
    const parsed = CreateEvidenceRunResponse.safeParse(raw);
    if (!parsed.success) {
      throw new AgentServiceError(`Agent service returned an invalid run: ${parsed.error.message}`, 502, "bad_response");
    }
    run = parsed.data;
  } catch (err) {
    if (err instanceof AgentServiceError) {
      await recordAuditEvent({
        eventType: "agent_run_failed",
        actor: "System",
        summary: `Agent run for ${input.clusterId} failed (${err.code}): ${err.message}`.slice(0, 1000),
      });
    }
    throw err;
  }

  const agentActor = `Agent (${run.modelName ?? "model unknown"})`;
  // Postgres now() is constant inside a transaction; stamp events explicitly so they list in true order.
  const t0 = Date.now();
  await db.transaction(async (tx) => {
    await tx.insert(agentRunsTable).values({
      id: run.runId,
      clusterId: run.clusterId,
      question: run.question,
      payload: run as unknown as Record<string, unknown>,
    });
    // Explicit, strictly increasing timestamps: rows written in one transaction would otherwise
    // share `now()` and the trail could not be replayed in the order the agent acted.
    const t0 = Date.now();
    const events = [
      {
        eventType: "agent_run",
        summary: `Run ${run.runId} on ${run.clusterId}: ${run.toolCalls.length} tool calls, ${
          run.householdRecommendations?.length ?? 0
        } household recommendations (drafts only; nothing actioned).`,
      },
      ...run.toolCalls.map((call) => ({
        eventType: "agent_tool_call",
        summary: (`${call.toolName}(${call.arguments ?? "{}"}) → ${call.status}, ${call.resultCount} records` +
          `${call.auditCallId ? ` [tool log ${call.auditCallId}]` : ""}${call.decision ? `. Reason: ${call.decision}` : ""}`).slice(0, 900),
      })),
    ];
    await tx.insert(auditEventsTable).values(
      events.map((e, i) => ({
        id: randomUUID(),
        eventType: e.eventType,
        actor: agentActor,
        summary: e.summary,
        occurredAt: new Date(t0 + i),
      })),
    );
  });
  return run;
}
