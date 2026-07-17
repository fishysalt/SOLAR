"""RAG 工作经验数据模型"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class RAGExperience:
    """工作经验"""
    task_id: str
    user_id: str
    instruction: str
    summary: str
    state_path: str
    key_steps: str
    result_preview: str
    success: bool = True
    time_cost: int = 0
    created_at: Optional[datetime] = None
    category: str = "general"  # ← 新增

@dataclass
class RAGCategory:
    """RAG 分类"""
    table_name: str
    agent_name: str
    category: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None