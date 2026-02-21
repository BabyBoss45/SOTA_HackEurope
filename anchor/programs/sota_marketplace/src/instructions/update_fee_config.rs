use anchor_lang::prelude::*;
use crate::state::MarketplaceConfig;
use crate::errors::SotaError;

#[derive(Accounts)]
pub struct UpdateFeeConfig<'info> {
    #[account(
        mut,
        seeds = [b"config"],
        bump = config.bump,
    )]
    pub config: Account<'info, MarketplaceConfig>,

    /// CHECK: New fee collector, can be any account
    pub fee_collector: UncheckedAccount<'info>,

    #[account(
        constraint = authority.key() == config.authority @ SotaError::Unauthorized
    )]
    pub authority: Signer<'info>,
}

pub fn handler(ctx: Context<UpdateFeeConfig>, platform_fee_bps: u16) -> Result<()> {
    require!(platform_fee_bps <= 1000, SotaError::FeeTooHigh);

    let config = &mut ctx.accounts.config;
    config.fee_collector = ctx.accounts.fee_collector.key();
    config.platform_fee_bps = platform_fee_bps;

    Ok(())
}
