import { randomUUID } from "node:crypto";
import { Router, type IRouter } from "express";
import { and, desc, eq } from "drizzle-orm";
import {
  CreateEvidenceRunResponse,
  SubmitAgentDraftsBody,
  SubmitAgentDraftsParams,
  SubmitAgentDraftsResponse,
  ApproveAdvisoryBody,
  ApproveAdvisoryParams,
  ApproveAdvisoryResponse,
  CreateManualAdvisoryBody,
  CreateManualAdvisoryResponse,
  GetAdvisoriesResponse,
} from "@workspace/api-zod";
import {
  advisoriesTable,
  agentRunsTable,
  auditEventsTable,
  db,
  type AdvisoryRow,
} from "@workspace/db";
import {
  findCluster,
  getAdvisoryEvidence,
  getEvidenceItems,
} from "../evidence/evidenceRepository";

const router: IRouter = Router();

async function toApiAdvisory(row: AdvisoryRow) {
  // Agent drafts carry a frozen snapshot of the evidence they cited, so the record stays
  // reviewable even if the underlying data later changes. Manual drafts look evidence up live.
  const evidence = row.evidenceSnapshot ?? (await getAdvisoryEvidence(row.evidenceIds, row.clusterId));
  return {
    advisoryId: row.id,
    clusterId: row.clusterId,
    title: row.title,
    recommendation: row.recommendation,
    rationale: row.rationale,
    status: row.status,
    origin: row.origin,
    authoredBy: row.authoredBy,
    submittedBy: row.submittedBy,
    agentRunId: row.agentRunId,
    approvedBy: row.approvedBy,
    approvalNote: row.approvalNote,
    evidence: evidence.map((item) => ({
      evidenceId: item.evidenceId,
      label: item.label,
      sourceName: item.sourceName,
      sourceRecordId: item.sourceRecordId,
      dataTier: item.dataTier,
    })),
    createdAt: row.createdAt.toISOString(),
    approvedAt: row.approvedAt?.toISOString() ?? null,
  };
}

router.get("/advisories", async (_req, res): Promise<void> => {
  const rows = await db
    .select()
    .from(advisoriesTable)
    .orderBy(desc(advisoriesTable.createdAt));
  const advisories = await Promise.all(rows.map(toApiAdvisory));
  res.json(GetAdvisoriesResponse.parse(advisories));
});

router.post("/advisories/manual", async (req, res): Promise<void> => {
  const parsed = CreateManualAdvisoryBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const input = parsed.data;
  const authoredBy = input.authoredBy.trim();
  if (authoredBy.length < 2) {
    res.status(400).json({ error: "Enter the author's full name" });
    return;
  }
  if (!(await findCluster(input.clusterId))) {
    res.status(404).json({ error: "Cluster not found" });
    return;
  }
  if (new Set(input.evidenceIds).size !== input.evidenceIds.length) {
    res.status(400).json({ error: "Evidence may only be attached once" });
    return;
  }
  const availableEvidence = new Set(
    (await getEvidenceItems(input.clusterId)).map((item) => item.evidenceId),
  );
  if (input.evidenceIds.some((id) => !availableEvidence.has(id))) {
    res.status(400).json({
      error: "Every cited evidence item must exist in the selected cluster",
    });
    return;
  }

  const advisoryId = randomUUID();
  const [row] = await db.transaction(async (tx) => {
    const [created] = await tx
      .insert(advisoriesTable)
      .values({
        id: advisoryId,
        clusterId: input.clusterId,
        title: input.title.trim(),
        recommendation: input.recommendation.trim(),
        rationale: input.rationale.trim(),
        status: "draft",
        origin: "manual_officer",
        authoredBy,
        evidenceIds: input.evidenceIds,
      })
      .returning();

    await tx.insert(auditEventsTable).values({
      id: randomUUID(),
      eventType: "advisory_drafted",
      actor: authoredBy,
      summary: `Created an officer-authored draft for ${input.clusterId} with ${input.evidenceIds.length} cited evidence records.`,
      advisoryId,
    });
    return [created];
  });

  res.status(201).json(
    CreateManualAdvisoryResponse.parse(await toApiAdvisory(row)),
  );
});

router.post("/advisories/:advisoryId/approve", async (req, res): Promise<void> => {
  const params = ApproveAdvisoryParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const parsed = ApproveAdvisoryBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const officerName = parsed.data.officerName.trim();
  if (officerName.length < 2) {
    res.status(400).json({ error: "Enter the approving officer's full name" });
    return;
  }

  const outcome = await db.transaction(async (tx) => {
    const [existing] = await tx
      .select()
      .from(advisoriesTable)
      .where(eq(advisoriesTable.id, params.data.advisoryId))
      .for("update")
      .limit(1);
    if (!existing) return { kind: "not_found" as const };
    if (existing.status !== "draft") return { kind: "conflict" as const };
    const approver = officerName.toLocaleLowerCase();
    if (
      existing.authoredBy.trim().toLocaleLowerCase() === approver ||
      existing.submittedBy?.trim().toLocaleLowerCase() === approver
    ) {
      return { kind: "same_officer" as const };
    }

    const [updated] = await tx
      .update(advisoriesTable)
      .set({
        status: "approved",
        approvedBy: officerName,
        approvalNote: parsed.data.approvalNote?.trim() || null,
        approvedAt: new Date(),
      })
      .where(
        and(
          eq(advisoriesTable.id, params.data.advisoryId),
          eq(advisoriesTable.status, "draft"),
        ),
      )
      .returning();

    if (!updated) return { kind: "conflict" as const };
    await tx.insert(auditEventsTable).values({
      id: randomUUID(),
      eventType: "advisory_approved",
      actor: officerName,
      summary: `Approved draft “${existing.title}” for ${existing.clusterId}. Approval does not send advice to a farmer.`,
      advisoryId: existing.id,
    });
    return { kind: "approved" as const, row: updated };
  });

  if (outcome.kind === "not_found") {
    res.status(404).json({ error: "Advisory not found" });
    return;
  }
  if (outcome.kind === "conflict") {
    res.status(409).json({ error: "This advisory is no longer awaiting approval" });
    return;
  }
  if (outcome.kind === "same_officer") {
    res.status(400).json({
      error: "A different named officer (not the author or the officer who submitted it) must approve this draft",
    });
    return;
  }
  res.json(ApproveAdvisoryResponse.parse(await toApiAdvisory(outcome.row)));
});

const ACTIONABLE = {
  delay_planting: {
    label: "Consider delaying planting",
    text: "Consider delaying planting on this plot until recent rainfall and the forecast support crop establishment.",
  },
  proceed_with_planting: {
    label: "Planting may proceed",
    text: "Planting may proceed as planned, subject to the officer's confirmation of field conditions.",
  },
  already_planted_monitor: {
    label: "Planted: monitor establishment",
    text: "Field is already planted: monitor crop establishment, soil moisture and pest pressure.",
  },
} as const;

router.post("/agent/runs/:runId/advisories", async (req, res): Promise<void> => {
  const params = SubmitAgentDraftsParams.safeParse(req.params);
  const body = SubmitAgentDraftsBody.safeParse(req.body);
  if (!params.success || !body.success) {
    res.status(400).json({ error: (params.success ? body : params).error?.message });
    return;
  }
  const officer = body.data.officerName.trim();
  if (officer.length < 2) {
    res.status(400).json({ error: "Enter the submitting officer's full name" });
    return;
  }
  const [stored] = await db
    .select()
    .from(agentRunsTable)
    .where(eq(agentRunsTable.id, params.data.runId))
    .limit(1);
  if (!stored) {
    res.status(404).json({ error: "Agent run not found" });
    return;
  }
  const run = CreateEvidenceRunResponse.parse(stored.payload);
  const recs = new Map((run.householdRecommendations ?? []).map((r) => [r.householdId, r]));
  const evidenceById = new Map(run.evidence.map((e) => [e.evidenceId, e]));
  const ids = [...new Set(body.data.householdIds)];

  const problems: string[] = [];
  for (const id of ids) {
    const rec = recs.get(id);
    if (!rec) problems.push(`${id} is not part of this run`);
    else if (!(rec.recommendation in ACTIONABLE))
      problems.push(`${id}: '${rec.recommendation}' cannot be saved as a draft`);
    else if (!rec.evidenceIds.some((e) => evidenceById.has(e)))
      problems.push(`${id}: no cited evidence available`);
  }
  if (problems.length > 0) {
    res.status(400).json({ error: problems.join("; ") });
    return;
  }

  const existing = await db
    .select({ household: advisoriesTable.agentHouseholdId })
    .from(advisoriesTable)
    .where(eq(advisoriesTable.agentRunId, run.runId));
  const taken = ids.filter((id) => existing.some((e) => e.household === id));
  if (taken.length > 0) {
    res.status(409).json({ error: `Draft already exists for ${taken.join(", ")} from this run` });
    return;
  }

  const author = `Extension agent (${run.modelName ?? "model unknown"})`;
  try {
    const rows = await db.transaction(async (tx) => {
      const created: AdvisoryRow[] = [];
      for (const id of ids) {
        const rec = recs.get(id)!;
        const kind = ACTIONABLE[rec.recommendation as keyof typeof ACTIONABLE];
        const cited = rec.evidenceIds.map((e) => evidenceById.get(e)).filter((e) => e !== undefined);
        const advisoryId = randomUUID();
        const [row] = await tx
          .insert(advisoriesTable)
          .values({
            id: advisoryId,
            clusterId: run.clusterId,
            title: `${kind.label} · ${rec.householdId}`.slice(0, 160),
            recommendation: `${kind.text} (Agent draft; requires approval.)`,
            rationale: [
              rec.rationale,
              rec.missingData.length ? `Missing data: ${rec.missingData.join(", ")}.` : "",
              `Source: agent run ${run.runId}; tool log ${(rec.auditCallIds ?? []).join(", ") || "n/a"}.`,
            ].filter(Boolean).join("\n\n").slice(0, 3000),
            status: "draft",
            origin: "agent_draft",
            authoredBy: author,
            submittedBy: officer,
            agentRunId: run.runId,
            agentHouseholdId: rec.householdId,
            evidenceIds: cited.map((e) => e.evidenceId),
            evidenceSnapshot: cited.map((e) => ({
              evidenceId: e.evidenceId, label: e.label, sourceName: e.sourceName,
              sourceRecordId: e.sourceRecordId, dataTier: e.dataTier,
            })),
          })
          .returning();
        await tx.insert(auditEventsTable).values({
          id: randomUUID(),
          eventType: "agent_draft_submitted",
          actor: officer,
          summary: `Submitted agent recommendation '${rec.recommendation}' for ${rec.householdId} (run ${run.runId}) as a draft with ${cited.length} cited evidence records. Awaiting a different officer's approval.`,
          advisoryId,
        });
        created.push(row);
      }
      return created;
    });
    res.status(201).json(SubmitAgentDraftsResponse.parse(await Promise.all(rows.map(toApiAdvisory))));
  } catch (err) {
    const code = (err as { code?: string; cause?: { code?: string } }).code ?? (err as { cause?: { code?: string } }).cause?.code;
    if (code === "23505") {
      res.status(409).json({ error: "A draft for one of these households already exists for this run" });
      return;
    }
    throw err;
  }
});

export default router;
