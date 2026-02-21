use anchor_lang::prelude::*;

#[event]
pub struct JobCreated {
    pub job_id: u64,
    pub poster: Pubkey,
    pub max_budget_usdc: u64,
}

#[event]
pub struct BidPlaced {
    pub job_id: u64,
    pub bid_id: u64,
    pub agent: Pubkey,
    pub price_usdc: u64,
}

#[event]
pub struct BidAccepted {
    pub job_id: u64,
    pub bid_id: u64,
    pub provider: Pubkey,
}

#[event]
pub struct ProviderAssigned {
    pub job_id: u64,
    pub provider: Pubkey,
}

#[event]
pub struct JobCompletedEvent {
    pub job_id: u64,
    pub delivery_proof: [u8; 32],
}

#[event]
pub struct JobReleased {
    pub job_id: u64,
    pub provider: Pubkey,
    pub amount: u64,
}

#[event]
pub struct JobCancelled {
    pub job_id: u64,
}

#[event]
pub struct JobDisputed {
    pub job_id: u64,
    pub disputed_by: Pubkey,
}

#[event]
pub struct EscrowFunded {
    pub job_id: u64,
    pub poster: Pubkey,
    pub provider: Pubkey,
    pub amount: u64,
}

#[event]
pub struct DeliveryConfirmed {
    pub job_id: u64,
    pub confirmer: Pubkey,
    pub timestamp: i64,
}

#[event]
pub struct PaymentReleased {
    pub job_id: u64,
    pub provider: Pubkey,
    pub payout: u64,
    pub fee: u64,
}

#[event]
pub struct PaymentRefunded {
    pub job_id: u64,
    pub poster: Pubkey,
    pub amount: u64,
}

#[event]
pub struct AgentRegistered {
    pub agent: Pubkey,
    pub developer: Pubkey,
    pub name: String,
    pub metadata_uri: String,
}

#[event]
pub struct AgentUpdated {
    pub agent: Pubkey,
    pub name: String,
}

#[event]
pub struct ReputationUpdated {
    pub agent: Pubkey,
    pub score: u64,
    pub jobs_completed: u64,
    pub jobs_failed: u64,
}
