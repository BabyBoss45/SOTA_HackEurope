use anchor_lang::prelude::*;
use crate::state::{MarketplaceConfig, Deposit, Job, JobStatus};
use crate::errors::SotaError;
use crate::events::DeliveryConfirmed;

#[derive(Accounts)]
pub struct ConfirmDelivery<'info> {
    #[account(
        seeds = [b"config"],
        bump = config.bump,
    )]
    pub config: Account<'info, MarketplaceConfig>,

    #[account(
        mut,
        seeds = [b"deposit", deposit.job_id.to_le_bytes().as_ref()],
        bump = deposit.bump,
    )]
    pub deposit: Account<'info, Deposit>,

    #[account(
        mut,
        seeds = [b"job", deposit.job_id.to_le_bytes().as_ref()],
        bump = job.bump,
    )]
    pub job: Account<'info, Job>,

    #[account(
        constraint = authority.key() == config.authority @ SotaError::Unauthorized
    )]
    pub authority: Signer<'info>,
}

pub fn handler(ctx: Context<ConfirmDelivery>) -> Result<()> {
    let job = &ctx.accounts.job;
    require!(job.status == JobStatus::Completed, SotaError::InvalidStatus);

    let deposit = &mut ctx.accounts.deposit;

    require!(deposit.funded, SotaError::NotFunded);
    require!(!deposit.released && !deposit.refunded, SotaError::InvalidEscrowState);

    let clock = Clock::get()?;
    deposit.delivery_confirmed = true;
    deposit.delivery_confirmed_at = clock.unix_timestamp;

    emit!(DeliveryConfirmed {
        job_id: deposit.job_id,
        confirmer: ctx.accounts.authority.key(),
        timestamp: clock.unix_timestamp,
    });

    Ok(())
}
