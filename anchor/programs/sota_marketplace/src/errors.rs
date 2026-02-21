use anchor_lang::prelude::*;

#[error_code]
pub enum SotaError {
    #[msg("Budget must be greater than zero")]
    ZeroBudget,
    #[msg("Deadline must be in the future")]
    PastDeadline,
    #[msg("Job is not open")]
    NotOpen,
    #[msg("Job deadline has passed")]
    DeadlinePassed,
    #[msg("Bid price must be greater than zero")]
    ZeroBid,
    #[msg("Bid exceeds job budget")]
    BidExceedsBudget,
    #[msg("Poster cannot bid on own job")]
    PosterCannotBid,
    #[msg("Not the job poster")]
    NotPoster,
    #[msg("Bid/job mismatch")]
    BidJobMismatch,
    #[msg("Bid already accepted")]
    BidAlreadyAccepted,
    #[msg("Provider address cannot be default")]
    ZeroProvider,
    #[msg("Not poster or provider")]
    NotPosterOrProvider,
    #[msg("Job is not assigned")]
    NotAssigned,
    #[msg("Not the escrow contract")]
    NotEscrow,
    #[msg("Job is not completed")]
    NotCompleted,
    #[msg("Not a party to this job")]
    NotParty,
    #[msg("Job cannot be disputed in this status")]
    CannotDispute,
    #[msg("Escrow already funded")]
    AlreadyFunded,
    #[msg("Amount must be greater than zero")]
    ZeroAmount,
    #[msg("Job not found")]
    JobNotFound,
    #[msg("Provider mismatch")]
    ProviderMismatch,
    #[msg("Escrow not funded")]
    NotFunded,
    #[msg("Escrow already released")]
    AlreadyReleased,
    #[msg("Escrow already refunded")]
    AlreadyRefunded,
    #[msg("Delivery not confirmed")]
    DeliveryNotConfirmed,
    #[msg("Not authorised")]
    NotAuthorised,
    #[msg("Dispute window is still active")]
    DisputeWindowActive,
    #[msg("Job not in completed state")]
    JobNotCompleted,
    #[msg("Escrow in invalid state")]
    InvalidEscrowState,
    #[msg("Agent already registered")]
    AlreadyRegistered,
    #[msg("Agent not registered")]
    NotRegistered,
    #[msg("Not the agent developer")]
    NotDeveloper,
    #[msg("Invalid agent status")]
    InvalidStatus,
    #[msg("Fee too high (max 10%)")]
    FeeTooHigh,
    #[msg("Unauthorized")]
    Unauthorized,
    #[msg("Arithmetic overflow")]
    Overflow,
    #[msg("Invalid amount: must be > 0 and <= job budget")]
    InvalidAmount,
}
