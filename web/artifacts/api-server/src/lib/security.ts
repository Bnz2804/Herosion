import { timingSafeEqual } from "node:crypto";
import type { NextFunction, Request, Response } from "express";
import { logger } from "./logger";

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

/**
 * APP_BASIC_AUTH = "user:password". Tolerates the usual deployment-tool accidents:
 * surrounding whitespace/newlines and wrapping quotes. The password may itself contain ':'.
 */
function configuredCredentials(): { user: string; pass: string } | null {
  const raw = (process.env["APP_BASIC_AUTH"] ?? "").trim().replace(/^(["'])([\s\S]*)\1$/, "$2").trim();
  const i = raw.indexOf(":");
  if (!raw) return null;
  if (i < 1 || i === raw.length - 1) {
    throw new Error('APP_BASIC_AUTH must look like "username:password" (one colon, both parts non-empty).');
  }
  return { user: raw.slice(0, i), pass: raw.slice(i + 1) };
}

export function assertSecurityConfig(): void {
  const creds = configuredCredentials();
  if (creds) {
    // Safe to log: the username and the password LENGTH, never the password.
    logger.info(`Login enabled for user '${creds.user}' (password length ${creds.pass.length}).`);
    return;
  }
  if (process.env["NODE_ENV"] === "production" && process.env["ALLOW_UNAUTHENTICATED"] !== "true") {
    throw new Error("Set APP_BASIC_AUTH=user:password (or ALLOW_UNAUTHENTICATED=true for a private network only).");
  }
}

export function basicAuth(req: Request, res: Response, next: NextFunction): void {
  const creds = configuredCredentials();
  if (!creds || req.path === "/api/healthz") return next();
  const header = req.headers.authorization;
  let reason = "no_authorization_header (browser has not sent a login yet)";
  if (header) {
    const [scheme, encoded] = header.split(" ");
    if (scheme !== "Basic" || !encoded) {
      reason = "not_basic_scheme";
    } else {
      const decoded = Buffer.from(encoded, "base64").toString();
      const i = decoded.indexOf(":");
      if (i < 0) {
        reason = "malformed_credentials (no colon)";
      } else {
        const user = decoded.slice(0, i);
        const pass = decoded.slice(i + 1);
        if (safeEqual(user, creds.user) && safeEqual(pass, creds.pass)) return next();
        reason = !safeEqual(user, creds.user)
          ? `user_mismatch (sent user length ${user.length}, expected ${creds.user.length})`
          : `password_mismatch (sent length ${pass.length}, expected ${creds.pass.length})`;
      }
    }
  }
  logger.warn({ path: req.path, reason }, "login refused");
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
