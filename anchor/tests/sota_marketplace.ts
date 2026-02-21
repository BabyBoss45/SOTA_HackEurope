import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { SotaMarketplace } from "../target/types/sota_marketplace";
import {
  createMint,
  mintTo,
  getOrCreateAssociatedTokenAccount,
  getAccount,
  TOKEN_PROGRAM_ID,
} from "@solana/spl-token";
import { expect } from "chai";
import { PublicKey, Keypair, SystemProgram } from "@solana/web3.js";
import BN from "bn.js";

const USDC = (n: number) => new BN(n * 1_000_000);

describe("sota_marketplace", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  const program = anchor.workspace
    .SotaMarketplace as Program<SotaMarketplace>;
  const authority = provider.wallet as anchor.Wallet;

  let usdcMint: PublicKey;
  let poster = Keypair.generate();
  let agent1 = Keypair.generate();
  let agent2 = Keypair.generate();
  let feeCollector = Keypair.generate();
  let configPda: PublicKey;
  let configBump: number;

  before(async () => {
    // Airdrop SOL to test accounts
    const airdropAmount = 10 * anchor.web3.LAMPORTS_PER_SOL;
    for (const kp of [poster, agent1, agent2, feeCollector]) {
      const sig = await provider.connection.requestAirdrop(
        kp.publicKey,
        airdropAmount
      );
      await provider.connection.confirmTransaction(sig);
    }

    // Create USDC mock mint (6 decimals)
    usdcMint = await createMint(
      provider.connection,
      (authority as any).payer,
      authority.publicKey, // mint authority
      null,
      6
    );

    // Derive config PDA
    [configPda, configBump] = PublicKey.findProgramAddressSync(
      [Buffer.from("config")],
      program.programId
    );
  });

  // ═══════════════════════════════════════════════════════════
  // Initialize
  // ═══════════════════════════════════════════════════════════

  describe("initialize", () => {
    it("initializes marketplace config", async () => {
      await program.methods
        .initialize(200) // 2% fee
        .accounts({
          config: configPda,
          authority: authority.publicKey,
          usdcMint,
          feeCollector: feeCollector.publicKey,
          systemProgram: SystemProgram.programId,
        })
        .rpc();

      const config = await program.account.marketplaceConfig.fetch(configPda);
      expect(config.authority.toString()).to.equal(
        authority.publicKey.toString()
      );
      expect(config.usdcMint.toString()).to.equal(usdcMint.toString());
      expect(config.platformFeeBps).to.equal(200);
      expect(config.nextJobId.toNumber()).to.equal(1);
      expect(config.nextBidId.toNumber()).to.equal(1);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // OrderBook: createJob
  // ═══════════════════════════════════════════════════════════

  describe("createJob", () => {
    it("creates a job with correct parameters", async () => {
      const config = await program.account.marketplaceConfig.fetch(configPda);
      const jobId = config.nextJobId;
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      const deadline = Math.floor(Date.now() / 1000) + 86400;

      await program.methods
        .createJob("ipfs://job1", USDC(100), new BN(deadline))
        .accounts({
          config: configPda,
          job: jobPda,
          poster: poster.publicKey,
          systemProgram: SystemProgram.programId,
        })
        .signers([poster])
        .rpc();

      const job = await program.account.job.fetch(jobPda);
      expect(job.poster.toString()).to.equal(poster.publicKey.toString());
      expect(job.maxBudgetUsdc.toNumber()).to.equal(USDC(100).toNumber());
      expect(JSON.stringify(job.status)).to.equal(JSON.stringify({ open: {} }));
    });

    it("reverts on zero budget", async () => {
      const config = await program.account.marketplaceConfig.fetch(configPda);
      const jobId = config.nextJobId;
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      const deadline = Math.floor(Date.now() / 1000) + 86400;

      try {
        await program.methods
          .createJob("ipfs://job1", new BN(0), new BN(deadline))
          .accounts({
            config: configPda,
            job: jobPda,
            poster: poster.publicKey,
            systemProgram: SystemProgram.programId,
          })
          .signers([poster])
          .rpc();
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.error?.errorCode?.code).to.equal("ZeroBudget");
      }
    });

    it("reverts on past deadline", async () => {
      const config = await program.account.marketplaceConfig.fetch(configPda);
      const jobId = config.nextJobId;
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      const pastDeadline = Math.floor(Date.now() / 1000) - 100;

      try {
        await program.methods
          .createJob("ipfs://job1", USDC(100), new BN(pastDeadline))
          .accounts({
            config: configPda,
            job: jobPda,
            poster: poster.publicKey,
            systemProgram: SystemProgram.programId,
          })
          .signers([poster])
          .rpc();
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.error?.errorCode?.code).to.equal("PastDeadline");
      }
    });
  });

  // ═══════════════════════════════════════════════════════════
  // OrderBook: placeBid
  // ═══════════════════════════════════════════════════════════

  describe("placeBid", () => {
    it("places a valid bid", async () => {
      // Job 1 was created above
      const jobId = new BN(1);
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      const config = await program.account.marketplaceConfig.fetch(configPda);
      const bidId = config.nextBidId;
      const [bidPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("bid"), bidId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      await program.methods
        .placeBid(USDC(80), new BN(3600), "I can do this")
        .accounts({
          config: configPda,
          job: jobPda,
          bid: bidPda,
          agent: agent1.publicKey,
          systemProgram: SystemProgram.programId,
        })
        .signers([agent1])
        .rpc();

      const bid = await program.account.bid.fetch(bidPda);
      expect(bid.priceUsdc.toNumber()).to.equal(USDC(80).toNumber());
      expect(bid.agent.toString()).to.equal(agent1.publicKey.toString());
      expect(bid.accepted).to.be.false;
    });

    it("reverts when bid exceeds budget", async () => {
      const jobId = new BN(1);
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      const config = await program.account.marketplaceConfig.fetch(configPda);
      const bidId = config.nextBidId;
      const [bidPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("bid"), bidId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      try {
        await program.methods
          .placeBid(USDC(150), new BN(3600), "Too expensive")
          .accounts({
            config: configPda,
            job: jobPda,
            bid: bidPda,
            agent: agent1.publicKey,
            systemProgram: SystemProgram.programId,
          })
          .signers([agent1])
          .rpc();
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.error?.errorCode?.code).to.equal("BidExceedsBudget");
      }
    });

    it("reverts when poster tries to bid on own job", async () => {
      const jobId = new BN(1);
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      const config = await program.account.marketplaceConfig.fetch(configPda);
      const bidId = config.nextBidId;
      const [bidPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("bid"), bidId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      try {
        await program.methods
          .placeBid(USDC(80), new BN(3600), "Self bid")
          .accounts({
            config: configPda,
            job: jobPda,
            bid: bidPda,
            agent: poster.publicKey,
            systemProgram: SystemProgram.programId,
          })
          .signers([poster])
          .rpc();
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.error?.errorCode?.code).to.equal("PosterCannotBid");
      }
    });
  });

  // ═══════════════════════════════════════════════════════════
  // OrderBook: acceptBid
  // ═══════════════════════════════════════════════════════════

  describe("acceptBid", () => {
    it("poster accepts a bid and assigns provider", async () => {
      const jobId = new BN(1);
      const bidId = new BN(1);
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const [bidPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("bid"), bidId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      await program.methods
        .acceptBid()
        .accounts({
          job: jobPda,
          bid: bidPda,
          poster: poster.publicKey,
        })
        .signers([poster])
        .rpc();

      const job = await program.account.job.fetch(jobPda);
      expect(job.provider.toString()).to.equal(agent1.publicKey.toString());
      expect(JSON.stringify(job.status)).to.equal(
        JSON.stringify({ assigned: {} })
      );

      const bid = await program.account.bid.fetch(bidPda);
      expect(bid.accepted).to.be.true;
    });

    it("reverts when non-poster tries to accept", async () => {
      // Create a new job and bid for this test
      const config = await program.account.marketplaceConfig.fetch(configPda);
      const newJobId = config.nextJobId;
      const [newJobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), newJobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const deadline = Math.floor(Date.now() / 1000) + 86400;

      await program.methods
        .createJob("ipfs://job2", USDC(200), new BN(deadline))
        .accounts({
          config: configPda,
          job: newJobPda,
          poster: poster.publicKey,
          systemProgram: SystemProgram.programId,
        })
        .signers([poster])
        .rpc();

      const config2 = await program.account.marketplaceConfig.fetch(configPda);
      const newBidId = config2.nextBidId;
      const [newBidPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("bid"), newBidId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      await program.methods
        .placeBid(USDC(150), new BN(3600), "bid")
        .accounts({
          config: configPda,
          job: newJobPda,
          bid: newBidPda,
          agent: agent1.publicKey,
          systemProgram: SystemProgram.programId,
        })
        .signers([agent1])
        .rpc();

      try {
        await program.methods
          .acceptBid()
          .accounts({
            job: newJobPda,
            bid: newBidPda,
            poster: agent2.publicKey,
          })
          .signers([agent2])
          .rpc();
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.error?.errorCode?.code).to.equal("NotPoster");
      }
    });
  });

  // ═══════════════════════════════════════════════════════════
  // OrderBook: assignProvider (direct)
  // ═══════════════════════════════════════════════════════════

  describe("assignProvider", () => {
    it("directly assigns a provider", async () => {
      const config = await program.account.marketplaceConfig.fetch(configPda);
      const jobId = config.nextJobId;
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const deadline = Math.floor(Date.now() / 1000) + 86400;

      await program.methods
        .createJob("ipfs://job-assign", USDC(100), new BN(deadline))
        .accounts({
          config: configPda,
          job: jobPda,
          poster: poster.publicKey,
          systemProgram: SystemProgram.programId,
        })
        .signers([poster])
        .rpc();

      await program.methods
        .assignProvider()
        .accounts({
          job: jobPda,
          poster: poster.publicKey,
          provider: agent1.publicKey,
        })
        .signers([poster])
        .rpc();

      const job = await program.account.job.fetch(jobPda);
      expect(JSON.stringify(job.status)).to.equal(
        JSON.stringify({ assigned: {} })
      );
      expect(job.provider.toString()).to.equal(agent1.publicKey.toString());
    });
  });

  // ═══════════════════════════════════════════════════════════
  // OrderBook: markCompleted
  // ═══════════════════════════════════════════════════════════

  describe("markCompleted", () => {
    it("provider marks job as completed", async () => {
      // Use job 1 which is assigned to agent1
      const jobId = new BN(1);
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      const proof = Buffer.alloc(32);
      Buffer.from("delivery proof").copy(proof);

      await program.methods
        .markCompleted(Array.from(proof) as any)
        .accounts({
          job: jobPda,
          signer: agent1.publicKey,
        })
        .signers([agent1])
        .rpc();

      const job = await program.account.job.fetch(jobPda);
      expect(JSON.stringify(job.status)).to.equal(
        JSON.stringify({ completed: {} })
      );
    });

    it("reverts when unauthorized user calls", async () => {
      // Job 3 is assigned to agent1
      const jobId = new BN(3);
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      const proof = Buffer.alloc(32);

      try {
        await program.methods
          .markCompleted(Array.from(proof) as any)
          .accounts({
            job: jobPda,
            signer: agent2.publicKey,
          })
          .signers([agent2])
          .rpc();
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.error?.errorCode?.code).to.equal("NotPosterOrProvider");
      }
    });
  });

  // ═══════════════════════════════════════════════════════════
  // OrderBook: cancelJob
  // ═══════════════════════════════════════════════════════════

  describe("cancelJob", () => {
    it("poster cancels an OPEN job", async () => {
      const config = await program.account.marketplaceConfig.fetch(configPda);
      const jobId = config.nextJobId;
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const deadline = Math.floor(Date.now() / 1000) + 86400;

      await program.methods
        .createJob("ipfs://cancel-test", USDC(50), new BN(deadline))
        .accounts({
          config: configPda,
          job: jobPda,
          poster: poster.publicKey,
          systemProgram: SystemProgram.programId,
        })
        .signers([poster])
        .rpc();

      await program.methods
        .cancelJob()
        .accounts({
          job: jobPda,
          poster: poster.publicKey,
        })
        .signers([poster])
        .rpc();

      const job = await program.account.job.fetch(jobPda);
      expect(JSON.stringify(job.status)).to.equal(
        JSON.stringify({ cancelled: {} })
      );
    });
  });

  // ═══════════════════════════════════════════════════════════
  // OrderBook: raiseDispute
  // ═══════════════════════════════════════════════════════════

  describe("raiseDispute", () => {
    it("poster can dispute a COMPLETED job", async () => {
      // Job 1 is completed
      const jobId = new BN(1);
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const [depositPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("deposit"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      await program.methods
        .raiseDispute()
        .accounts({
          job: jobPda,
          deposit: depositPda,
          signer: poster.publicKey,
        })
        .signers([poster])
        .rpc();

      const job = await program.account.job.fetch(jobPda);
      expect(JSON.stringify(job.status)).to.equal(
        JSON.stringify({ disputed: {} })
      );
    });

    it("reverts when non-party tries to dispute", async () => {
      // Job 3 is assigned
      const jobId = new BN(3);
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const [depositPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("deposit"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      try {
        await program.methods
          .raiseDispute()
          .accounts({
            job: jobPda,
            deposit: depositPda,
            signer: agent2.publicKey,
          })
          .signers([agent2])
          .rpc();
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.error?.errorCode?.code).to.equal("NotParty");
      }
    });
  });

  // ═══════════════════════════════════════════════════════════
  // Registry: registerAgent
  // ═══════════════════════════════════════════════════════════

  describe("registerAgent", () => {
    it("registers an agent with correct parameters", async () => {
      const [agentPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("agent"), agent1.publicKey.toBuffer()],
        program.programId
      );
      const [repPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("reputation"), agent1.publicKey.toBuffer()],
        program.programId
      );

      await program.methods
        .registerAgent("TestAgent", "ipfs://meta", ["search", "data"])
        .accounts({
          agent: agentPda,
          reputation: repPda,
          wallet: agent1.publicKey,
          developer: agent1.publicKey,
          systemProgram: SystemProgram.programId,
        })
        .signers([agent1])
        .rpc();

      const agent = await program.account.agent.fetch(agentPda);
      expect(agent.name).to.equal("TestAgent");
      expect(JSON.stringify(agent.status)).to.equal(
        JSON.stringify({ active: {} })
      );
      expect(agent.capabilities).to.deep.equal(["search", "data"]);

      const rep = await program.account.reputation.fetch(repPda);
      expect(rep.score.toNumber()).to.equal(0);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // Registry: updateAgent
  // ═══════════════════════════════════════════════════════════

  describe("updateAgent", () => {
    it("developer can update their agent", async () => {
      const [agentPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("agent"), agent1.publicKey.toBuffer()],
        program.programId
      );

      await program.methods
        .updateAgent("Agent1Updated", "ipfs://meta2", ["search", "data", "ai"], 1)
        .accounts({
          agent: agentPda,
          developer: agent1.publicKey,
        })
        .signers([agent1])
        .rpc();

      const agent = await program.account.agent.fetch(agentPda);
      expect(agent.name).to.equal("Agent1Updated");
    });

    it("reverts when non-developer tries to update", async () => {
      const [agentPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("agent"), agent1.publicKey.toBuffer()],
        program.programId
      );

      try {
        await program.methods
          .updateAgent("Hacked", "ipfs://evil", [], 1)
          .accounts({
            agent: agentPda,
            developer: agent2.publicKey,
          })
          .signers([agent2])
          .rpc();
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.error?.errorCode?.code).to.equal("NotDeveloper");
      }
    });
  });

  // ═══════════════════════════════════════════════════════════
  // Escrow: Full integration flow
  // ═══════════════════════════════════════════════════════════

  describe("Escrow: fund_job → confirm → release", () => {
    let escrowJobId: BN;
    let escrowJobPda: PublicKey;

    before(async () => {
      // Mint USDC to poster
      const posterAta = await getOrCreateAssociatedTokenAccount(
        provider.connection,
        (authority as any).payer,
        usdcMint,
        poster.publicKey
      );
      await mintTo(
        provider.connection,
        (authority as any).payer,
        usdcMint,
        posterAta.address,
        authority.publicKey,
        10_000_000_000 // 10,000 USDC
      );

      // Create a fresh job for escrow testing
      const config = await program.account.marketplaceConfig.fetch(configPda);
      escrowJobId = config.nextJobId;
      [escrowJobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), escrowJobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const deadline = Math.floor(Date.now() / 1000) + 86400;

      await program.methods
        .createJob("ipfs://escrow-test", USDC(100), new BN(deadline))
        .accounts({
          config: configPda,
          job: escrowJobPda,
          poster: poster.publicKey,
          systemProgram: SystemProgram.programId,
        })
        .signers([poster])
        .rpc();

      // Assign provider
      await program.methods
        .assignProvider()
        .accounts({
          job: escrowJobPda,
          poster: poster.publicKey,
          provider: agent1.publicKey,
        })
        .signers([poster])
        .rpc();
    });

    it("funds escrow with USDC", async () => {
      const [depositPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("deposit"), escrowJobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const [escrowVaultPda] = PublicKey.findProgramAddressSync(
        [
          Buffer.from("escrow_vault"),
          escrowJobId.toArrayLike(Buffer, "le", 8),
        ],
        program.programId
      );
      const posterAta = await getOrCreateAssociatedTokenAccount(
        provider.connection,
        (authority as any).payer,
        usdcMint,
        poster.publicKey
      );

      await program.methods
        .fundJob(USDC(100))
        .accounts({
          config: configPda,
          job: escrowJobPda,
          deposit: depositPda,
          escrowVault: escrowVaultPda,
          posterAta: posterAta.address,
          usdcMint,
          poster: poster.publicKey,
          provider: agent1.publicKey,
          tokenProgram: TOKEN_PROGRAM_ID,
          systemProgram: SystemProgram.programId,
          rent: anchor.web3.SYSVAR_RENT_PUBKEY,
        })
        .signers([poster])
        .rpc();

      const deposit = await program.account.deposit.fetch(depositPda);
      expect(deposit.funded).to.be.true;
      expect(deposit.amount.toNumber()).to.equal(USDC(100).toNumber());

      // Verify escrow vault has the tokens
      const vault = await getAccount(
        provider.connection,
        escrowVaultPda
      );
      expect(Number(vault.amount)).to.equal(USDC(100).toNumber());
    });

    it("confirms delivery", async () => {
      const [depositPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("deposit"), escrowJobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );

      // Mark job completed first
      const proof = Buffer.alloc(32);
      Buffer.from("hackathon results").copy(proof);

      await program.methods
        .markCompleted(Array.from(proof) as any)
        .accounts({
          job: escrowJobPda,
          signer: agent1.publicKey,
        })
        .signers([agent1])
        .rpc();

      // Authority confirms delivery
      await program.methods
        .confirmDelivery()
        .accounts({
          config: configPda,
          deposit: depositPda,
          job: escrowJobPda,
          authority: authority.publicKey,
        })
        .rpc();

      const deposit = await program.account.deposit.fetch(depositPda);
      expect(deposit.deliveryConfirmed).to.be.true;
    });

    it("releases payment to provider with 2% fee", async () => {
      const [depositPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("deposit"), escrowJobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const [escrowVaultPda] = PublicKey.findProgramAddressSync(
        [
          Buffer.from("escrow_vault"),
          escrowJobId.toArrayLike(Buffer, "le", 8),
        ],
        program.programId
      );
      const [repPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("reputation"), agent1.publicKey.toBuffer()],
        program.programId
      );

      const providerAta = await getOrCreateAssociatedTokenAccount(
        provider.connection,
        (authority as any).payer,
        usdcMint,
        agent1.publicKey
      );
      const feeCollectorAta = await getOrCreateAssociatedTokenAccount(
        provider.connection,
        (authority as any).payer,
        usdcMint,
        feeCollector.publicKey
      );

      const providerBefore = Number(
        (await getAccount(provider.connection, providerAta.address)).amount
      );
      const feeBefore = Number(
        (await getAccount(provider.connection, feeCollectorAta.address)).amount
      );

      // Poster releases immediately (no dispute window needed)
      await program.methods
        .releaseToProvider()
        .accounts({
          config: configPda,
          job: escrowJobPda,
          deposit: depositPda,
          escrowVault: escrowVaultPda,
          providerAta: providerAta.address,
          feeCollectorAta: feeCollectorAta.address,
          reputation: repPda,
          signer: poster.publicKey,
          tokenProgram: TOKEN_PROGRAM_ID,
        })
        .signers([poster])
        .rpc();

      // 2% fee on 100 USDC = 2 USDC
      const expectedFee = 2_000_000;
      const expectedPayout = 98_000_000;

      const providerAfter = Number(
        (await getAccount(provider.connection, providerAta.address)).amount
      );
      const feeAfter = Number(
        (await getAccount(provider.connection, feeCollectorAta.address)).amount
      );

      expect(providerAfter - providerBefore).to.equal(expectedPayout);
      expect(feeAfter - feeBefore).to.equal(expectedFee);

      // Verify job status = Released
      const job = await program.account.job.fetch(escrowJobPda);
      expect(JSON.stringify(job.status)).to.equal(
        JSON.stringify({ released: {} })
      );

      // Verify reputation updated
      const rep = await program.account.reputation.fetch(repPda);
      expect(rep.score.toNumber()).to.be.gt(0);
      expect(rep.jobsCompleted.toNumber()).to.equal(1);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // Escrow: refund
  // ═══════════════════════════════════════════════════════════

  describe("Escrow: refund", () => {
    it("owner refunds poster", async () => {
      // Create and fund a job
      const config = await program.account.marketplaceConfig.fetch(configPda);
      const jobId = config.nextJobId;
      const [jobPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("job"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const deadline = Math.floor(Date.now() / 1000) + 86400;

      await program.methods
        .createJob("ipfs://refund-test", USDC(50), new BN(deadline))
        .accounts({
          config: configPda,
          job: jobPda,
          poster: poster.publicKey,
          systemProgram: SystemProgram.programId,
        })
        .signers([poster])
        .rpc();

      await program.methods
        .assignProvider()
        .accounts({
          job: jobPda,
          poster: poster.publicKey,
          provider: agent1.publicKey,
        })
        .signers([poster])
        .rpc();

      const [depositPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("deposit"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const [escrowVaultPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("escrow_vault"), jobId.toArrayLike(Buffer, "le", 8)],
        program.programId
      );
      const posterAta = await getOrCreateAssociatedTokenAccount(
        provider.connection,
        (authority as any).payer,
        usdcMint,
        poster.publicKey
      );

      await program.methods
        .fundJob(USDC(50))
        .accounts({
          config: configPda,
          job: jobPda,
          deposit: depositPda,
          escrowVault: escrowVaultPda,
          posterAta: posterAta.address,
          usdcMint,
          poster: poster.publicKey,
          provider: agent1.publicKey,
          tokenProgram: TOKEN_PROGRAM_ID,
          systemProgram: SystemProgram.programId,
          rent: anchor.web3.SYSVAR_RENT_PUBKEY,
        })
        .signers([poster])
        .rpc();

      const posterBefore = Number(
        (await getAccount(provider.connection, posterAta.address)).amount
      );

      const [repPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("reputation"), agent1.publicKey.toBuffer()],
        program.programId
      );

      await program.methods
        .refund()
        .accounts({
          config: configPda,
          deposit: depositPda,
          job: jobPda,
          escrowVault: escrowVaultPda,
          posterAta: posterAta.address,
          reputation: repPda,
          authority: authority.publicKey,
          tokenProgram: TOKEN_PROGRAM_ID,
        })
        .rpc();

      const posterAfter = Number(
        (await getAccount(provider.connection, posterAta.address)).amount
      );
      expect(posterAfter - posterBefore).to.equal(USDC(50).toNumber());

      // Verify reputation failure recorded
      const rep = await program.account.reputation.fetch(repPda);
      expect(rep.jobsFailed.toNumber()).to.equal(1);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // Fee Configuration
  // ═══════════════════════════════════════════════════════════

  describe("updateFeeConfig", () => {
    it("owner can update fee", async () => {
      await program.methods
        .updateFeeConfig(500) // 5%
        .accounts({
          config: configPda,
          feeCollector: feeCollector.publicKey,
          authority: authority.publicKey,
        })
        .rpc();

      const config = await program.account.marketplaceConfig.fetch(configPda);
      expect(config.platformFeeBps).to.equal(500);

      // Reset back to 2%
      await program.methods
        .updateFeeConfig(200)
        .accounts({
          config: configPda,
          feeCollector: feeCollector.publicKey,
          authority: authority.publicKey,
        })
        .rpc();
    });

    it("reverts when fee exceeds 10%", async () => {
      try {
        await program.methods
          .updateFeeConfig(1001)
          .accounts({
            config: configPda,
            feeCollector: feeCollector.publicKey,
            authority: authority.publicKey,
          })
          .rpc();
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.error?.errorCode?.code).to.equal("FeeTooHigh");
      }
    });
  });
});
