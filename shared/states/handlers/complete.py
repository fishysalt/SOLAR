"""complete 状态处理函数 - 任务完成并保存"""

from typing import Dict, Any
from datetime import datetime
from .common import TaskStatus


async def handle_complete(agent, task, data: Dict) -> Dict[str, Any]:
    agent._update_task_status(task.task_id, TaskStatus.COMPLETED)
    task.completed_at = datetime.now()

    await agent._save_task_memory(task)
    await agent._save_rag_experience(task)

    agent.store.delete_task_memory(task.task_id)

    agent._emit_process(f"✅ 任务完成并保存", "✅")
    agent.log(agent.name, "INFO", f"✅ 任务完成: {task.task_id}")

    return {
        "status": "success",
        "message": task.final_result or "任务已完成",
        "task_id": task.task_id
    }