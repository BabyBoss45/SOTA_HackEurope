use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};
use crate::state::{MarketplaceConfig, Job, JobStatus, Deposit, Reputation};
use crate::errors::SotaError;
use crate::events::{PaymentRefunded, ReputationUpdated};

#[derive(Accounts)]
pub struct Refund<'info> {
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
        mut,
        seeds = [b"escrow_vault", deposit.job_id.to_le_bytes().as_ref()],
        bump,
        token::mint = config.usdc_mint,
        token::authority = deposit,
    )]
    pub escrow_vault: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = poster_ata.owner == deposit.poster,
        constraint = poster_ata.mint == config.usdc_mint,
    )]
    pub poster_ata: Account<'info, TokenAccount>,

    #[account(
        mut,
        seeds = [b"reputation", deposit.provider.as_ref()],
        bump = reputation.bump,
    )]
    pub reputation: Account<'info, Reputation>,

    #[account(
        constraint = authority.key() == config.authority @ SotaError::Unauthorized
    )]
    pub authority: Signer<'info>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<Refund>) -> Result<()> {
    let job = &ctx.accounts.job;
    require!(
        job.status == JobStatus::Open || job.status == JobStatus::Assigned || job.status == JobStatus::Disputed,
        SotaError::InvalidStatus
    );

    let deposit = &ctx.accounts.deposit;

    require!(
        deposit.funded && !deposit.released && !deposit.refunded,
        SotaError::InvalidEscrowState
    );

    // Transfer USDC back to poster
    let job_id_bytes = deposit.job_id.to_le_bytes();
    let bump_slice = [deposit.bump];
    let deposit_seeds: &[&[u8]] = &[b"deposit", job_id_bytes.as_ref(), &bump_slice];
    let signer_seeds = &[deposit_seeds];

    let cpi_accounts = Transfer {
        from: ctx.accounts.escrow_vault.to_account_info(),
        to: ctx.accounts.poster_ata.to_account_info(),
        authority: ctx.accounts.deposit.to_account_info(),
    };
    let cpi_ctx = CpiContext::new_with_signer(
        ctx.accounts.token_program.to_account_info(),
        cpi_accounts,
        signer_seeds,
    );
    token::transfer(cpi_ctx, deposit.amount)?;

    // Update deposit
    let deposit = &mut ctx.accounts.deposit;
    deposit.refunded = true;

    // Transition job to Cancelled
    let job = &mut ctx.accounts.job;
    job.status = JobStatus::Cancelled;

    // Update reputation: score -= 5 (floor at 0)
    let reputation = &mut ctx.accounts.reputation;
    reputation.score = reputation.score.saturating_sub(5);
    reputation.jobs_failed = reputation.jobs_failed.checked_add(1).ok_or(SotaError::Overflow)?;
    let clock = Clock::get()?;
    reputation.last_updated = clock.unix_timestamp;

    emit!(PaymentRefunded {
        job_id: deposit.job_id,
        poster: deposit.poster,
        amount: deposit.amount,
    });

    emit!(ReputationUpdated {
        agent: deposit.provider,
        score: reputation.score,
        jobs_completed: reputation.jobs_completed,
        jobs_failed: reputation.jobs_failed,
    });

    Ok(())
}
