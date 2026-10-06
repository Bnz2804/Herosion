import { desc, eq } from "drizzle-orm";
import { randomUUID } from "node:crypto";
import { auditEventsTable, db } from "@workspace/db";

export interface AuditEventInput {
  eventType: string;
  actor: string;
  summary: string;
  advisoryId?: string | null;
}

export async function recordAuditEvent(event: AuditEventInput): Promise<void> {
  await db.insert(auditEventsTable).values({
    id: randomUUID(),
    eventType: event.eventType,
    actor: event.actor,
    summary: event.summary,
    advisoryId: event.advisoryId ?? null,
  });
}

export async function listAuditEvents(advisoryId?: string) {
  const rows = advisoryId
    ? await db
        .select()
        .from(auditEventsTable)
        .where(eq(auditEventsTable.advisoryId, advisoryId))
        .orderBy(desc(auditEventsTable.occurredAt))
        .limit(100)
    : await db
        .select()
        .from(auditEventsTable)
        .orderBy(desc(auditEventsTable.occurredAt))
        .limit(100);

  return rows.map((row) => ({
    eventId: row.id,
    eventType: row.eventType,
    actor: row.actor,
    summary: row.summary,
    occurredAt: row.occurredAt.toISOString(),
    advisoryId: row.advisoryId,
    dataTier: "local_test_data" as const,
  }));
}
