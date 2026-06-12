"""Scavenger Agent 消息总线 - 连接主总线"""

import sys
from pathlib import Path

# 从主总线导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conductor.core.message_bus import get_message_bus, Message, MessageBus

__all__ = ["get_message_bus", "Message", "MessageBus"]