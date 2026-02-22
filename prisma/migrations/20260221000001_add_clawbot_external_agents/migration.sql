-- ClawBot External Agent Marketplace
-- Adds ExternalAgent, ExecutionToken, ExternalAgentReputation, Dispute models

-- ExternalAgent registry
CREATE TABLE "ExternalAgent" (
    "id"               SERIAL PRIMARY KEY,
    "agentId"          TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "name"             TEXT NOT NULL,
    "description"      TEXT NOT NULL,
    "endpoint"         TEXT NOT NULL,
    "capabilities"     TEXT[] NOT NULL DEFAULT '{}',
    "supportedDomains" TEXT[] NOT NULL DEFAULT '{}',
    "walletAddress"    TEXT NOT NULL,
    "publicKey"        TEXT,
    "status"           TEXT NOT NULL DEFAULT 'pending',
    "verifiedAt"       TIMESTAMP(3),
    "createdAt"        TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt"        TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX "ExternalAgent_agentId_key" ON "ExternalAgent"("agentId");
CREATE INDEX "ExternalAgent_status_idx" ON "ExternalAgent"("status");
CREATE INDEX "ExternalAgent_walletAddress_idx" ON "ExternalAgent"("walletAddress");

-- Single-use execution tokens (anti-replay)
CREATE TABLE "ExecutionToken" (
    "id"                  SERIAL PRIMARY KEY,
    "token"               TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "jobId"               TEXT NOT NULL,
    "agentId"             TEXT NOT NULL,
    "expiresAt"           TIMESTAMP(3) NOT NULL,
    "used"                BOOLEAN NOT NULL DEFAULT false,
    "usedAt"              TIMESTAMP(3),
    "confidenceSubmitted" DOUBLE PRECISION,
    "createdAt"           TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ExecutionToken_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "ExternalAgent"("agentId") ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "ExecutionToken_token_key" ON "ExecutionToken"("token");
CREATE INDEX "ExecutionToken_token_idx" ON "ExecutionToken"("token");
CREATE INDEX "ExecutionToken_jobId_idx" ON "ExecutionToken"("jobId");
CREATE INDEX "ExecutionToken_agentId_idx" ON "ExecutionToken"("agentId");

-- Per-agent reputation metrics
CREATE TABLE "ExternalAgentReputation" (
    "id"                 SERIAL PRIMARY KEY,
    "agentId"            TEXT NOT NULL,
    "totalJobs"          INTEGER NOT NULL DEFAULT 0,
    "successfulJobs"     INTEGER NOT NULL DEFAULT 0,
    "failedJobs"         INTEGER NOT NULL DEFAULT 0,
    "avgExecutionTimeMs" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "avgConfidenceError" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "failureTypes"       JSONB NOT NULL DEFAULT '{}',
    "disputes"           INTEGER NOT NULL DEFAULT 0,
    "reputationScore"    DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    "updatedAt"          TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ExternalAgentReputation_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "ExternalAgent"("agentId") ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "ExternalAgentReputation_agentId_key" ON "ExternalAgentReputation"("agentId");

-- Dispute handling
CREATE TABLE "Dispute" (
    "id"         SERIAL PRIMARY KEY,
    "jobId"      TEXT NOT NULL,
    "raisedBy"   TEXT NOT NULL,
    "agentId"    TEXT NOT NULL,
    "reason"     TEXT NOT NULL,
    "status"     TEXT NOT NULL DEFAULT 'open',
    "resolution" TEXT,
    "logs"       JSONB,
    "createdAt"  TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "resolvedAt" TIMESTAMP(3)
);

CREATE INDEX "Dispute_jobId_idx" ON "Dispute"("jobId");
CREATE INDEX "Dispute_agentId_idx" ON "Dispute"("agentId");
CREATE INDEX "Dispute_status_idx" ON "Dispute"("status");
