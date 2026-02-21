use anchor_lang::prelude::*;
use crate::state::{Job, Bid, JobStatus};
use crate::errors::SotaError;
use crate::events::{BidAccepted, ProviderAssigned};

#[derive(Accounts)]
pub struct AcceptBid<'info> {
    #[account(
        mut,
        seeds = [b"job", job.id.to_le_bytes().as_ref()],
        bump = job.bump,
    )]
    pub job: Account<'info, Job>,

    #[account(
        mut,
        seeds = [b"bid", bid.id.to_le_bytes().as_ref()],
        bump = bid.bump,
    )]
    pub bid: Account<'info, Bid>,

    pub poster: Signer<'info>,
}

pub fn handler(ctx: Context<AcceptBid>) -> Result<()> {
    let job = &mut ctx.accounts.job;
    let bid = &mut ctx.accounts.bid;

    require!(job.poster == ctx.accounts.poster.key(), SotaError::NotPoster);
    require!(job.status == JobStatus::Open, SotaError::NotOpen);
    require!(bid.job_id == job.id, SotaError::BidJobMismatch);
    require!(!bid.accepted, SotaError::BidAlreadyAccepted);

    bid.accepted = true;
    job.provider = bid.agent;
    job.status = JobStatus::Assigned;
    job.accepted_bid_id = bid.id;

    emit!(BidAccepted {
        job_id: job.id,
        bid_id: bid.id,
        provider: bid.agent,
    });

    emit!(ProviderAssigned {
        job_id: job.id,
        provider: bid.agent,
    });

    Ok(())
}
