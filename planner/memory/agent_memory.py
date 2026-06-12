"""Creator 记忆管理器"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conductor.core.memory.agent_memory import AgentMemory


class CreatorMemory(AgentMemory):
    """Creator 专用记忆管理器"""
    
    def __init__(self, agent_name: str = "creator"):
        # 使用 creator 专用路径
        memory_dir = Path(__file__).parent
        super().__init__(agent_name, memory_dir)