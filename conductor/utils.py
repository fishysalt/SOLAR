"""Conductor 辅助函数"""

from datetime import datetime
from typing import Optional
import uuid


def log_with_timestamp(
    agent_name: str, 
    level: str, 
    message: str, 
    error: bool = False
):
    """带时间戳的日志输出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "[ERROR] " if error else ""
    print(f"[{timestamp}] [{agent_name}] [{level}] {prefix}{message}")


def generate_msg_id(sender: str) -> str:
    """生成消息 ID"""
    return f"{sender}_{uuid.uuid4().hex[:8]}"


def extract_schedule_command(response: str) -> Optional[tuple]:
    """
    从 LLM 响应中提取调度命令
    返回 (agent_name, instruction) 或 None
    """
    lines = response.strip().split("\n")
    if not lines:
        return None
    
    first_line = lines[0]
    if first_line.startswith("SCHEDULE:"):
        agent_name = first_line.replace("SCHEDULE:", "").strip()
        instruction = "\n".join(lines[1:]).strip()
        return (agent_name, instruction)
    
    return None