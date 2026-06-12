"""Scavenger 辅助函数"""

from datetime import datetime


def log_with_timestamp(agent_name: str, level: str, message: str, error: bool = False):
    """带时间戳的日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "[ERROR] " if error else ""
    print(f"[{timestamp}] [{agent_name}] [{level}] {prefix}{message}")