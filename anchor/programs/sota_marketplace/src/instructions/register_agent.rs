use anchor_lang::prelude::*;
use crate::state::{Agent, Reputation, AgentStatus};
use crate::events::AgentRegistered;

#[derive(Accounts)]
#[instruction(name: String, metadata_uri: String, capabilities: Vec<String>)]
pub struct RegisterAgent<'info> {
    #[account(
        init,
        payer = developer,
        space = 8 + Agent::INIT_SPACE,
        seeds = [b"agent", wallet.key().as_ref()],
        bump,
    )]
    pub agent: Account<'info, Agent>,

    #[account(
        init,
        payer = developer,
        space = 8 + Reputation::INIT_SPACE,
        seeds = [b"reputation", wallet.key().as_ref()],
        bump,
    )]
    pub reputation: Account<'info, Reputation>,

    /// CHECK: The wallet address to register. Can be any pubkey.
    pub wallet: UncheckedAccount<'info>,

    #[account(mut)]
    pub developer: Signer<'info>,

    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<RegisterAgent>,
    name: String,
    metadata_uri: String,
    capabilities: Vec<String>,
) -> Result<()> {
    let clock = Clock::get()?;

    let agent = &mut ctx.accounts.agent;
    agent.wallet = ctx.accounts.wallet.key();
    agent.developer = ctx.accounts.developer.key();
    agent.name = name.clone();
    agent.metadata_uri = metadata_uri.clone();
    agent.capabilities = capabilities;
    agent.reputation = 0;
    agent.status = AgentStatus::Active;
    agent.created_at = clock.unix_timestamp;
    agent.updated_at = clock.unix_timestamp;
    agent.bump = ctx.bumps.agent;

    let reputation = &mut ctx.accounts.reputation;
    reputation.wallet = ctx.accounts.wallet.key();
    reputation.score = 0;
    reputation.jobs_completed = 0;
    reputation.jobs_failed = 0;
    reputation.total_earned = 0;
    reputation.last_updated = clock.unix_timestamp;
    reputation.bump = ctx.bumps.reputation;

    emit!(AgentRegistered {
        agent: ctx.accounts.wallet.key(),
        developer: ctx.accounts.developer.key(),
        name,
        metadata_uri,
    });

    Ok(())
}
