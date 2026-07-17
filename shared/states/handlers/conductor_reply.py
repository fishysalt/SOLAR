"""Conductor 专用的 reply 状态处理函数 - 回复用户并等待确认"""

from typing import Dict, Any
from conductor.utils import log_with_timestamp  # 导入 conductor 的日志函数
from .common import TaskStatus


async def handle_conductor_reply(agent, task, data: Dict) -> None:
    content = data.get("content")

    if not content:
        log_with_timestamp(agent.name, "WARNING", "data.content 为空，尝试从记忆中提取")
        for msg in reversed(task.isolated_memory):
            role = msg.get("role", "")
            if role not in ["system"]:
                content = msg.get("content", "")
                if content:
                    break
        if not content:
            content = "任务已处理完成，请确认是否结束？"
            log_with_timestamp(agent.name, "WARNING", "使用默认回复内容")

    task.isolated_memory.append({
        "role": "assistant",
        "content": content
    })

    task.final_result = content
    task.level = 2
    agent._update_task_status(task.task_id, TaskStatus.AWAITING_CONFIRMATION)

    agent._emit_process(f"💬 回复: {content[:50]}...", "💬")
    agent._emit_process("⏳ 等待用户确认...", "⏳")
    log_with_timestamp(agent.name, "INFO", f"💬 等待确认")

    return None