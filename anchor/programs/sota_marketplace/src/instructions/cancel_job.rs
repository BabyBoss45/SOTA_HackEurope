use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};
use crate::state::{Job, JobStatus, Deposit, Reputation};
use crate::errors::SotaError;
use crate::events::{JobCancelled, PaymentRefunded, ReputationUpdated};

#[derive(Accounts)]
pub struct CancelJob<'info> {
    #[account(
        mut,
        seeds = [b"job", job.id.to_le_bytes().as_ref()],
        bump = job.bump,
    )]
    pub job: Account<'info, Job>,

    pub poster: Signer<'info>,

    // --- Optional escrow accounts (present when the job was funded) ---

    #[account(
        mut,
        seeds = [b"deposit", job.id.to_le_bytes().as_ref()],
        bump,
    )]
    pub deposit: Option<Account<'info, Deposit>>,

    #[account(
        mut,
        seeds = [b"escrow_vault", job.id.to_le_bytes().as_ref()],
        bump,
    )]
    pub escrow_vault: Option<Account<'info, TokenAccount>>,

    #[account(mut)]
    pub poster_ata: Option<Account<'info, TokenAccount>>,

    pub token_program: Option<Program<'info, Token>>,

    // --- Optional reputation account (present when a provider was assigned) ---

    #[account(
        mut,
        seeds = [b"reputation", job.provider.as_ref()],
        bump,
    )]
    pub reputation: Option<Account<'info, Reputation>>,
}

pub fn handler(ctx: Context<CancelJob>) -> Result<()> {
    let job = &mut ctx.accounts.job;

    require!(job.poster == ctx.accounts.poster.key(), SotaError::NotPoster);
    require!(
        job.status == JobStatus::Open || job.status == JobStatus::Assigned,
        SotaError::NotOpen
    );

    // --- Refund escrow if funded and not yet refunded ---
    if let (Some(deposit), Some(escrow_vault), Some(poster_ata), Some(token_program)) = (
        ctx.accounts.deposit.as_mut(),
        ctx.accounts.escrow_vault.as_ref(),
        ctx.accounts.poster_ata.as_ref(),
        ctx.accounts.token_program.as_ref(),
    ) {
        if deposit.funded && !deposit.refunded && !deposit.released {
            let job_id_bytes = deposit.job_id.to_le_bytes();
            let bump_slice = [deposit.bump];
            let deposit_seeds: &[&[u8]] = &[b"deposit", job_id_bytes.as_ref(), &bump_slice];
            let signer_seeds = &[deposit_seeds];

            let cpi_accounts = Transfer {
                from: escrow_vault.to_account_info(),
                to: poster_ata.to_account_info(),
                authority: deposit.to_account_info(),
            };
            let cpi_ctx = CpiContext::new_with_signer(
                token_program.to_account_info(),
                cpi_accounts,
                signer_seeds,
            );
            token::transfer(cpi_ctx, deposit.amount)?;

            deposit.refunded = true;

            emit!(PaymentRefunded {
                job_id: job.id,
                poster: deposit.poster,
                amount: deposit.amount,
            });
        }
    }

    // --- Penalise provider reputation if one was assigned ---
    if job.provider != Pubkey::default() {
        if let Some(reputation) = ctx.accounts.reputation.as_mut() {
            reputation.jobs_failed = reputation
                .jobs_failed
                .checked_add(1)
                .ok_or(SotaError::Overflow)?;
            reputation.score = reputation.score.saturating_sub(5);
            let clock = Clock::get()?;
            reputation.last_updated = clock.unix_timestamp;

            emit!(ReputationUpdated {
                agent: job.provider,
                score: reputation.score,
                jobs_completed: reputation.jobs_completed,
                jobs_failed: reputation.jobs_failed,
            });
        }
    }

    job.status = JobStatus::Cancelled;

    emit!(JobCancelled { job_id: job.id });

    Ok(())
}
