"""call_agent 状态处理函数 - 调用子Agent"""

from typing import Dict, Any


async def handle_call_agent(agent, task, data: Dict) -> None:
    agent_name = data.get("agent_name")
    instruction = data.get("instruction")

    if not agent_name or not instruction:
        agent.log(agent.name, "WARNING", "call_agent 缺少参数")
        return

    task.isolated_memory.append({
        "role": "assistant",
        "content": f"[决策] 调用 {agent_name}: {instruction}"
    })

    agent._emit_process(f"📤 调用 {agent_name}", "📤")

    # 直接导入 http_client 并调用
    from conductor.http_client import get_http_client
    client = get_http_client()
    result = await client.send_task(agent_name, instruction)

    task.isolated_memory.append({
        "role": agent_name,
        "content": result.get("message", result.get("error", "执行完成"))
    })

    if result.get("status") == "error":
        agent.log(agent.name, "WARNING", f"子Agent调用失败: {result.get('error')}")