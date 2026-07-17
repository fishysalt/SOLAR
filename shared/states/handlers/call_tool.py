"""call_tool 状态处理函数"""

from typing import Optional, Dict, Any
from creator.utils import log_with_timestamp as log


async def handle_call_tool(agent, task, data: Dict) -> Optional[Dict[str, Any]]:
    """处理 call_tool 状态 - 调用工具"""
    tool_name = data.get("tool_name")
    tool_args = data.get("args", {})

    if not tool_name:
        log(agent.name, "WARNING", "call_tool 缺少 tool_name")
        return None

    task.isolated_memory.append({
        "role": "assistant",
        "content": f"[决策] 调用工具: {tool_name}"
    })

    agent._emit_process(f"🔧 调用工具: {tool_name}", "🔧")

    try:
        result, elapsed = await agent.tools.execute(tool_name, **tool_args)
        result_str = str(result)
        if len(result_str) > 2000:
            result_str = result_str[:2000] + "... (截断)"
        task.isolated_memory.append({
            "role": "tool",
            "content": result_str,
            "tool_name": tool_name,
            "elapsed": elapsed
        })
        log(agent.name, "INFO", f"工具 {tool_name} 执行耗时: {elapsed:.2f}s")
        return None
    except Exception as e:
        task.isolated_memory.append({
            "role": "tool",
            "content": f"工具执行失败: {str(e)}"
        })
        log(agent.name, "ERROR", f"工具调用失败: {e}", error=True)
        from .fail import handle_fail
        return await handle_fail(agent, task, {"error": f"工具执行失败: {str(e)}"})