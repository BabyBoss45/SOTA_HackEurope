use anchor_lang::prelude::*;
use crate::state::{Job, JobStatus};
use crate::errors::SotaError;
use crate::events::JobCompletedEvent;

#[derive(Accounts)]
pub struct MarkCompleted<'info> {
    #[account(
        mut,
        seeds = [b"job", job.id.to_le_bytes().as_ref()],
        bump = job.bump,
    )]
    pub job: Account<'info, Job>,

    pub signer: Signer<'info>,
}

pub fn handler(ctx: Context<MarkCompleted>, delivery_proof: [u8; 32]) -> Result<()> {
    let job = &mut ctx.accounts.job;
    let signer = ctx.accounts.signer.key();

    require!(signer == job.provider, SotaError::Unauthorized);
    require!(job.status == JobStatus::Assigned, SotaError::NotAssigned);

    job.status = JobStatus::Completed;
    job.delivery_proof = delivery_proof;

    emit!(JobCompletedEvent {
        job_id: job.id,
        delivery_proof,
    });

    Ok(())
}
