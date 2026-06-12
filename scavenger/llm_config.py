"""Scavenger LLM 配置 - 从环境变量加载"""

import sys
from pathlib import Path

# 复用 conductor 的配置
sys.path.insert(0, str(Path(__file__).parent.parent))
from conductor.llm_config import get_llm_config, LLMConfig

__all__ = ["get_llm_config", "LLMConfig"]