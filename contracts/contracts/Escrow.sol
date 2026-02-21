// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

interface IOrderBook {
    struct JobInfo {
        uint256 id;
        address poster;
        address provider;
        string  metadataURI;
        uint256 maxBudgetUsdc;
        uint64  deadline;
        uint8   status;
        bytes32 deliveryProof;
        uint256 createdAt;
        uint256 acceptedBidId;
    }
    function markReleased(uint256 jobId) external;
    function getJob(uint256 jobId) external view returns (JobInfo memory);
}

interface IReputationToken {
    function recordSuccess(address agent, uint256 payoutAmount) external;
    function recordFailure(address agent) external;
}

/**
 * @title Escrow
 * @notice Holds USDC for jobs. Release is gated on owner-confirmed delivery.
 *
 *         Flow:
 *           1. fundJob()           — poster deposits USDC (must approve first)
 *           2. confirmDelivery()   — owner confirms the work is done
 *           3. releaseToProvider() — poster or provider triggers USDC payout
 *
 *         All amounts are USDC with 6 decimals.
 */
contract Escrow is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ─── Types ──────────────────────────────────────────────

    struct Deposit {
        address poster;
        address provider;
        uint256 amount;       // USDC amount (6 decimals)
        bool funded;
        bool released;
        bool refunded;
    }

    // ─── Job Status Constants (must match OrderBook.JobStatus) ─

    uint8 private constant JOB_STATUS_ASSIGNED  = 1;
    uint8 private constant JOB_STATUS_COMPLETED = 2;

    // ─── Dispute Window ─────────────────────────────────────

    uint256 public constant DISPUTE_WINDOW = 1 hours;

    // ─── State ──────────────────────────────────────────────

    mapping(uint256 => Deposit) public deposits;
    mapping(uint256 => bool) public deliveryConfirmed;
    mapping(uint256 => uint256) public deliveryConfirmedAt;

    IERC20 public immutable usdc;
    IOrderBook public orderBook;
    IReputationToken public reputationToken;
    address public feeCollector;
    uint96 public platformFeeBps;  // 200 = 2%

    // ─── Events ─────────────────────────────────────────────

    event EscrowFunded(
        uint256 indexed jobId,
        address indexed poster,
        address indexed provider,
        uint256 amount
    );
    event DeliveryConfirmed(uint256 indexed jobId);
    event PaymentReleased(
        uint256 indexed jobId,
        address indexed provider,
        uint256 payout,
        uint256 fee
    );
    event PaymentRefunded(
        uint256 indexed jobId,
        address indexed poster,
        uint256 amount
    );

    // ─── Constructor ────────────────────────────────────────

    constructor(
        address initialOwner,
        address usdcToken,
        address feeCollector_
    ) Ownable(initialOwner) {
        usdc = IERC20(usdcToken);
        feeCollector = feeCollector_;
        platformFeeBps = 200; // 2%
    }

    // ─── Config ─────────────────────────────────────────────

    function setOrderBook(address ob) external onlyOwner {
        orderBook = IOrderBook(ob);
    }

    function setReputationToken(address rt) external onlyOwner {
        reputationToken = IReputationToken(rt);
    }

    function setFeeCollector(address collector, uint96 bps) external onlyOwner {
        require(collector != address(0), "Escrow: zero fee collector");
        require(bps <= 1000, "Escrow: fee too high");
        feeCollector = collector;
        platformFeeBps = bps;
    }

    // ─── Core Functions ─────────────────────────────────────

    /**
     * @notice Fund escrow with USDC. Caller must approve this contract first.
     *         Validates job exists on OrderBook and caller is the poster.
     */
    function fundJob(
        uint256 jobId,
        address provider,
        uint256 amount
    ) external {
        Deposit storage dep = deposits[jobId];
        require(!dep.funded, "Escrow: already funded");
        require(amount > 0, "Escrow: zero amount");
        require(provider != address(0), "Escrow: zero provider");

        // Validate against OrderBook (mandatory)
        require(address(orderBook) != address(0), "Escrow: OrderBook not set");
        IOrderBook.JobInfo memory job = orderBook.getJob(jobId);
        require(job.id > 0, "Escrow: job not found");
        require(job.poster == msg.sender, "Escrow: not job poster");
        require(job.status == JOB_STATUS_ASSIGNED, "Escrow: job not assigned");
        require(job.provider == provider, "Escrow: provider mismatch");

        usdc.safeTransferFrom(msg.sender, address(this), amount);

        dep.poster = msg.sender;
        dep.provider = provider;
        dep.amount = amount;
        dep.funded = true;

        emit EscrowFunded(jobId, msg.sender, provider, amount);
    }

    /**
     * @notice Owner confirms delivery.
     */
    function confirmDelivery(uint256 jobId) external onlyOwner {
        Deposit storage dep = deposits[jobId];
        require(dep.funded, "Escrow: not funded");
        require(!dep.released && !dep.refunded, "Escrow: already settled");
        deliveryConfirmed[jobId] = true;
        deliveryConfirmedAt[jobId] = block.timestamp;
        emit DeliveryConfirmed(jobId);
    }

    /**
     * @notice Release USDC to provider. Requires delivery confirmation.
     *         Provider must wait for DISPUTE_WINDOW after confirmDelivery;
     *         poster can release immediately (waiving their own dispute window).
     */
    function releaseToProvider(uint256 jobId) external nonReentrant {
        Deposit storage dep = deposits[jobId];
        require(dep.funded, "Escrow: not funded");
        require(!dep.released, "Escrow: already released");
        require(!dep.refunded, "Escrow: refunded");
        require(deliveryConfirmed[jobId], "Escrow: delivery not confirmed");
        require(
            msg.sender == dep.poster || msg.sender == dep.provider,
            "Escrow: not authorised"
        );

        // Provider must wait for dispute window; poster can release immediately
        if (msg.sender == dep.provider) {
            require(
                block.timestamp >= deliveryConfirmedAt[jobId] + DISPUTE_WINDOW,
                "Escrow: dispute window active"
            );
        }

        // Verify job isn't disputed on OrderBook
        if (address(orderBook) != address(0)) {
            IOrderBook.JobInfo memory job = orderBook.getJob(jobId);
            require(job.status == JOB_STATUS_COMPLETED, "Escrow: job not in completed state");
        }

        dep.released = true;
        uint256 fee = (dep.amount * platformFeeBps) / 10_000;
        uint256 payout = dep.amount - fee;

        if (fee > 0 && feeCollector != address(0)) {
            usdc.safeTransfer(feeCollector, fee);
        }
        usdc.safeTransfer(dep.provider, payout);

        if (address(orderBook) != address(0)) {
            orderBook.markReleased(jobId);
        }

        if (address(reputationToken) != address(0)) {
            reputationToken.recordSuccess(dep.provider, payout);
        }

        emit PaymentReleased(jobId, dep.provider, payout, fee);
    }

    /**
     * @notice Refund poster (owner-only dispute resolution).
     */
    function refund(uint256 jobId) external nonReentrant onlyOwner {
        Deposit storage dep = deposits[jobId];
        require(dep.funded && !dep.released && !dep.refunded, "Escrow: invalid state");
        dep.refunded = true;
        usdc.safeTransfer(dep.poster, dep.amount);

        if (address(reputationToken) != address(0) && dep.provider != address(0)) {
            reputationToken.recordFailure(dep.provider);
        }

        emit PaymentRefunded(jobId, dep.poster, dep.amount);
    }

    // ─── Views ──────────────────────────────────────────────

    function getDeposit(uint256 jobId) external view returns (Deposit memory) {
        return deposits[jobId];
    }

    function isDeliveryConfirmed(uint256 jobId) external view returns (bool) {
        return deliveryConfirmed[jobId];
    }
}
