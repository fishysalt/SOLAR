"""reply 状态处理函数"""

from typing import Dict, Any
from datetime import datetime
from creator.utils import log_with_timestamp as log


async def handle_reply(agent, task, data: Dict) -> Dict[str, Any]:
    """处理 reply 状态 - 任务完成，返回结果"""
    content = data.get("content")

    log(agent.name, "INFO", f"📝 reply 收到: {content[:50] if content else 'None'}")

    if not content:
        log(agent.name, "WARNING", "data.content 为空，尝试从记忆中提取")
        for msg in reversed(task.isolated_memory):
            role = msg.get("role", "")
            if role not in ["system"]:
                content = msg.get("content", "")
                if content:
                    log(agent.name, "INFO", f"从记忆中提取到: {content[:50]}...")
                    break
        if not content:
            content = "任务已完成"
            log(agent.name, "WARNING", "使用默认内容")

    task.isolated_memory.append({
        "role": "assistant",
        "content": content
    })

    task.final_result = content
    task.completed_at = datetime.now()

    return await agent._finalize_task(task, success=True, message=content)