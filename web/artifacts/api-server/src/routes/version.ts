import { Router, type IRouter } from "express";
import { agentService } from "../agent/agentServiceClient";

/** Which build is actually running? Open /api/version in the browser (behind the same login). */
export const WEB_BUILD = "2026-10-08-e";
const router: IRouter = Router();

router.get("/version", async (_req, res): Promise<void> => {
  let agent: unknown = "unreachable";
  try {
    agent = (await agentService.status() as unknown as Record<string, unknown>)["agentBuild"] ?? "unknown (agent is older than build 2026-10-08-e)";
  } catch {
    /* reported as unreachable */
  }
  res.json({ web: WEB_BUILD, agent, expected: "2026-10-08-e for both" });
});

export default router;
