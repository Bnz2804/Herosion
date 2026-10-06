import { Router, type IRouter } from "express";
import { GetAuditEventsResponse } from "@workspace/api-zod";
import { listAuditEvents } from "../audit/auditRepository";

const router: IRouter = Router();

router.get("/audit", async (_req, res): Promise<void> => {
  res.json(GetAuditEventsResponse.parse(await listAuditEvents()));
});

export default router;
