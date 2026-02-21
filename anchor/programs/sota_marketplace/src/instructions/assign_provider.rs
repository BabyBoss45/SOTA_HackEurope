use anchor_lang::prelude::*;
use crate::state::{Job, JobStatus};
use crate::errors::SotaError;
use crate::events::ProviderAssigned;

#[derive(Accounts)]
pub struct AssignProvider<'info> {
    #[account(
        mut,
        seeds = [b"job", job.id.to_le_bytes().as_ref()],
        bump = job.bump,
    )]
    pub job: Account<'info, Job>,

    pub poster: Signer<'info>,

    /// CHECK: Provider can be any valid pubkey
    pub provider: UncheckedAccount<'info>,
}

pub fn handler(ctx: Context<AssignProvider>) -> Result<()> {
    let job = &mut ctx.accounts.job;

    require!(job.poster == ctx.accounts.poster.key(), SotaError::NotPoster);
    require!(job.status == JobStatus::Open, SotaError::NotOpen);
    require!(ctx.accounts.provider.key() != Pubkey::default(), SotaError::ZeroProvider);

    job.provider = ctx.accounts.provider.key();
    job.status = JobStatus::Assigned;

    emit!(ProviderAssigned {
        job_id: job.id,
        provider: ctx.accounts.provider.key(),
    });

    Ok(())
}
