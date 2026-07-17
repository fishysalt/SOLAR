"""Conductor 任务数据模型"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


class TaskStatus(str, Enum):
    """任务状态"""
    CREATED = "created"          # 已创建，等待规划
    PLANNING = "planning"        # 规划中（LLM拆解）
    RUNNING = "running"          # 执行中（子任务进行中）
    WAITING = "waiting"          # 等待子Agent回调
    COMPLETED = "completed"      # 已完成
    CANCELLED = "cancelled"      # 已取消
    FAILED = "failed"            # 失败


class SubtaskStatus(str, Enum):
    """子任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubTask:
    """子任务"""
    id: str                          # subtask_001
    agent_name: str                  # creator / scavenger / engineer
    instruction: str                 # 具体指令
    status: SubtaskStatus = SubtaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    output_files: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "instruction": self.instruction[:100],
            "status": self.status.value,
            "result": self.result[:200] if self.result else None,
            "error": self.error[:200] if self.error else None,
            "output_files": self.output_files,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


@dataclass
class Task:
    """主任务"""
    def __init__(self, task_id: str, user_id: str, instruction: str):
        self.task_id = task_id
        self.user_id = user_id
        self.instruction = instruction
        self.status = TaskStatus.CREATED
        self.subtasks: List[SubTask] = []
        self.final_result = None
        self.error = None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.completed_at = None
        
        # ReAct 状态
        self.iteration_count = 0
        self.max_iterations = 20
        self.reasoning_history: List[Dict[str, Any]] = []
        
        # 子任务索引
        self._current_subtask_id = None
        
        # ========== 任务独立记忆（新增） ==========
        self.isolated_memory: List[Dict[str, str]] = []
    
    def to_dict(self, include_full_instruction: bool = False) -> Dict[str, Any]:
        """供UI展示用"""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "instruction": self.instruction if include_full_instruction else self.instruction[:100],
            "status": self.status.value,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "current_subtask_index": self.current_subtask_index,
            "final_result": self.final_result[:500] if self.final_result else None,
            "error": self.error[:200] if self.error else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress": self._calculate_progress()
        }
    
    def _calculate_progress(self) -> int:
        """计算进度百分比"""
        if not self.subtasks:
            return 0
        completed = sum(1 for st in self.subtasks if st.status == SubtaskStatus.COMPLETED)
        return int(completed / len(self.subtasks) * 100)
    
    def get_pending_subtasks(self) -> List[SubTask]:
        """获取待执行的子任务"""
        return [st for st in self.subtasks if st.status == SubtaskStatus.PENDING]
    
    def get_running_subtasks(self) -> List[SubTask]:
        """获取正在执行的子任务"""
        return [st for st in self.subtasks if st.status == SubtaskStatus.RUNNING]
    
    def is_all_completed(self) -> bool:
        """检查是否所有子任务都已完成"""
        if not self.subtasks:
            return False
        return all(st.status == SubtaskStatus.COMPLETED for st in self.subtasks)
    
    def is_any_failed(self) -> bool:
        """检查是否有子任务失败"""
        return any(st.status == SubtaskStatus.FAILED for st in self.subtasks)