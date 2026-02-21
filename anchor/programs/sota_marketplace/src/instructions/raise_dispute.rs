use anchor_lang::prelude::*;
use crate::state::{Job, Deposit, JobStatus};
use crate::errors::SotaError;
use crate::events::JobDisputed;

pub const DISPUTE_DEADLINE: i64 = 3600; // 1 hour after delivery confirmation

#[derive(Accounts)]
pub struct RaiseDispute<'info> {
    #[account(
        mut,
        seeds = [b"job", job.id.to_le_bytes().as_ref()],
        bump = job.bump,
    )]
    pub job: Account<'info, Job>,

    #[account(
        seeds = [b"deposit", job.id.to_le_bytes().as_ref()],
        bump = deposit.bump,
        constraint = deposit.job_id == job.id,
    )]
    pub deposit: Account<'info, Deposit>,

    pub signer: Signer<'info>,
}

pub fn handler(ctx: Context<RaiseDispute>) -> Result<()> {
    let job = &mut ctx.accounts.job;
    let deposit = &ctx.accounts.deposit;
    let signer = ctx.accounts.signer.key();

    require!(
        signer == job.poster || signer == job.provider,
        SotaError::NotParty
    );
    require!(
        job.status == JobStatus::Completed,
        SotaError::InvalidStatus
    );

    // Dispute must happen within DISPUTE_DEADLINE seconds of delivery confirmation
    if deposit.delivery_confirmed && deposit.delivery_confirmed_at > 0 {
        let clock = Clock::get()?;
        require!(
            clock.unix_timestamp <= deposit.delivery_confirmed_at + DISPUTE_DEADLINE,
            SotaError::CannotDispute
        );
    }

    job.status = JobStatus::Disputed;

    emit!(JobDisputed {
        job_id: job.id,
        disputed_by: signer,
    });

    Ok(())
}
