"""状态管理系统 - 独立于工具模块"""

from .models import StateInfo
from .registry import StateRegistry, get_state_registry

__all__ = [
    "StateInfo",
    "StateRegistry",
    "get_state_registry",
]