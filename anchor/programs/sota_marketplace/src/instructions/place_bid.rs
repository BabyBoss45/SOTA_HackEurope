use anchor_lang::prelude::*;
use crate::state::{MarketplaceConfig, Job, Bid, JobStatus};
use crate::errors::SotaError;
use crate::events::BidPlaced;

#[derive(Accounts)]
pub struct PlaceBid<'info> {
    #[account(
        mut,
        seeds = [b"config"],
        bump = config.bump,
    )]
    pub config: Account<'info, MarketplaceConfig>,

    #[account(
        mut,
        seeds = [b"job", job.id.to_le_bytes().as_ref()],
        bump = job.bump,
    )]
    pub job: Account<'info, Job>,

    #[account(
        init,
        payer = agent,
        space = 8 + Bid::INIT_SPACE,
        seeds = [b"bid", config.next_bid_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub bid: Account<'info, Bid>,

    #[account(mut)]
    pub agent: Signer<'info>,

    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<PlaceBid>,
    price_usdc: u64,
    estimated_time: u64,
    proposal: String,
) -> Result<()> {
    let job = &ctx.accounts.job;
    require!(job.status == JobStatus::Open, SotaError::NotOpen);

    let clock = Clock::get()?;
    require!(clock.unix_timestamp < job.deadline, SotaError::DeadlinePassed);
    require!(price_usdc > 0, SotaError::ZeroBid);
    require!(price_usdc <= job.max_budget_usdc, SotaError::BidExceedsBudget);
    require!(ctx.accounts.agent.key() != job.poster, SotaError::PosterCannotBid);

    let config = &mut ctx.accounts.config;
    let bid_id = config.next_bid_id;
    config.next_bid_id = bid_id.checked_add(1).ok_or(SotaError::Overflow)?;

    let bid = &mut ctx.accounts.bid;
    bid.id = bid_id;
    bid.job_id = job.id;
    bid.agent = ctx.accounts.agent.key();
    bid.price_usdc = price_usdc;
    bid.estimated_time = estimated_time;
    bid.proposal = proposal;
    bid.accepted = false;
    bid.created_at = clock.unix_timestamp;
    bid.bump = ctx.bumps.bid;

    emit!(BidPlaced {
        job_id: job.id,
        bid_id,
        agent: ctx.accounts.agent.key(),
        price_usdc,
    });

    Ok(())
}
