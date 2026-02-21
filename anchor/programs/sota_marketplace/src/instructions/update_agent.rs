use anchor_lang::prelude::*;
use crate::state::{Agent, AgentStatus};
use crate::errors::SotaError;
use crate::events::AgentUpdated;

#[derive(Accounts)]
pub struct UpdateAgent<'info> {
    #[account(
        mut,
        seeds = [b"agent", agent.wallet.as_ref()],
        bump = agent.bump,
    )]
    pub agent: Account<'info, Agent>,

    pub developer: Signer<'info>,
}

pub fn handler(
    ctx: Context<UpdateAgent>,
    name: String,
    metadata_uri: String,
    capabilities: Vec<String>,
    status: u8,
) -> Result<()> {
    let agent = &mut ctx.accounts.agent;

    require!(agent.status != AgentStatus::Unregistered, SotaError::NotRegistered);
    require!(agent.developer == ctx.accounts.developer.key(), SotaError::NotDeveloper);

    let new_status = match status {
        1 => AgentStatus::Active,
        2 => AgentStatus::Inactive,
        _ => return Err(SotaError::InvalidStatus.into()),
    };

    agent.name = name.clone();
    agent.metadata_uri = metadata_uri;
    agent.capabilities = capabilities;
    agent.status = new_status;
    let clock = Clock::get()?;
    agent.updated_at = clock.unix_timestamp;

    emit!(AgentUpdated {
        agent: agent.wallet,
        name,
    });

    Ok(())
}
