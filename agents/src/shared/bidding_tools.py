"""
Bidding Tools for Archive Agents

Tools for job bidding and contract interactions.
"""

import json
from typing import Optional, Any

from pydantic import Field
from .tool_base import BaseTool

from .contracts import ContractInstances, place_bid, get_job, get_bids_for_job, submit_delivery
from .config import JobType, JOB_TYPE_LABELS


class GetJobDetailsTool(BaseTool):
    """Tool to get job details from blockchain"""
    
    name: str = "get_job_details"
    description: str = """
    Get detailed information about a job from the OrderBook contract.
    Returns job type, description, budget, deadline, and status.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "integer",
                "description": "The job ID to query"
            }
        },
        "required": ["job_id"]
    }
    
    _contracts: Optional[ContractInstances] = None
    
    def set_contracts(self, contracts: ContractInstances):
        self._contracts = contracts
    
    async def execute(self, job_id: int) -> str:
        if not self._contracts:
            return json.dumps({"error": "Contracts not configured"})
        
        try:
            job = get_job(self._contracts, job_id)

            return json.dumps({
                "success": True,
                "job_id": job_id,
                "poster": job["poster"],
                "provider": job["provider"],
                "metadata_uri": job["metadata_uri"],
                "budget_usdc": job["budget_usdc"],
                "deadline": job["deadline"],
                "status": job["status"],
                "status_label": ["OPEN","ASSIGNED","COMPLETED","RELEASED","CANCELLED","DISPUTED"][job["status"]] if job["status"] <= 5 else "UNKNOWN",
            }, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


class ListJobBidsTool(BaseTool):
    """Tool to list bids on a job"""
    
    name: str = "list_job_bids"
    description: str = """
    Get all bids placed on a specific job.
    Useful for understanding competition before bidding.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "integer",
                "description": "The job ID to query bids for"
            }
        },
        "required": ["job_id"]
    }
    
    _contracts: Optional[ContractInstances] = None
    
    def set_contracts(self, contracts: ContractInstances):
        self._contracts = contracts
    
    async def execute(self, job_id: int) -> str:
        if not self._contracts:
            return json.dumps({"error": "Contracts not configured"})
        
        try:
            bids = get_bids_for_job(self._contracts, job_id)
            
            parsed_bids = []
            for i, bid in enumerate(bids):
                # Bid struct: id(0), jobId(1), agent(2), priceUsdc(3),
                #             estimatedTime(4), proposal(5), createdAt(6), accepted(7)
                parsed_bids.append({
                    "bid_id": bid[0] if len(bid) > 0 else i,
                    "bidder": bid[2] if len(bid) > 2 else "",
                    "amount": bid[3] if len(bid) > 3 else 0,
                    "amount_usdc": (bid[3] / 10**6) if len(bid) > 3 else 0,
                    "estimated_time": bid[4] if len(bid) > 4 else 0,
                })
            
            return json.dumps({
                "success": True,
                "job_id": job_id,
                "bid_count": len(parsed_bids),
                "bids": parsed_bids
            }, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


class PlaceBidTool(BaseTool):
    """Tool to place a bid on a job"""
    
    name: str = "place_bid"
    description: str = """
    Place a bid on an open job. This submits a transaction to the blockchain.
    
    The bid includes:
    - Amount: How much USDC you're willing to accept
    - Estimated Time: How long you expect the job to take (in seconds)
    - Metadata: Optional URI with additional proposal information
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "integer",
                "description": "The job ID to bid on"
            },
            "amount_usdc": {
                "type": "number",
                "description": "Bid amount in USDC (e.g., 10.50)"
            },
            "estimated_hours": {
                "type": "number",
                "description": "Estimated completion time in hours"
            },
            "proposal_notes": {
                "type": "string",
                "description": "Optional notes about your proposal"
            }
        },
        "required": ["job_id", "amount_usdc", "estimated_hours"]
    }
    
    _contracts: Optional[ContractInstances] = None
    _agent_type: str = "agent"
    
    def set_contracts(self, contracts: ContractInstances):
        self._contracts = contracts
    
    def set_agent_type(self, agent_type: str):
        self._agent_type = agent_type
    
    async def execute(
        self,
        job_id: int,
        amount_usdc: float,
        estimated_hours: float,
        proposal_notes: str = ""
    ) -> str:
        if not self._contracts:
            return json.dumps({"error": "Contracts not configured"})

        try:
            # Convert to contract units
            amount_raw = int(amount_usdc * 10**6)  # 6 decimals (USDC)
            estimated_seconds = int(estimated_hours * 3600)
            
            # Create metadata URI (could be IPFS in production)
            metadata_uri = f"archive://{self._agent_type}/bid/{job_id}"
            if proposal_notes:
                metadata_uri += f"?notes={proposal_notes[:100]}"
            
            bid_id = place_bid(
                self._contracts,
                job_id,
                amount_raw,
                estimated_seconds,
                metadata_uri
            )
            
            return json.dumps({
                "success": True,
                "job_id": job_id,
                "bid_id": bid_id,
                "amount_usdc": amount_usdc,
                "estimated_hours": estimated_hours,
                "metadata_uri": metadata_uri
            }, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


class SubmitDeliveryTool(BaseTool):
    """Tool to submit job delivery proof"""
    
    name: str = "submit_delivery"
    description: str = """
    Submit proof of job completion to the OrderBook contract.
    
    The proof hash should be a hash of the delivery content (e.g., storage URI).
    After submission, the client can approve and release payment.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "integer",
                "description": "The job ID to submit delivery for"
            },
            "proof_hash": {
                "type": "string",
                "description": "Hash of the delivery proof (hex string)"
            }
        },
        "required": ["job_id", "proof_hash"]
    }
    
    _contracts: Optional[ContractInstances] = None
    
    def set_contracts(self, contracts: ContractInstances):
        self._contracts = contracts
    
    async def execute(self, job_id: int, proof_hash: str) -> str:
        if not self._contracts:
            return json.dumps({"error": "Contracts not configured"})
        
        try:
            # Convert hex string to bytes
            if proof_hash.startswith("0x"):
                proof_hash = proof_hash[2:]
            proof_bytes = bytes.fromhex(proof_hash)
            
            tx_hash = submit_delivery(self._contracts, job_id, proof_bytes)
            
            return json.dumps({
                "success": True,
                "job_id": job_id,
                "tx_hash": tx_hash,
                "proof_hash": proof_hash
            }, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


def create_bidding_tools(
    contracts: Optional[ContractInstances] = None,
    agent_type: str = "agent"
) -> list[BaseTool]:
    """
    Create all bidding tools with optional contract injection.
    
    Args:
        contracts: ContractInstances to inject
        agent_type: Type of agent for metadata
    
    Returns:
        List of bidding tools
    """
    get_job_tool = GetJobDetailsTool()
    list_bids_tool = ListJobBidsTool()
    place_bid_tool = PlaceBidTool()
    submit_delivery_tool = SubmitDeliveryTool()
    
    if contracts:
        get_job_tool.set_contracts(contracts)
        list_bids_tool.set_contracts(contracts)
        place_bid_tool.set_contracts(contracts)
        submit_delivery_tool.set_contracts(contracts)
    
    place_bid_tool.set_agent_type(agent_type)
    
    return [
        get_job_tool,
        list_bids_tool,
        place_bid_tool,
        submit_delivery_tool,
    ]
