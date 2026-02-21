use anchor_lang::prelude::*;
use crate::state::{MarketplaceConfig, Agent, AgentStatus};
use crate::errors::SotaError;
use crate::events::AgentUpdated;

#[derive(Accounts)]
pub struct AdminUpdateStatus<'info> {
    #[account(
        seeds = [b"config"],
        bump = config.bump,
    )]
    pub config: Account<'info, MarketplaceConfig>,

    #[account(
        mut,
        seeds = [b"agent", agent.wallet.as_ref()],
        bump = agent.bump,
    )]
    pub agent: Account<'info, Agent>,

    #[account(
        constraint = authority.key() == config.authority @ SotaError::Unauthorized
    )]
    pub authority: Signer<'info>,
}

pub fn handler(ctx: Context<AdminUpdateStatus>, status: u8) -> Result<()> {
    let agent = &mut ctx.accounts.agent;

    require!(agent.status != AgentStatus::Unregistered, SotaError::NotRegistered);

    let new_status = match status {
        1 => AgentStatus::Active,
        2 => AgentStatus::Inactive,
        3 => AgentStatus::Banned,
        _ => return Err(SotaError::InvalidStatus.into()),
    };

    agent.status = new_status;
    let clock = Clock::get()?;
    agent.updated_at = clock.unix_timestamp;

    emit!(AgentUpdated {
        agent: agent.wallet,
        name: agent.name.clone(),
    });

    Ok(())
}
