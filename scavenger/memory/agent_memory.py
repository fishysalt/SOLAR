"""Scavenger 记忆管理"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conductor.core.memory.agent_memory import AgentMemory


class ScavengerMemory(AgentMemory):
    """Scavenger 专用记忆管理"""
    
    def __init__(self, agent_name: str = "Scavenger"):
        # 使用 Scavenger 专用路径
        memory_dir = Path(__file__).parent
        super().__init__(agent_name, memory_dir)