use anchor_lang::prelude::*;
use crate::state::{MarketplaceConfig, Job, JobStatus};
use crate::errors::SotaError;
use crate::events::JobCreated;

#[derive(Accounts)]
pub struct CreateJob<'info> {
    #[account(
        mut,
        seeds = [b"config"],
        bump = config.bump,
    )]
    pub config: Account<'info, MarketplaceConfig>,

    #[account(
        init,
        payer = poster,
        space = 8 + Job::INIT_SPACE,
        seeds = [b"job", config.next_job_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub job: Account<'info, Job>,

    #[account(mut)]
    pub poster: Signer<'info>,

    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<CreateJob>,
    metadata_uri: String,
    max_budget_usdc: u64,
    deadline: i64,
) -> Result<()> {
    require!(max_budget_usdc > 0, SotaError::ZeroBudget);

    let clock = Clock::get()?;
    require!(deadline > clock.unix_timestamp, SotaError::PastDeadline);

    let config = &mut ctx.accounts.config;
    let job_id = config.next_job_id;
    config.next_job_id = job_id.checked_add(1).ok_or(SotaError::Overflow)?;

    let job = &mut ctx.accounts.job;
    job.id = job_id;
    job.poster = ctx.accounts.poster.key();
    job.provider = Pubkey::default();
    job.metadata_uri = metadata_uri;
    job.max_budget_usdc = max_budget_usdc;
    job.deadline = deadline;
    job.status = JobStatus::Open;
    job.delivery_proof = [0u8; 32];
    job.created_at = clock.unix_timestamp;
    job.accepted_bid_id = 0;
    job.bump = ctx.bumps.job;

    emit!(JobCreated {
        job_id,
        poster: ctx.accounts.poster.key(),
        max_budget_usdc,
    });

    Ok(())
}
