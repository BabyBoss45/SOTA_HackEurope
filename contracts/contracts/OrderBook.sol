// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title OrderBook
 * @notice Job lifecycle with competitive bidding for the SOTA marketplace.
 *
 *         Workflow:
 *           1. createJob()      — poster describes work + max USDC budget
 *           2. placeBid()       — agents bid with a price ≤ budget
 *           3. acceptBid()      — poster selects the winning bid → assigns provider
 *           4. markCompleted()  — agent declares work done
 *           5. markReleased()   — called by Escrow after payment release
 *
 *         All prices are denominated in USDC (6 decimals).
 */
contract OrderBook is Ownable {
    // ─── Types ──────────────────────────────────────────────

    enum JobStatus {
        OPEN,
        ASSIGNED,
        COMPLETED,
        RELEASED,
        CANCELLED,
        DISPUTED
    }

    struct Job {
        uint256 id;
        address poster;
        address provider;           // assigned agent (after acceptBid)
        string  metadataURI;        // IPFS / off-chain job description
        uint256 maxBudgetUsdc;      // budget in USDC (6 decimals)
        uint64  deadline;
        JobStatus status;
        bytes32 deliveryProof;
        uint256 createdAt;
        uint256 acceptedBidId;      // winning bid ID
    }

    struct Bid {
        uint256 id;
        uint256 jobId;
        address agent;
        uint256 priceUsdc;          // bid price in USDC (6 decimals)
        uint256 estimatedTime;      // seconds to complete
        string  proposal;           // brief description of approach
        uint256 createdAt;
        bool    accepted;
    }

    // ─── State ──────────────────────────────────────────────

    uint256 private _nextJobId = 1;
    uint256 private _nextBidId = 1;
    mapping(uint256 => Job) public jobs;
    mapping(uint256 => Bid) public bids;
    mapping(uint256 => uint256[]) public jobBids;   // jobId → bidId[]
    uint256[] public jobIds;                         // for enumeration

    address public escrow;                           // Escrow address

    // ─── Events ─────────────────────────────────────────────

    event JobCreated(
        uint256 indexed jobId,
        address indexed poster,
        uint256 maxBudgetUsdc
    );
    event BidPlaced(
        uint256 indexed jobId,
        uint256 indexed bidId,
        address indexed agent,
        uint256 priceUsdc
    );
    event BidAccepted(
        uint256 indexed jobId,
        uint256 indexed bidId,
        address indexed provider
    );
    event ProviderAssigned(
        uint256 indexed jobId,
        address indexed provider
    );
    event JobCompleted(
        uint256 indexed jobId,
        bytes32 deliveryProof
    );
    event JobReleased(uint256 indexed jobId);
    event JobCancelled(uint256 indexed jobId);
    event JobDisputed(uint256 indexed jobId, address indexed disputedBy);

    // ─── Constructor ────────────────────────────────────────

    constructor(address initialOwner) Ownable(initialOwner) {}

    // ─── Config ─────────────────────────────────────────────

    function setEscrow(address escrow_) external onlyOwner {
        escrow = escrow_;
    }

    // ─── Core Functions ─────────────────────────────────────

    /**
     * @notice Post a new job with a max USDC budget.
     */
    function createJob(
        string calldata metadataURI,
        uint256 maxBudgetUsdc,
        uint64 deadline
    ) external returns (uint256 jobId) {
        require(maxBudgetUsdc > 0, "OrderBook: zero budget");
        require(deadline > block.timestamp, "OrderBook: past deadline");

        jobId = _nextJobId++;

        jobs[jobId] = Job({
            id: jobId,
            poster: msg.sender,
            provider: address(0),
            metadataURI: metadataURI,
            maxBudgetUsdc: maxBudgetUsdc,
            deadline: deadline,
            status: JobStatus.OPEN,
            deliveryProof: bytes32(0),
            createdAt: block.timestamp,
            acceptedBidId: 0
        });

        jobIds.push(jobId);
        emit JobCreated(jobId, msg.sender, maxBudgetUsdc);
    }

    /**
     * @notice Agent places a bid on an OPEN job.
     *         Bid price must be ≤ the job's max budget.
     */
    function placeBid(
        uint256 jobId,
        uint256 priceUsdc,
        uint256 estimatedTime,
        string calldata proposal
    ) external returns (uint256 bidId) {
        Job storage job = jobs[jobId];
        require(job.status == JobStatus.OPEN, "OrderBook: not open");
        require(block.timestamp < job.deadline, "OrderBook: past deadline");
        require(priceUsdc > 0, "OrderBook: zero bid");
        require(priceUsdc <= job.maxBudgetUsdc, "OrderBook: bid exceeds budget");
        require(msg.sender != job.poster, "OrderBook: poster cannot bid");

        bidId = _nextBidId++;
        bids[bidId] = Bid({
            id: bidId,
            jobId: jobId,
            agent: msg.sender,
            priceUsdc: priceUsdc,
            estimatedTime: estimatedTime,
            proposal: proposal,
            createdAt: block.timestamp,
            accepted: false
        });

        jobBids[jobId].push(bidId);
        emit BidPlaced(jobId, bidId, msg.sender, priceUsdc);
    }

    /**
     * @notice Poster accepts a bid and assigns the agent.
     *         After acceptance, the poster should call Escrow.fundJob().
     */
    function acceptBid(uint256 jobId, uint256 bidId) external {
        Job storage job = jobs[jobId];
        require(job.poster == msg.sender, "OrderBook: not poster");
        require(job.status == JobStatus.OPEN, "OrderBook: not open");

        Bid storage bid = bids[bidId];
        require(bid.jobId == jobId, "OrderBook: bid/job mismatch");
        require(!bid.accepted, "OrderBook: bid already accepted");

        bid.accepted = true;
        job.provider = bid.agent;
        job.status = JobStatus.ASSIGNED;
        job.acceptedBidId = bidId;

        emit BidAccepted(jobId, bidId, bid.agent);
        emit ProviderAssigned(jobId, bid.agent);
    }

    /**
     * @notice Poster assigns an agent directly (without bidding).
     *         After assignment, the poster should call Escrow.fundJob().
     */
    function assignProvider(
        uint256 jobId,
        address provider
    ) external {
        Job storage job = jobs[jobId];
        require(job.poster == msg.sender, "OrderBook: not poster");
        require(job.status == JobStatus.OPEN, "OrderBook: not open");
        require(provider != address(0), "OrderBook: zero provider");

        job.provider = provider;
        job.status = JobStatus.ASSIGNED;

        emit ProviderAssigned(jobId, provider);
    }

    /**
     * @notice Poster or provider marks the job as completed.
     *         After this, the owner confirms delivery on Escrow,
     *         then Escrow.releaseToProvider() can be called.
     */
    function markCompleted(
        uint256 jobId,
        bytes32 deliveryProof
    ) external {
        Job storage job = jobs[jobId];
        require(
            job.provider == msg.sender || job.poster == msg.sender,
            "OrderBook: not poster or provider"
        );
        require(job.status == JobStatus.ASSIGNED, "OrderBook: not assigned");

        job.status = JobStatus.COMPLETED;
        job.deliveryProof = deliveryProof;

        emit JobCompleted(jobId, deliveryProof);
    }

    /**
     * @notice Called by Escrow after successful payment release.
     */
    function markReleased(uint256 jobId) external {
        require(msg.sender == escrow, "OrderBook: not escrow");
        jobs[jobId].status = JobStatus.RELEASED;
        emit JobReleased(jobId);
    }

    /**
     * @notice Poster can cancel an OPEN job (before assignment).
     */
    function cancelJob(uint256 jobId) external {
        Job storage job = jobs[jobId];
        require(job.poster == msg.sender, "OrderBook: not poster");
        require(job.status == JobStatus.OPEN, "OrderBook: not open");
        job.status = JobStatus.CANCELLED;
        emit JobCancelled(jobId);
    }

    /**
     * @notice Poster or provider can raise a dispute on an ASSIGNED or COMPLETED job.
     */
    function raiseDispute(uint256 jobId) external {
        Job storage job = jobs[jobId];
        require(
            msg.sender == job.poster || msg.sender == job.provider,
            "OrderBook: not party"
        );
        require(
            job.status == JobStatus.ASSIGNED || job.status == JobStatus.COMPLETED,
            "OrderBook: cannot dispute"
        );
        job.status = JobStatus.DISPUTED;
        emit JobDisputed(jobId, msg.sender);
    }

    // ─── Views ──────────────────────────────────────────────

    function getJob(uint256 jobId) external view returns (Job memory) {
        return jobs[jobId];
    }

    function getBid(uint256 bidId) external view returns (Bid memory) {
        return bids[bidId];
    }

    function getJobBidIds(uint256 jobId) external view returns (uint256[] memory) {
        return jobBids[jobId];
    }

    function getJobBidCount(uint256 jobId) external view returns (uint256) {
        return jobBids[jobId].length;
    }

    function totalJobs() external view returns (uint256) {
        return jobIds.length;
    }

    function getJobIds(
        uint256 offset,
        uint256 limit
    ) external view returns (uint256[] memory ids) {
        uint256 total = jobIds.length;
        if (offset >= total) return new uint256[](0);
        uint256 end = offset + limit > total ? total : offset + limit;
        ids = new uint256[](end - offset);
        for (uint256 i = offset; i < end; i++) {
            ids[i - offset] = jobIds[i];
        }
    }
}
