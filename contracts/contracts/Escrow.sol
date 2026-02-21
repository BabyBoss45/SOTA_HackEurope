// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

interface IOrderBook {
    function markReleased(uint256 jobId) external;
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

    // ─── State ──────────────────────────────────────────────

    mapping(uint256 => Deposit) public deposits;
    mapping(uint256 => bool) public deliveryConfirmed;

    IERC20 public immutable usdc;
    IOrderBook public orderBook;
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

    function setFeeCollector(address collector, uint96 bps) external onlyOwner {
        require(bps <= 1000, "Escrow: fee too high");
        feeCollector = collector;
        platformFeeBps = bps;
    }

    // ─── Core Functions ─────────────────────────────────────

    /**
     * @notice Fund escrow with USDC. Caller must approve this contract first.
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
        deliveryConfirmed[jobId] = true;
        emit DeliveryConfirmed(jobId);
    }

    /**
     * @notice Release USDC to provider. Requires delivery confirmation.
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
