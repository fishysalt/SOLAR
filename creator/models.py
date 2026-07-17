"""Creator Agent 数据模型 - 任务相关"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


class TaskStatus(str, Enum):
    """主任务状态"""
    CREATED = "created"
    RECEIVED = "received"
    RUNNING = "running"
    WAITING = "waiting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubtaskStatus(str, Enum):
    """子任务状态（工具调用）"""
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubTask:
    """子任务 - 工具调用"""
    id: str
    tool_name: str
    instruction: str
    status: SubtaskStatus = SubtaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "instruction": self.instruction[:100],
            "status": self.status.value,
            "result": str(self.result)[:200] if self.result else None,
            "error": self.error[:200] if self.error else None,
        }


@dataclass
class Task:
    """主任务 - 所有信息存储在 isolated_memory 中"""
    task_id: str
    user_id: str
    instruction: str
    status: TaskStatus = TaskStatus.CREATED
    level: int = 1
    subtasks: List[SubTask] = field(default_factory=list)
    final_result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # ReAct 状态
    iteration_count: int = 0
    max_iterations: int = 20
    state_path: List[str] = field(default_factory=list)

    # ========== 任务独立记忆（唯一信息存储） ==========
    isolated_memory: List[Dict[str, str]] = field(default_factory=list)

    # ========== 回调信息 ==========
    subtask_id: str = ""
    callback_url: Optional[str] = None

    # ========== 等待确认 ==========
    pending_reply: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "instruction": self.instruction[:100],
            "status": self.status.value,
            "level": self.level,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "final_result": self.final_result[:500] if self.final_result else None,
            "error": self.error[:200] if self.error else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress": self._calculate_progress(),
            "iteration": self.iteration_count,
            "state_path": "→".join(self.state_path) if self.state_path else "",
            "isolated_memory_count": len(self.isolated_memory)
        }

    def _calculate_progress(self) -> int:
        if not self.subtasks:
            return 0
        completed = sum(1 for st in self.subtasks if st.status == SubtaskStatus.COMPLETED)
        return int(completed / len(self.subtasks) * 100)

    def is_all_completed(self) -> bool:
        if not self.subtasks:
            return False
        return all(st.status == SubtaskStatus.COMPLETED for st in self.subtasks)

    def has_failed(self) -> bool:
        return any(st.status == SubtaskStatus.FAILED for st in self.subtasks)


@dataclass
class CancelRequest:
    """取消任务请求"""
    task_id: str
    reason: str = "user_cancelled"