import { timingSafeEqual } from "node:crypto";
import type { NextFunction, Request, Response } from "express";

/**
 * Access control for a publicly reachable test deployment.
 * - APP_BASIC_AUTH="user:password" protects the whole app (the browser shows its native login prompt).
 * - In production the app refuses to start without it, unless ALLOW_UNAUTHENTICATED=true is set explicitly.
 * Why: an open agent endpoint lets anyone spend your model-API credits.
 */
const safeEqual = (a: string, b: string) => {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
};

export function assertSecurityConfig(): void {
  if (process.env["NODE_ENV"] === "production" && !process.env["APP_BASIC_AUTH"] && process.env["ALLOW_UNAUTHENTICATED"] !== "true") {
    throw new Error("Set APP_BASIC_AUTH=user:password (or ALLOW_UNAUTHENTICATED=true for a private network only).");
  }
}

export function basicAuth(req: Request, res: Response, next: NextFunction): void {
  const expected = process.env["APP_BASIC_AUTH"];
  if (!expected || req.path === "/api/healthz") return next();
  const header = req.headers.authorization ?? "";
  const [scheme, encoded] = header.split(" ");
  if (scheme === "Basic" && encoded && safeEqual(Buffer.from(encoded, "base64").toString(), expected)) return next();
  res.set("WWW-Authenticate", 'Basic realm="Herosion extension workbench"').status(401).send("Authentication required");
}

/** Sliding-window cap on expensive agent runs (per process). */
export function runRateLimit(maxPerHour = Number(process.env["MAX_AGENT_RUNS_PER_HOUR"] ?? 30)) {
  const hits: number[] = [];
  return (_req: Request, res: Response, next: NextFunction): void => {
    const cutoff = Date.now() - 3_600_000;
    while (hits.length && hits[0]! < cutoff) hits.shift();
    if (hits.length >= maxPerHour) {
      res.status(429).json({ error: `Agent run limit reached (${maxPerHour}/hour). Try again later.` });
      return;
    }
    hits.push(Date.now());
    next();
  };
}

export function securityHeaders(_req: Request, res: Response, next: NextFunction): void {
  res.set({ "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin", "X-Frame-Options": "DENY" });
  next();
}
