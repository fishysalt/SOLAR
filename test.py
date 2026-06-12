
from conductor.agent import get_conductor
import asyncio

c = get_conductor()

print("已配置的 Agent:", list(c.registry._config.keys()))
print("\nScavenger 配置:", c.registry._config.get("scavenger"))

async def test():
    return await c.registry.check_agent_status("scavenger")

result = asyncio.run(test())
print("\n检测结果:", result)