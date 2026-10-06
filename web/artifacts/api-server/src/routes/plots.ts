import { Router, type IRouter } from "express";
import {
  GetPlotFieldCandidatesParams,
  GetPlotFieldCandidatesResponse,
  MatchPlotFieldBody,
  MatchPlotFieldParams,
  MatchPlotFieldResponse,
} from "@workspace/api-zod";
import { agentService, AgentServiceError } from "../agent/agentServiceClient";
import { recordAuditEvent } from "../audit/auditRepository";
import { invalidateCache } from "../evidence/evidenceRepository";

const router: IRouter = Router();

function fail(err: unknown, res: import("express").Response): void {
  if (err instanceof AgentServiceError) {
    res.status(err.httpStatus).json({ error: err.message, code: err.code });
    return;
  }
  throw err;
}

router.get("/plots/:plotId/candidates", async (req, res): Promise<void> => {
  const params = GetPlotFieldCandidatesParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  try {
    res.json(GetPlotFieldCandidatesResponse.parse(await agentService.candidates(params.data.plotId)));
  } catch (err) {
    fail(err, res);
  }
});

router.post("/plots/:plotId/match", async (req, res): Promise<void> => {
  const params = MatchPlotFieldParams.safeParse(req.params);
  const body = MatchPlotFieldBody.safeParse(req.body);
  if (!params.success || !body.success) {
    res.status(400).json({ error: "Invalid plot, field or officer name" });
    return;
  }
  const officer = body.data.officerName.trim();
  try {
    const result = MatchPlotFieldResponse.parse(
      await agentService.match(params.data.plotId, body.data.candidateId, officer),
    );
    invalidateCache();
    await recordAuditEvent({
      eventType: "plot_matched",
      actor: officer,
      summary: `Confirmed field ${result.candidateId} as plot ${result.plotId} (was ${result.previousVerification}, now ${result.verificationLevel}; weather cell ${result.weatherCellId}). Earlier agent runs used the previous location.`,
    });
    res.json(result);
  } catch (err) {
    fail(err, res);
  }
});

export default router;
