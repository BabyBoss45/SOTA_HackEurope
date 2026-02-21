use anchor_lang::prelude::*;

pub mod state;
pub mod errors;
pub mod events;
pub mod instructions;

use instructions::*;

declare_id!("EuGy9m9G5H5QNm3YaHQ26Peo5ZTABqWHk83R3AT2nYSD");

#[program]
pub mod sota_marketplace {
    use super::*;

    // ─── Admin ─────────────────────────────────────────────

    pub fn initialize(ctx: Context<Initialize>, platform_fee_bps: u16) -> Result<()> {
        instructions::initialize::handler(ctx, platform_fee_bps)
    }

    pub fn update_fee_config(ctx: Context<UpdateFeeConfig>, platform_fee_bps: u16) -> Result<()> {
        instructions::update_fee_config::handler(ctx, platform_fee_bps)
    }

    // ─── OrderBook ─────────────────────────────────────────

    pub fn create_job(
        ctx: Context<CreateJob>,
        metadata_uri: String,
        max_budget_usdc: u64,
        deadline: i64,
    ) -> Result<()> {
        instructions::create_job::handler(ctx, metadata_uri, max_budget_usdc, deadline)
    }

    pub fn place_bid(
        ctx: Context<PlaceBid>,
        price_usdc: u64,
        estimated_time: u64,
        proposal: String,
    ) -> Result<()> {
        instructions::place_bid::handler(ctx, price_usdc, estimated_time, proposal)
    }

    pub fn accept_bid(ctx: Context<AcceptBid>) -> Result<()> {
        instructions::accept_bid::handler(ctx)
    }

    pub fn assign_provider(ctx: Context<AssignProvider>) -> Result<()> {
        instructions::assign_provider::handler(ctx)
    }

    pub fn mark_completed(ctx: Context<MarkCompleted>, delivery_proof: [u8; 32]) -> Result<()> {
        instructions::mark_completed::handler(ctx, delivery_proof)
    }

    pub fn cancel_job(ctx: Context<CancelJob>) -> Result<()> {
        instructions::cancel_job::handler(ctx)
    }

    pub fn raise_dispute(ctx: Context<RaiseDispute>) -> Result<()> {
        instructions::raise_dispute::handler(ctx)
    }

    // ─── Escrow ────────────────────────────────────────────

    pub fn fund_job(ctx: Context<FundJob>, amount: u64) -> Result<()> {
        instructions::fund_job::handler(ctx, amount)
    }

    pub fn confirm_delivery(ctx: Context<ConfirmDelivery>) -> Result<()> {
        instructions::confirm_delivery::handler(ctx)
    }

    pub fn release_to_provider(ctx: Context<ReleaseToProvider>) -> Result<()> {
        instructions::release_to_provider::handler(ctx)
    }

    pub fn refund(ctx: Context<Refund>) -> Result<()> {
        instructions::refund::handler(ctx)
    }

    // ─── Registry ──────────────────────────────────────────

    pub fn register_agent(
        ctx: Context<RegisterAgent>,
        name: String,
        metadata_uri: String,
        capabilities: Vec<String>,
    ) -> Result<()> {
        instructions::register_agent::handler(ctx, name, metadata_uri, capabilities)
    }

    pub fn update_agent(
        ctx: Context<UpdateAgent>,
        name: String,
        metadata_uri: String,
        capabilities: Vec<String>,
        status: u8,
    ) -> Result<()> {
        instructions::update_agent::handler(ctx, name, metadata_uri, capabilities, status)
    }

    pub fn admin_update_status(ctx: Context<AdminUpdateStatus>, status: u8) -> Result<()> {
        instructions::admin_update_status::handler(ctx, status)
    }
}
