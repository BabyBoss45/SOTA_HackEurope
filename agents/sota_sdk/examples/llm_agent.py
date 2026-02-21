"""
LLM-powered agent using Anthropic Claude.

Demonstrates setup() for client init and async execute().

Requires:  pip install anthropic
Env:       ANTHROPIC_API_KEY=sk-ant-...

Run:  python llm_agent.py
"""
from sota_sdk import SOTAAgent, Job


class LLMAgent(SOTAAgent):
    name = "llm-analyst"
    description = "Answers questions using Claude"
    tags = ["data_analysis", "question_answering"]

    async def setup(self):
        import anthropic

        self.client = anthropic.AsyncAnthropic()

        # Optional: wrap with Paid.ai cost tracking
        try:
            from sota_sdk import cost

            self.client = cost.wrap_anthropic(self.client)
        except Exception:
            pass

    async def execute(self, job: Job) -> dict:
        response = await self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": job.description}],
        )
        return {"success": True, "answer": response.content[0].text}


if __name__ == "__main__":
    LLMAgent.run()
