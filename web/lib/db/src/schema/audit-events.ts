import { createInsertSchema } from "drizzle-zod";
import { pgTable, text, timestamp } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const auditEventsTable = pgTable("audit_events", {
  id: text("id").primaryKey(),
  eventType: text("event_type").notNull(),
  actor: text("actor").notNull(),
  summary: text("summary").notNull(),
  advisoryId: text("advisory_id"),
  occurredAt: timestamp("occurred_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const insertAuditEventSchema = createInsertSchema(auditEventsTable).omit({
  occurredAt: true,
});
export type InsertAuditEvent = z.infer<typeof insertAuditEventSchema>;
export type AuditEventRow = typeof auditEventsTable.$inferSelect;
