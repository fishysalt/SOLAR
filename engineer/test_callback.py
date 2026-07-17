# test_callback.py
import asyncio
import aiohttp
import json

async def test_full_flow():
    async with aiohttp.ClientSession() as session:
        print("📤 1. 用户发送消息...")
        async with session.post(
            "http://localhost:7860/api/chat",
            json={"user_id": "alice", "message": "帮我生成一个测试文件"}
        ) as resp:
            text = await resp.text()
            print(f"   状态码: {resp.status}")
            print(f"   响应: {text}")
            if resp.status == 200:
                result = json.loads(text)
                task_id = result.get("task_id")
                print(f"   task_id: {task_id}")
            else:
                print("   ❌ 请求失败")

if __name__ == "__main__":
    asyncio.run(test_full_flow())