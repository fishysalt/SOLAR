"""状态数据模型"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any, List


@dataclass
class StateInfo:
    """状态信息 - 对应数据库 agent_states 表"""
    state_id: str
    description: str
    handler: Callable  # async def handler(task, data) -> Optional[Dict]
    estimated_duration: float = 0.0
    permission_level: int = 1
    execution_count: int = 0
    is_final: bool = False
    is_available: bool = True
    extra_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_prompt_line(self) -> str:
        """生成状态描述行，用于 LLM 提示词"""
        return f"- {self.state_id}: {self.description}"