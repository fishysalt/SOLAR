"""wait 状态处理函数"""

import asyncio
from typing import Optional, Dict, Any
from creator.utils import log_with_timestamp as log
from .common import TaskStatus


async def handle_wait(agent, task, data: Dict) -> Optional[Dict[str, Any]]:
    """处理 wait 状态 - 等待长时间工具完成"""
    tool_name = data.get("tool_name", "未知工具")
    wait_time = data.get("wait_time")
    if wait_time is None:
        wait_time = agent.tools.get_wait_time(tool_name) if agent.tools else 0.0
        if wait_time <= 0:
            wait_time = 40

    if wait_time > 0.5:
        agent._emit_process(f"⏳ 等待 {tool_name} 完成 (预估 {wait_time:.1f}s)", "⏳")
        agent._update_task_status(task.task_id, TaskStatus.WAITING)
        await asyncio.sleep(wait_time)
        agent._update_task_status(task.task_id, TaskStatus.RUNNING)
        agent._emit_process(f"✅ {tool_name} 等待完成", "✅")
        log(agent.name, "INFO", f"✅ 等待完成: {tool_name}")
    else:
        await asyncio.sleep(wait_time)

    return None