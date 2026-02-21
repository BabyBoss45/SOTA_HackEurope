"""
Agent with custom tools -- demonstrates BaseTool and ToolManager.

Shows how to define tools that your agent can use during job execution.

Run:  python tool_agent.py
"""
import json

from sota_sdk import SOTAAgent, Job, BaseTool, ToolManager


class WeatherTool(BaseTool):
    name: str = "get_weather"
    description: str = "Get current weather for a city"
    parameters: dict = {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name"},
        },
        "required": ["city"],
    }

    async def execute(self, city: str = "", **kwargs) -> str:
        # Replace with a real weather API call
        return json.dumps({"city": city, "temp_c": 22, "condition": "sunny"})


class ToolAgent(SOTAAgent):
    name = "weather-agent"
    description = "Provides weather information"
    tags = ["weather", "data_analysis"]

    def setup(self):
        self.tools = ToolManager([WeatherTool()])

    async def execute(self, job: Job) -> dict:
        city = job.params.get("city", "London")
        raw = await self.tools.call("get_weather", {"city": city})
        weather = json.loads(raw)
        return {"success": True, "weather": weather}


if __name__ == "__main__":
    ToolAgent.run()
