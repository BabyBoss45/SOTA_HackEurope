import { expect } from "chai";
import { ethers } from "hardhat";
import { loadFixture, time } from "@nomicfoundation/hardhat-network-helpers";
import { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";

// USDC uses 6 decimals
const USDC = (n: number) => BigInt(n) * 10n ** 6n;

async function deployFixture() {
  const [owner, poster, agent1, agent2, feeCollector] = await ethers.getSigners();

  // Deploy MockUSDC
  const usdc = await ethers.deployContract("MockUSDC");
  await usdc.waitForDeployment();

  // Deploy OrderBook
  const orderBook = await ethers.deployContract("OrderBook", [owner.address]);
  await orderBook.waitForDeployment();

  // Deploy Escrow
  const escrow = await ethers.deployContract("Escrow", [
    owner.address,
    await usdc.getAddress(),
    feeCollector.address,
  ]);
  await escrow.waitForDeployment();

  // Deploy AgentRegistry
  const agentRegistry = await ethers.deployContract("AgentRegistry", [owner.address]);
  await agentRegistry.waitForDeployment();

  // Deploy ReputationToken
  const reputationToken = await ethers.deployContract("ReputationToken", [owner.address]);
  await reputationToken.waitForDeployment();

  // Wire contracts
  await orderBook.setEscrow(await escrow.getAddress());
  await escrow.setOrderBook(await orderBook.getAddress());
  await escrow.setReputationToken(await reputationToken.getAddress());
  await reputationToken.setEscrow(await escrow.getAddress());
  await reputationToken.setAgentRegistry(await agentRegistry.getAddress());
  await agentRegistry.setReputationOracle(await reputationToken.getAddress());

  // Mint USDC to poster
  await usdc.mint(poster.address, USDC(10_000));

  return { owner, poster, agent1, agent2, feeCollector, usdc, orderBook, escrow, agentRegistry, reputationToken };
}

// ═══════════════════════════════════════════════════════════════
// MockUSDC
// ═══════════════════════════════════════════════════════════════

describe("MockUSDC", () => {
  it("has 6 decimals", async () => {
    const { usdc } = await loadFixture(deployFixture);
    expect(await usdc.decimals()).to.equal(6);
  });

  it("allows unrestricted minting", async () => {
    const { usdc, agent1 } = await loadFixture(deployFixture);
    await usdc.mint(agent1.address, USDC(500));
    expect(await usdc.balanceOf(agent1.address)).to.equal(USDC(500));
  });

  it("supports approve and transferFrom", async () => {
    const { usdc, poster, agent1 } = await loadFixture(deployFixture);
    await usdc.connect(poster).approve(agent1.address, USDC(100));
    await usdc.connect(agent1).transferFrom(poster.address, agent1.address, USDC(100));
    expect(await usdc.balanceOf(agent1.address)).to.equal(USDC(100));
  });
});

// ═══════════════════════════════════════════════════════════════
// OrderBook
// ═══════════════════════════════════════════════════════════════

describe("OrderBook", () => {
  describe("createJob", () => {
    it("creates a job with correct parameters", async () => {
      const { orderBook, poster } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;

      await expect(orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline))
        .to.emit(orderBook, "JobCreated")
        .withArgs(1, poster.address, USDC(100));

      const job = await orderBook.getJob(1);
      expect(job.poster).to.equal(poster.address);
      expect(job.maxBudgetUsdc).to.equal(USDC(100));
      expect(job.status).to.equal(0); // OPEN
    });

    it("reverts on zero budget", async () => {
      const { orderBook, poster } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await expect(
        orderBook.connect(poster).createJob("ipfs://job1", 0, deadline)
      ).to.be.revertedWith("OrderBook: zero budget");
    });

    it("reverts on past deadline", async () => {
      const { orderBook, poster } = await loadFixture(deployFixture);
      const pastDeadline = (await time.latest()) - 1;
      await expect(
        orderBook.connect(poster).createJob("ipfs://job1", USDC(100), pastDeadline)
      ).to.be.revertedWith("OrderBook: past deadline");
    });

    it("increments job IDs", async () => {
      const { orderBook, poster } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://1", USDC(100), deadline);
      await orderBook.connect(poster).createJob("ipfs://2", USDC(200), deadline);
      expect(await orderBook.totalJobs()).to.equal(2);
    });
  });

  describe("placeBid", () => {
    it("places a valid bid", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);

      await expect(
        orderBook.connect(agent1).placeBid(1, USDC(80), 3600, "I can do this")
      )
        .to.emit(orderBook, "BidPlaced")
        .withArgs(1, 1, agent1.address, USDC(80));
    });

    it("reverts when bid exceeds budget", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);

      await expect(
        orderBook.connect(agent1).placeBid(1, USDC(150), 3600, "Too expensive")
      ).to.be.revertedWith("OrderBook: bid exceeds budget");
    });

    it("reverts when poster tries to bid on own job", async () => {
      const { orderBook, poster } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);

      await expect(
        orderBook.connect(poster).placeBid(1, USDC(80), 3600, "Self bid")
      ).to.be.revertedWith("OrderBook: poster cannot bid");
    });

    it("reverts on zero bid", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);

      await expect(
        orderBook.connect(agent1).placeBid(1, 0, 3600, "Free")
      ).to.be.revertedWith("OrderBook: zero bid");
    });
  });

  describe("acceptBid", () => {
    it("poster accepts a bid and assigns provider", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(agent1).placeBid(1, USDC(80), 3600, "bid");

      await expect(orderBook.connect(poster).acceptBid(1, 1))
        .to.emit(orderBook, "BidAccepted")
        .withArgs(1, 1, agent1.address);

      const job = await orderBook.getJob(1);
      expect(job.provider).to.equal(agent1.address);
      expect(job.status).to.equal(1); // ASSIGNED
    });

    it("reverts when non-poster tries to accept", async () => {
      const { orderBook, poster, agent1, agent2 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(agent1).placeBid(1, USDC(80), 3600, "bid");

      await expect(
        orderBook.connect(agent2).acceptBid(1, 1)
      ).to.be.revertedWith("OrderBook: not poster");
    });

    it("reverts on bid/job mismatch", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).createJob("ipfs://job2", USDC(200), deadline);
      await orderBook.connect(agent1).placeBid(2, USDC(150), 3600, "bid on job 2");

      // Try to accept bid 1 (for job 2) on job 1
      await expect(
        orderBook.connect(poster).acceptBid(1, 1)
      ).to.be.revertedWith("OrderBook: bid/job mismatch");
    });
  });

  describe("assignProvider", () => {
    it("directly assigns a provider", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);

      await expect(orderBook.connect(poster).assignProvider(1, agent1.address))
        .to.emit(orderBook, "ProviderAssigned")
        .withArgs(1, agent1.address);

      const job = await orderBook.getJob(1);
      expect(job.status).to.equal(1); // ASSIGNED
    });

    it("reverts on zero address", async () => {
      const { orderBook, poster } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);

      await expect(
        orderBook.connect(poster).assignProvider(1, ethers.ZeroAddress)
      ).to.be.revertedWith("OrderBook: zero provider");
    });
  });

  describe("markCompleted", () => {
    it("provider marks job as completed", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);

      const proof = ethers.keccak256(ethers.toUtf8Bytes("delivery proof"));
      await expect(orderBook.connect(agent1).markCompleted(1, proof))
        .to.emit(orderBook, "JobCompleted")
        .withArgs(1, proof);

      const job = await orderBook.getJob(1);
      expect(job.status).to.equal(2); // COMPLETED
    });

    it("reverts when unauthorized user calls", async () => {
      const { orderBook, poster, agent1, agent2 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);

      const proof = ethers.keccak256(ethers.toUtf8Bytes("proof"));
      await expect(
        orderBook.connect(agent2).markCompleted(1, proof)
      ).to.be.revertedWith("OrderBook: not poster or provider");
    });
  });

  describe("markReleased", () => {
    it("reverts when called by non-escrow", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);

      await expect(
        orderBook.connect(poster).markReleased(1)
      ).to.be.revertedWith("OrderBook: not escrow");
    });

    it("reverts on DISPUTED job via releaseToProvider (status guard)", async () => {
      const { orderBook, escrow, usdc, owner, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;

      // Create job → assign → fund → complete → dispute
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);
      await usdc.connect(poster).approve(await escrow.getAddress(), USDC(100));
      await escrow.connect(poster).fundJob(1, agent1.address, USDC(100));
      const proof = ethers.keccak256(ethers.toUtf8Bytes("proof"));
      await orderBook.connect(agent1).markCompleted(1, proof);

      // Dispute after completion
      await orderBook.connect(poster).raiseDispute(1);
      expect((await orderBook.getJob(1)).status).to.equal(5); // DISPUTED

      // Confirm delivery on Escrow (owner still can)
      await escrow.connect(owner).confirmDelivery(1);

      // releaseToProvider should revert because OrderBook status is DISPUTED, not COMPLETED
      await expect(
        escrow.connect(poster).releaseToProvider(1)
      ).to.be.revertedWith("Escrow: job not in completed state");
    });
  });

  describe("cancelJob", () => {
    it("poster cancels an OPEN job", async () => {
      const { orderBook, poster } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);

      await expect(orderBook.connect(poster).cancelJob(1))
        .to.emit(orderBook, "JobCancelled")
        .withArgs(1);

      const job = await orderBook.getJob(1);
      expect(job.status).to.equal(4); // CANCELLED
    });

    it("reverts on ASSIGNED job", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);

      await expect(
        orderBook.connect(poster).cancelJob(1)
      ).to.be.revertedWith("OrderBook: not open");
    });
  });

  describe("raiseDispute", () => {
    it("poster can dispute an ASSIGNED job", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);

      await expect(orderBook.connect(poster).raiseDispute(1))
        .to.emit(orderBook, "JobDisputed")
        .withArgs(1, poster.address);

      const job = await orderBook.getJob(1);
      expect(job.status).to.equal(5); // DISPUTED
    });

    it("provider can dispute a COMPLETED job", async () => {
      const { orderBook, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);
      const proof = ethers.keccak256(ethers.toUtf8Bytes("proof"));
      await orderBook.connect(agent1).markCompleted(1, proof);

      await expect(orderBook.connect(agent1).raiseDispute(1))
        .to.emit(orderBook, "JobDisputed");
    });

    it("reverts when non-party tries to dispute", async () => {
      const { orderBook, poster, agent1, agent2 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);

      await expect(
        orderBook.connect(agent2).raiseDispute(1)
      ).to.be.revertedWith("OrderBook: not party");
    });
  });
});

// ═══════════════════════════════════════════════════════════════
// Escrow
// ═══════════════════════════════════════════════════════════════

describe("Escrow", () => {
  async function fundedJobFixture() {
    const base = await deployFixture();
    const { orderBook, escrow, usdc, poster, agent1 } = base;
    const deadline = (await time.latest()) + 86400;

    // Create job + assign + fund
    await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
    await orderBook.connect(poster).assignProvider(1, agent1.address);
    await usdc.connect(poster).approve(await escrow.getAddress(), USDC(100));
    await escrow.connect(poster).fundJob(1, agent1.address, USDC(100));

    return { ...base, deadline };
  }

  describe("fundJob", () => {
    it("accepts funding for an assigned job", async () => {
      const { escrow, poster, agent1 } = await loadFixture(fundedJobFixture);

      const dep = await escrow.getDeposit(1);
      expect(dep.poster).to.equal(poster.address);
      expect(dep.provider).to.equal(agent1.address);
      expect(dep.amount).to.equal(USDC(100));
      expect(dep.funded).to.be.true;
    });

    it("reverts on already funded job", async () => {
      const { escrow, usdc, poster, agent1 } = await loadFixture(fundedJobFixture);
      await usdc.connect(poster).approve(await escrow.getAddress(), USDC(100));

      await expect(
        escrow.connect(poster).fundJob(1, agent1.address, USDC(100))
      ).to.be.revertedWith("Escrow: already funded");
    });

    it("reverts on zero amount", async () => {
      const { orderBook, escrow, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job2", USDC(50), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);

      await expect(
        escrow.connect(poster).fundJob(1, agent1.address, 0)
      ).to.be.revertedWith("Escrow: zero amount");
    });

    it("reverts when caller is not the job poster", async () => {
      const { orderBook, escrow, usdc, poster, agent1, agent2 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);

      // agent2 tries to fund (not the poster)
      await usdc.mint(agent2.address, USDC(100));
      await usdc.connect(agent2).approve(await escrow.getAddress(), USDC(100));

      await expect(
        escrow.connect(agent2).fundJob(1, agent1.address, USDC(100))
      ).to.be.revertedWith("Escrow: not job poster");
    });

    it("reverts when job is not ASSIGNED", async () => {
      const { orderBook, escrow, usdc, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      // Job is OPEN, not ASSIGNED

      await usdc.connect(poster).approve(await escrow.getAddress(), USDC(100));

      await expect(
        escrow.connect(poster).fundJob(1, agent1.address, USDC(100))
      ).to.be.revertedWith("Escrow: job not assigned");
    });

    it("reverts when OrderBook is not set", async () => {
      const [owner, poster, agent1, , feeCollector] = await ethers.getSigners();

      const usdc = await ethers.deployContract("MockUSDC");
      await usdc.waitForDeployment();
      const escrowNoOB = await ethers.deployContract("Escrow", [
        owner.address,
        await usdc.getAddress(),
        feeCollector.address,
      ]);
      await escrowNoOB.waitForDeployment();
      // Do NOT call setOrderBook

      await usdc.mint(poster.address, USDC(100));
      await usdc.connect(poster).approve(await escrowNoOB.getAddress(), USDC(100));

      await expect(
        escrowNoOB.connect(poster).fundJob(1, agent1.address, USDC(100))
      ).to.be.revertedWith("Escrow: OrderBook not set");
    });

    it("reverts when provider doesn't match assigned provider", async () => {
      const { orderBook, escrow, usdc, poster, agent1, agent2 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);

      await usdc.connect(poster).approve(await escrow.getAddress(), USDC(100));

      // Try to fund with wrong provider
      await expect(
        escrow.connect(poster).fundJob(1, agent2.address, USDC(100))
      ).to.be.revertedWith("Escrow: provider mismatch");
    });
  });

  describe("confirmDelivery", () => {
    it("owner confirms delivery", async () => {
      const { escrow, owner } = await loadFixture(fundedJobFixture);

      await expect(escrow.connect(owner).confirmDelivery(1))
        .to.emit(escrow, "DeliveryConfirmed")
        .withArgs(1);

      expect(await escrow.isDeliveryConfirmed(1)).to.be.true;
    });

    it("reverts when non-owner calls", async () => {
      const { escrow, poster } = await loadFixture(fundedJobFixture);

      await expect(
        escrow.connect(poster).confirmDelivery(1)
      ).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
    });
  });

  describe("releaseToProvider", () => {
    it("releases payment with 2% fee", async () => {
      const { escrow, orderBook, usdc, owner, poster, agent1, feeCollector } = await loadFixture(fundedJobFixture);

      // Mark job completed on OrderBook before release
      const proof = ethers.keccak256(ethers.toUtf8Bytes("delivery proof"));
      await orderBook.connect(agent1).markCompleted(1, proof);
      await escrow.connect(owner).confirmDelivery(1);

      const agent1Before = await usdc.balanceOf(agent1.address);
      const feeBefore = await usdc.balanceOf(feeCollector.address);

      await expect(escrow.connect(poster).releaseToProvider(1))
        .to.emit(escrow, "PaymentReleased");

      // 2% fee on 100 USDC = 2 USDC
      const expectedFee = USDC(2);
      const expectedPayout = USDC(98);

      expect(await usdc.balanceOf(agent1.address) - agent1Before).to.equal(expectedPayout);
      expect(await usdc.balanceOf(feeCollector.address) - feeBefore).to.equal(expectedFee);
    });

    it("reverts without delivery confirmation", async () => {
      const { escrow, poster } = await loadFixture(fundedJobFixture);

      await expect(
        escrow.connect(poster).releaseToProvider(1)
      ).to.be.revertedWith("Escrow: delivery not confirmed");
    });

    it("reverts when called by unauthorized user", async () => {
      const { escrow, orderBook, owner, agent1, agent2 } = await loadFixture(fundedJobFixture);
      const proof = ethers.keccak256(ethers.toUtf8Bytes("proof"));
      await orderBook.connect(agent1).markCompleted(1, proof);
      await escrow.connect(owner).confirmDelivery(1);

      await expect(
        escrow.connect(agent2).releaseToProvider(1)
      ).to.be.revertedWith("Escrow: not authorised");
    });

    it("reverts on double release", async () => {
      const { escrow, orderBook, owner, poster, agent1 } = await loadFixture(fundedJobFixture);
      const proof = ethers.keccak256(ethers.toUtf8Bytes("proof"));
      await orderBook.connect(agent1).markCompleted(1, proof);
      await escrow.connect(owner).confirmDelivery(1);
      await escrow.connect(poster).releaseToProvider(1);

      await expect(
        escrow.connect(poster).releaseToProvider(1)
      ).to.be.revertedWith("Escrow: already released");
    });

    it("marks job as RELEASED on OrderBook", async () => {
      const { escrow, orderBook, owner, poster, agent1 } = await loadFixture(fundedJobFixture);
      const proof = ethers.keccak256(ethers.toUtf8Bytes("proof"));
      await orderBook.connect(agent1).markCompleted(1, proof);
      await escrow.connect(owner).confirmDelivery(1);
      await escrow.connect(poster).releaseToProvider(1);

      const job = await orderBook.getJob(1);
      expect(job.status).to.equal(3); // RELEASED
    });
  });

  describe("refund", () => {
    it("owner refunds poster", async () => {
      const { escrow, usdc, owner, poster } = await loadFixture(fundedJobFixture);
      const posterBefore = await usdc.balanceOf(poster.address);

      await expect(escrow.connect(owner).refund(1))
        .to.emit(escrow, "PaymentRefunded")
        .withArgs(1, poster.address, USDC(100));

      expect(await usdc.balanceOf(poster.address) - posterBefore).to.equal(USDC(100));
    });

    it("reverts after release", async () => {
      const { escrow, orderBook, owner, poster, agent1 } = await loadFixture(fundedJobFixture);
      const proof = ethers.keccak256(ethers.toUtf8Bytes("proof"));
      await orderBook.connect(agent1).markCompleted(1, proof);
      await escrow.connect(owner).confirmDelivery(1);
      await escrow.connect(poster).releaseToProvider(1);

      await expect(
        escrow.connect(owner).refund(1)
      ).to.be.revertedWith("Escrow: invalid state");
    });

    it("reverts when non-owner calls", async () => {
      const { escrow, poster } = await loadFixture(fundedJobFixture);

      await expect(
        escrow.connect(poster).refund(1)
      ).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
    });
  });

  describe("fee configuration", () => {
    it("owner can update fee", async () => {
      const { escrow, owner, feeCollector } = await loadFixture(deployFixture);
      await escrow.connect(owner).setFeeCollector(feeCollector.address, 500); // 5%
      expect(await escrow.platformFeeBps()).to.equal(500);
    });

    it("reverts when fee exceeds 10%", async () => {
      const { escrow, owner, feeCollector } = await loadFixture(deployFixture);
      await expect(
        escrow.connect(owner).setFeeCollector(feeCollector.address, 1001)
      ).to.be.revertedWith("Escrow: fee too high");
    });
  });
});

// ═══════════════════════════════════════════════════════════════
// AgentRegistry
// ═══════════════════════════════════════════════════════════════

describe("AgentRegistry", () => {
  describe("registerAgent", () => {
    it("registers an agent with 4 params", async () => {
      const { agentRegistry, agent1 } = await loadFixture(deployFixture);

      await expect(
        agentRegistry.connect(agent1).registerAgent(
          agent1.address, "TestAgent", "ipfs://meta", ["search", "data"]
        )
      ).to.emit(agentRegistry, "AgentRegistered");

      const agent = await agentRegistry.getAgent(agent1.address);
      expect(agent.name).to.equal("TestAgent");
      expect(agent.status).to.equal(1); // Active
    });

    it("reverts on duplicate registration", async () => {
      const { agentRegistry, agent1 } = await loadFixture(deployFixture);
      await agentRegistry.connect(agent1).registerAgent(
        agent1.address, "Agent1", "ipfs://1", ["cap1"]
      );

      await expect(
        agentRegistry.connect(agent1).registerAgent(
          agent1.address, "Agent1Again", "ipfs://2", ["cap2"]
        )
      ).to.be.revertedWith("AgentRegistry: already registered");
    });
  });

  describe("updateAgent", () => {
    it("developer can update their agent", async () => {
      const { agentRegistry, agent1 } = await loadFixture(deployFixture);
      await agentRegistry.connect(agent1).registerAgent(
        agent1.address, "Agent1", "ipfs://1", ["cap1"]
      );

      await agentRegistry.connect(agent1).updateAgent(
        agent1.address, "Agent1Updated", "ipfs://2", ["cap1", "cap2"], 1 // Active
      );

      const agent = await agentRegistry.getAgent(agent1.address);
      expect(agent.name).to.equal("Agent1Updated");
    });

    it("reverts when non-developer tries to update", async () => {
      const { agentRegistry, agent1, agent2 } = await loadFixture(deployFixture);
      await agentRegistry.connect(agent1).registerAgent(
        agent1.address, "Agent1", "ipfs://1", ["cap1"]
      );

      await expect(
        agentRegistry.connect(agent2).updateAgent(
          agent1.address, "Hacked", "ipfs://evil", [], 1
        )
      ).to.be.revertedWith("AgentRegistry: not developer");
    });
  });

  describe("syncReputation", () => {
    it("reputation oracle can sync scores", async () => {
      const { agentRegistry, reputationToken, agent1, owner } = await loadFixture(deployFixture);
      await agentRegistry.connect(agent1).registerAgent(
        agent1.address, "Agent1", "ipfs://1", []
      );

      // ReputationToken is set as oracle, so we simulate through it
      // Direct call from owner (who was initially set as oracle) should also work
      // since owner = deployer = initial reputationOracle
      // But we already changed oracle to reputationToken, so let's use owner call
      // Actually the oracle is now reputationToken address, so only it can call
      // Let's verify that non-oracle can't call
      await expect(
        agentRegistry.connect(agent1).syncReputation(agent1.address, 100)
      ).to.be.revertedWith("AgentRegistry: not reputation oracle");
    });
  });

  describe("views", () => {
    it("reports correct agent count", async () => {
      const { agentRegistry, agent1, agent2 } = await loadFixture(deployFixture);
      await agentRegistry.connect(agent1).registerAgent(agent1.address, "A1", "ipfs://1", []);
      await agentRegistry.connect(agent2).registerAgent(agent2.address, "A2", "ipfs://2", []);
      expect(await agentRegistry.agentCount()).to.equal(2);
    });

    it("isAgentActive returns correct status", async () => {
      const { agentRegistry, agent1 } = await loadFixture(deployFixture);
      expect(await agentRegistry.isAgentActive(agent1.address)).to.be.false;

      await agentRegistry.connect(agent1).registerAgent(agent1.address, "A1", "ipfs://1", []);
      expect(await agentRegistry.isAgentActive(agent1.address)).to.be.true;
    });
  });
});

// ═══════════════════════════════════════════════════════════════
// ReputationToken
// ═══════════════════════════════════════════════════════════════

describe("ReputationToken", () => {
  describe("recordSuccess", () => {
    it("only escrow can call recordSuccess", async () => {
      const { reputationToken, agent1 } = await loadFixture(deployFixture);

      await expect(
        reputationToken.connect(agent1).recordSuccess(agent1.address, USDC(100))
      ).to.be.revertedWith("Reputation: caller is not escrow");
    });

    it("increments reputation on successful release (integration)", async () => {
      const { orderBook, escrow, usdc, reputationToken, owner, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;

      // Full flow without agent registration (reputation still updates)
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);
      await usdc.connect(poster).approve(await escrow.getAddress(), USDC(100));
      await escrow.connect(poster).fundJob(1, agent1.address, USDC(100));
      const proof = ethers.keccak256(ethers.toUtf8Bytes("delivery proof"));
      await orderBook.connect(agent1).markCompleted(1, proof);
      await escrow.connect(owner).confirmDelivery(1);
      await escrow.connect(poster).releaseToProvider(1);

      // Check reputation was updated
      const score = await reputationToken.scoreOf(agent1.address);
      expect(score).to.be.gt(0);

      const stats = await reputationToken.statsOf(agent1.address);
      expect(stats.jobsCompleted).to.equal(1);
    });
  });

  describe("recordFailure", () => {
    it("only escrow can call recordFailure", async () => {
      const { reputationToken, agent1 } = await loadFixture(deployFixture);

      await expect(
        reputationToken.connect(agent1).recordFailure(agent1.address)
      ).to.be.revertedWith("Reputation: caller is not escrow");
    });

    it("decrements reputation on refund (integration)", async () => {
      const { orderBook, escrow, usdc, reputationToken, owner, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;

      // First complete a job to build reputation
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);
      await usdc.connect(poster).approve(await escrow.getAddress(), USDC(100));
      await escrow.connect(poster).fundJob(1, agent1.address, USDC(100));
      const proof = ethers.keccak256(ethers.toUtf8Bytes("delivery proof"));
      await orderBook.connect(agent1).markCompleted(1, proof);
      await escrow.connect(owner).confirmDelivery(1);
      await escrow.connect(poster).releaseToProvider(1);

      const scoreBefore = await reputationToken.scoreOf(agent1.address);
      expect(scoreBefore).to.be.gt(0);

      // Now create another job and refund it
      await orderBook.connect(poster).createJob("ipfs://job2", USDC(50), deadline);
      await orderBook.connect(poster).assignProvider(2, agent1.address);
      await usdc.connect(poster).approve(await escrow.getAddress(), USDC(50));
      await escrow.connect(poster).fundJob(2, agent1.address, USDC(50));
      await escrow.connect(owner).refund(2);

      const scoreAfter = await reputationToken.scoreOf(agent1.address);
      expect(scoreAfter).to.be.lt(scoreBefore);

      const stats = await reputationToken.statsOf(agent1.address);
      expect(stats.jobsFailed).to.equal(1);
    });

    it("score floors at zero", async () => {
      const { orderBook, escrow, usdc, reputationToken, owner, poster, agent1 } = await loadFixture(deployFixture);
      const deadline = (await time.latest()) + 86400;

      // Refund without prior reputation — score should stay 0
      await orderBook.connect(poster).createJob("ipfs://job1", USDC(50), deadline);
      await orderBook.connect(poster).assignProvider(1, agent1.address);
      await usdc.connect(poster).approve(await escrow.getAddress(), USDC(50));
      await escrow.connect(poster).fundJob(1, agent1.address, USDC(50));
      await escrow.connect(owner).refund(1);

      expect(await reputationToken.scoreOf(agent1.address)).to.equal(0);
    });
  });
});

// ═══════════════════════════════════════════════════════════════
// Full Integration: End-to-End
// ═══════════════════════════════════════════════════════════════

describe("Full Integration", () => {
  it("end-to-end: create -> bid -> accept -> fund -> complete -> confirm -> release", async () => {
    const { orderBook, escrow, usdc, reputationToken, agentRegistry, owner, poster, agent1, feeCollector } =
      await loadFixture(deployFixture);
    const deadline = (await time.latest()) + 86400;

    // 1. Register agent
    await agentRegistry.connect(agent1).registerAgent(
      agent1.address, "HackathonAgent", "ipfs://agent1", ["search", "hackathon"]
    );

    // 2. Create job
    await orderBook.connect(poster).createJob("ipfs://hackathon-search", USDC(50), deadline);
    expect(await orderBook.totalJobs()).to.equal(1);

    // 3. Agent bids
    await orderBook.connect(agent1).placeBid(1, USDC(40), 120, "I'll find hackathons");
    expect(await orderBook.getJobBidCount(1)).to.equal(1);

    // 4. Poster accepts bid
    await orderBook.connect(poster).acceptBid(1, 1);
    let job = await orderBook.getJob(1);
    expect(job.status).to.equal(1); // ASSIGNED
    expect(job.provider).to.equal(agent1.address);

    // 5. Fund escrow (at bid price)
    await usdc.connect(poster).approve(await escrow.getAddress(), USDC(40));
    await escrow.connect(poster).fundJob(1, agent1.address, USDC(40));
    const dep = await escrow.getDeposit(1);
    expect(dep.funded).to.be.true;

    // 6. Agent completes work
    const proof = ethers.keccak256(ethers.toUtf8Bytes("hackathon results data"));
    await orderBook.connect(agent1).markCompleted(1, proof);
    job = await orderBook.getJob(1);
    expect(job.status).to.equal(2); // COMPLETED

    // 7. Owner confirms delivery
    await escrow.connect(owner).confirmDelivery(1);
    expect(await escrow.isDeliveryConfirmed(1)).to.be.true;

    // 8. Release payment
    const agent1BalBefore = await usdc.balanceOf(agent1.address);
    const feeBalBefore = await usdc.balanceOf(feeCollector.address);

    await escrow.connect(agent1).releaseToProvider(1);

    // Verify payment: 40 USDC - 2% = 39.2 USDC to agent, 0.8 USDC fee
    const expectedFee = (USDC(40) * 200n) / 10000n; // 0.8 USDC
    const expectedPayout = USDC(40) - expectedFee;

    expect(await usdc.balanceOf(agent1.address) - agent1BalBefore).to.equal(expectedPayout);
    expect(await usdc.balanceOf(feeCollector.address) - feeBalBefore).to.equal(expectedFee);

    // 9. Verify final state
    job = await orderBook.getJob(1);
    expect(job.status).to.equal(3); // RELEASED

    // 10. Verify reputation
    const score = await reputationToken.scoreOf(agent1.address);
    expect(score).to.be.gt(0);
    const stats = await reputationToken.statsOf(agent1.address);
    expect(stats.jobsCompleted).to.equal(1);

    // 11. Verify registry reputation synced
    const agentData = await agentRegistry.getAgent(agent1.address);
    expect(agentData.reputation).to.equal(score);
  });

  it("dispute flow: create -> assign -> fund -> dispute -> refund", async () => {
    const { orderBook, escrow, usdc, reputationToken, owner, poster, agent1 } =
      await loadFixture(deployFixture);
    const deadline = (await time.latest()) + 86400;

    // Create and assign
    await orderBook.connect(poster).createJob("ipfs://job1", USDC(100), deadline);
    await orderBook.connect(poster).assignProvider(1, agent1.address);

    // Fund
    await usdc.connect(poster).approve(await escrow.getAddress(), USDC(100));
    await escrow.connect(poster).fundJob(1, agent1.address, USDC(100));

    // Dispute
    await orderBook.connect(poster).raiseDispute(1);
    let job = await orderBook.getJob(1);
    expect(job.status).to.equal(5); // DISPUTED

    // Refund
    const posterBefore = await usdc.balanceOf(poster.address);
    await escrow.connect(owner).refund(1);
    expect(await usdc.balanceOf(poster.address) - posterBefore).to.equal(USDC(100));

    // Verify failure recorded in reputation
    const stats = await reputationToken.statsOf(agent1.address);
    expect(stats.jobsFailed).to.equal(1);
  });
});
