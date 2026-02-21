use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Mint, Transfer};
use crate::state::{MarketplaceConfig, Job, Deposit, JobStatus};
use crate::errors::SotaError;
use crate::events::EscrowFunded;

#[derive(Accounts)]
pub struct FundJob<'info> {
    #[account(
        seeds = [b"config"],
        bump = config.bump,
    )]
    pub config: Account<'info, MarketplaceConfig>,

    #[account(
        seeds = [b"job", job.id.to_le_bytes().as_ref()],
        bump = job.bump,
    )]
    pub job: Account<'info, Job>,

    #[account(
        init,
        payer = poster,
        space = 8 + Deposit::INIT_SPACE,
        seeds = [b"deposit", job.id.to_le_bytes().as_ref()],
        bump,
    )]
    pub deposit: Account<'info, Deposit>,

    #[account(
        init,
        payer = poster,
        seeds = [b"escrow_vault", job.id.to_le_bytes().as_ref()],
        bump,
        token::mint = usdc_mint,
        token::authority = deposit,
    )]
    pub escrow_vault: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = poster_ata.mint == usdc_mint.key(),
        constraint = poster_ata.owner == poster.key(),
    )]
    pub poster_ata: Account<'info, TokenAccount>,

    #[account(
        constraint = usdc_mint.key() == config.usdc_mint,
    )]
    pub usdc_mint: Account<'info, Mint>,

    #[account(mut)]
    pub poster: Signer<'info>,

    /// CHECK: Provider can be any pubkey, validated against job.provider
    pub provider: UncheckedAccount<'info>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

pub fn handler(ctx: Context<FundJob>, amount: u64) -> Result<()> {
    let job = &ctx.accounts.job;

    require!(amount > 0 && amount <= job.max_budget_usdc, SotaError::InvalidAmount);
    require!(job.poster == ctx.accounts.poster.key(), SotaError::NotPoster);
    require!(job.status == JobStatus::Assigned, SotaError::NotAssigned);
    require!(
        job.provider == ctx.accounts.provider.key(),
        SotaError::ProviderMismatch
    );

    // Transfer USDC from poster to escrow vault
    let cpi_accounts = Transfer {
        from: ctx.accounts.poster_ata.to_account_info(),
        to: ctx.accounts.escrow_vault.to_account_info(),
        authority: ctx.accounts.poster.to_account_info(),
    };
    let cpi_ctx = CpiContext::new(ctx.accounts.token_program.to_account_info(), cpi_accounts);
    token::transfer(cpi_ctx, amount)?;

    // Initialize deposit
    let deposit = &mut ctx.accounts.deposit;
    deposit.job_id = job.id;
    deposit.poster = ctx.accounts.poster.key();
    deposit.provider = ctx.accounts.provider.key();
    deposit.amount = amount;
    deposit.funded = true;
    deposit.released = false;
    deposit.refunded = false;
    deposit.delivery_confirmed = false;
    deposit.delivery_confirmed_at = 0;
    deposit.bump = ctx.bumps.deposit;

    emit!(EscrowFunded {
        job_id: job.id,
        poster: ctx.accounts.poster.key(),
        provider: ctx.accounts.provider.key(),
        amount,
    });

    Ok(())
}
