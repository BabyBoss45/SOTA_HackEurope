-- Rename legacy "neofsUri" column to "storageUri" to match Prisma schema
ALTER TABLE "CallSummary" RENAME COLUMN "neofsUri" TO "storageUri";
