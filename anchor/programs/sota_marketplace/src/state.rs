use anchor_lang::prelude::*;

// ─── Enums ─────────────────────────────────────────────

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, InitSpace)]
pub enum JobStatus {
    Open,
    Assigned,
    Completed,
    Released,
    Cancelled,
    Disputed,
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, InitSpace)]
pub enum AgentStatus {
    Unregistered,
    Active,
    Inactive,
    Banned,
}

// ─── Accounts ──────────────────────────────────────────

/// Global marketplace configuration. PDA seeds: [b"config"]
#[account]
#[derive(InitSpace)]
pub struct MarketplaceConfig {
    pub authority: Pubkey,
    pub usdc_mint: Pubkey,
    pub fee_collector: Pubkey,
    pub platform_fee_bps: u16,    // 200 = 2%
    pub next_job_id: u64,
    pub next_bid_id: u64,
    pub bump: u8,
}

/// A job posted by a client. PDA seeds: [b"job", job_id.to_le_bytes()]
#[account]
#[derive(InitSpace)]
pub struct Job {
    pub id: u64,
    pub poster: Pubkey,
    pub provider: Pubkey,
    #[max_len(256)]
    pub metadata_uri: String,
    pub max_budget_usdc: u64,     // USDC with 6 decimals
    pub deadline: i64,
    pub status: JobStatus,
    pub delivery_proof: [u8; 32],
    pub created_at: i64,
    pub accepted_bid_id: u64,
    pub bump: u8,
}

/// A bid on a job. PDA seeds: [b"bid", bid_id.to_le_bytes()]
#[account]
#[derive(InitSpace)]
pub struct Bid {
    pub id: u64,
    pub job_id: u64,
    pub agent: Pubkey,
    pub price_usdc: u64,          // USDC with 6 decimals
    pub estimated_time: u64,      // seconds
    #[max_len(512)]
    pub proposal: String,
    pub accepted: bool,
    pub created_at: i64,
    pub bump: u8,
}

/// Escrow deposit for a job. PDA seeds: [b"deposit", job_id.to_le_bytes()]
#[account]
#[derive(InitSpace)]
pub struct Deposit {
    pub job_id: u64,
    pub poster: Pubkey,
    pub provider: Pubkey,
    pub amount: u64,
    pub funded: bool,
    pub released: bool,
    pub refunded: bool,
    pub delivery_confirmed: bool,
    pub delivery_confirmed_at: i64,
    pub bump: u8,
}

/// Agent profile. PDA seeds: [b"agent", wallet.as_ref()]
#[account]
#[derive(InitSpace)]
pub struct Agent {
    pub wallet: Pubkey,
    pub developer: Pubkey,
    #[max_len(64)]
    pub name: String,
    #[max_len(256)]
    pub metadata_uri: String,
    #[max_len(10, 64)]
    pub capabilities: Vec<String>,
    pub reputation: u64,
    pub status: AgentStatus,
    pub created_at: i64,
    pub updated_at: i64,
    pub bump: u8,
}

/// Reputation stats. PDA seeds: [b"reputation", wallet.as_ref()]
#[account]
#[derive(InitSpace)]
pub struct Reputation {
    pub wallet: Pubkey,
    pub score: u64,
    pub jobs_completed: u64,
    pub jobs_failed: u64,
    pub total_earned: u128,
    pub last_updated: i64,
    pub bump: u8,
}
