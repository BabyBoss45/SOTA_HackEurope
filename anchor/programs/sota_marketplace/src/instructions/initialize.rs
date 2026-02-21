use anchor_lang::prelude::*;
use crate::state::MarketplaceConfig;
use crate::errors::SotaError;

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(
        init,
        payer = authority,
        space = 8 + MarketplaceConfig::INIT_SPACE,
        seeds = [b"config"],
        bump,
    )]
    pub config: Account<'info, MarketplaceConfig>,

    #[account(mut)]
    pub authority: Signer<'info>,

    pub usdc_mint: Account<'info, anchor_spl::token::Mint>,
    /// CHECK: Fee collector can be any account
    pub fee_collector: UncheckedAccount<'info>,

    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<Initialize>, platform_fee_bps: u16) -> Result<()> {
    require!(platform_fee_bps <= 5000, SotaError::FeeTooHigh);

    let config = &mut ctx.accounts.config;
    config.authority = ctx.accounts.authority.key();
    config.usdc_mint = ctx.accounts.usdc_mint.key();
    config.fee_collector = ctx.accounts.fee_collector.key();
    config.platform_fee_bps = platform_fee_bps;
    config.next_job_id = 1;
    config.next_bid_id = 1;
    config.bump = ctx.bumps.config;
    Ok(())
}
