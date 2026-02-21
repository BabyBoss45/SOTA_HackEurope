use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};
use crate::state::{MarketplaceConfig, Job, Deposit, Reputation, JobStatus};
use crate::errors::SotaError;
use crate::events::{PaymentReleased, JobReleased, ReputationUpdated};

pub const DISPUTE_WINDOW: i64 = 3600; // 1 hour

#[derive(Accounts)]
pub struct ReleaseToProvider<'info> {
    #[account(
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
        mut,
        seeds = [b"deposit", deposit.job_id.to_le_bytes().as_ref()],
        bump = deposit.bump,
        constraint = deposit.job_id == job.id,
    )]
    pub deposit: Account<'info, Deposit>,

    #[account(
        mut,
        seeds = [b"escrow_vault", job.id.to_le_bytes().as_ref()],
        bump,
        token::mint = config.usdc_mint,
        token::authority = deposit,
    )]
    pub escrow_vault: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = provider_ata.owner == deposit.provider,
        constraint = provider_ata.mint == config.usdc_mint,
    )]
    pub provider_ata: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = fee_collector_ata.owner == config.fee_collector,
        constraint = fee_collector_ata.mint == config.usdc_mint,
    )]
    pub fee_collector_ata: Account<'info, TokenAccount>,

    #[account(
        mut,
        seeds = [b"reputation", deposit.provider.as_ref()],
        bump = reputation.bump,
    )]
    pub reputation: Account<'info, Reputation>,

    pub signer: Signer<'info>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<ReleaseToProvider>) -> Result<()> {
    let deposit = &ctx.accounts.deposit;
    let job = &ctx.accounts.job;
    let signer = ctx.accounts.signer.key();

    require!(deposit.funded, SotaError::NotFunded);
    require!(!deposit.released, SotaError::AlreadyReleased);
    require!(!deposit.refunded, SotaError::AlreadyRefunded);
    require!(deposit.delivery_confirmed, SotaError::DeliveryNotConfirmed);
    require!(
        signer == deposit.poster || signer == deposit.provider,
        SotaError::NotAuthorised
    );

    // Provider must wait for dispute window; poster can release immediately
    if signer == deposit.provider {
        let clock = Clock::get()?;
        require!(
            clock.unix_timestamp >= deposit.delivery_confirmed_at + DISPUTE_WINDOW,
            SotaError::DisputeWindowActive
        );
    }

    // Verify job is in COMPLETED state (not disputed)
    require!(job.status == JobStatus::Completed, SotaError::JobNotCompleted);

    // Calculate fee and payout
    let fee = (deposit.amount as u128)
        .checked_mul(ctx.accounts.config.platform_fee_bps as u128)
        .ok_or(SotaError::Overflow)?
        .checked_div(10_000)
        .ok_or(SotaError::Overflow)? as u64;
    let payout = deposit.amount.checked_sub(fee).ok_or(SotaError::Overflow)?;

    // PDA signer seeds for deposit (escrow vault authority)
    let job_id_bytes = deposit.job_id.to_le_bytes();
    let bump_slice = [deposit.bump];
    let deposit_seeds: &[&[u8]] = &[b"deposit", job_id_bytes.as_ref(), &bump_slice];
    let signer_seeds = &[deposit_seeds];

    // Transfer fee to fee collector
    if fee > 0 {
        let cpi_accounts = Transfer {
            from: ctx.accounts.escrow_vault.to_account_info(),
            to: ctx.accounts.fee_collector_ata.to_account_info(),
            authority: ctx.accounts.deposit.to_account_info(),
        };
        let cpi_ctx = CpiContext::new_with_signer(
            ctx.accounts.token_program.to_account_info(),
            cpi_accounts,
            signer_seeds,
        );
        token::transfer(cpi_ctx, fee)?;
    }

    // Transfer payout to provider
    let cpi_accounts = Transfer {
        from: ctx.accounts.escrow_vault.to_account_info(),
        to: ctx.accounts.provider_ata.to_account_info(),
        authority: ctx.accounts.deposit.to_account_info(),
    };
    let cpi_ctx = CpiContext::new_with_signer(
        ctx.accounts.token_program.to_account_info(),
        cpi_accounts,
        signer_seeds,
    );
    token::transfer(cpi_ctx, payout)?;

    // Update deposit state
    let deposit = &mut ctx.accounts.deposit;
    deposit.released = true;

    // Update job status to Released
    let job = &mut ctx.accounts.job;
    job.status = JobStatus::Released;

    // Update reputation: score += (payout / 1_000_000) + 10
    let reputation = &mut ctx.accounts.reputation;
    let delta = (payout as u64) / 1_000_000 + 10;
    reputation.score = reputation.score.saturating_add(delta);
    reputation.jobs_completed = reputation.jobs_completed.checked_add(1).ok_or(SotaError::Overflow)?;
    reputation.total_earned = reputation.total_earned.saturating_add(payout as u128);
    let clock = Clock::get()?;
    reputation.last_updated = clock.unix_timestamp;

    emit!(JobReleased {
        job_id: job.id,
        provider: deposit.provider,
        amount: payout,
    });

    emit!(PaymentReleased {
        job_id: job.id,
        provider: deposit.provider,
        payout,
        fee,
    });

    emit!(ReputationUpdated {
        agent: deposit.provider,
        score: reputation.score,
        jobs_completed: reputation.jobs_completed,
        jobs_failed: reputation.jobs_failed,
    });

    Ok(())
}
