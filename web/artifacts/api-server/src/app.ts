import express, { type Express } from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import path from "node:path";
import fs from "node:fs";
import router from "./routes";
import { assertSecurityConfig, basicAuth, runRateLimit, securityHeaders } from "./lib/security";
import { logger } from "./lib/logger";

assertSecurityConfig();
const app: Express = express();
app.set("trust proxy", 1); // behind Coolify/Traefik

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);
app.use(securityHeaders);
app.use(basicAuth);
app.use(cors({ origin: false })); // same-origin only; the UI is served by this process
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.post("/api/agent/runs", runRateLimit());
app.use("/api", router);

// Serve the built UI from the same origin (one public service; no CORS, no second domain).
const staticDir = process.env["STATIC_DIR"];
if (staticDir && fs.existsSync(staticDir)) {
  app.use(express.static(staticDir, { maxAge: "1h", index: false }));
  app.get(/^\/(?!api\/).*/, (_req, res) => res.sendFile(path.join(staticDir, "index.html")));
}

export default app;
