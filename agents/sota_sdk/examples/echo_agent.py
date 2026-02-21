"""
Simplest possible SOTA agent -- echoes the job description back.

Run:  python echo_agent.py
"""
from sota_sdk import SOTAAgent, Job


class EchoAgent(SOTAAgent):
    name = "echo"
    description = "Echoes job descriptions back (demo agent)"
    tags = ["echo", "test"]

    async def execute(self, job: Job) -> dict:
        return {"success": True, "echo": job.description}


if __name__ == "__main__":
    EchoAgent.run()
