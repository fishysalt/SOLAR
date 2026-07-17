"""fail 状态处理函数"""

from typing import Dict, Any
from datetime import datetime
from creator.utils import log_with_timestamp as log


async def handle_fail(agent, task, data: Dict) -> Dict[str, Any]:
    """处理 fail 状态 - 任务失败，汇报错误"""
    error = data.get("error", "未知错误")

    task.isolated_memory.append({
        "role": "assistant",
        "content": f"[失败] {error}"
    })

    task.error = error
    task.completed_at = datetime.now()

    log(agent.name, "WARNING", f"❌ 任务失败: {error}")

    return await agent._finalize_task(task, success=False, error=error)