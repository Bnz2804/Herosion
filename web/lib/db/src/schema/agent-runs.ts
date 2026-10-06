import { jsonb, pgTable, text, timestamp } from "drizzle-orm/pg-core";

/** Full agent run as returned by the agent service, stored so drafts can only cite what the run found. */
export const agentRunsTable = pgTable("agent_runs", {
  id: text("id").primaryKey(),
  clusterId: text("cluster_id").notNull(),
  question: text("question").notNull(),
  payload: jsonb("payload").$type<Record<string, unknown>>().notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});
export type AgentRunRow = typeof agentRunsTable.$inferSelect;
