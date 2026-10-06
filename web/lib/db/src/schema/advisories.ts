import { createInsertSchema } from "drizzle-zod";
import { jsonb, pgTable, text, timestamp, unique } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const advisoriesTable = pgTable("advisories", {
  // Provenance for agent_draft rows (null for manual_officer drafts).
  // submittedBy = the human who forwarded the agent output for review; they cannot approve it.
  id: text("id").primaryKey(),
  clusterId: text("cluster_id").notNull(),
  title: text("title").notNull(),
  recommendation: text("recommendation").notNull(),
  rationale: text("rationale").notNull(),
  status: text("status").notNull().default("draft"),
  origin: text("origin").notNull().default("manual_officer"),
  authoredBy: text("authored_by").notNull(),
  submittedBy: text("submitted_by"),
  agentRunId: text("agent_run_id"),
  agentHouseholdId: text("agent_household_id"),
  evidenceSnapshot: jsonb("evidence_snapshot").$type<
    Array<{ evidenceId: string; label: string; sourceName: string; sourceRecordId: string; dataTier: "local_test_data" }>
  >(),
  approvedBy: text("approved_by"),
  approvalNote: text("approval_note"),
  evidenceIds: text("evidence_ids").array().notNull(),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
  approvedAt: timestamp("approved_at", { withTimezone: true }),
}, (t) => [unique("advisories_agent_run_household_uq").on(t.agentRunId, t.agentHouseholdId)]);

export const insertAdvisorySchema = createInsertSchema(advisoriesTable).omit({
  createdAt: true,
  approvedAt: true,
});
export type InsertAdvisory = z.infer<typeof insertAdvisorySchema>;
export type AdvisoryRow = typeof advisoriesTable.$inferSelect;
