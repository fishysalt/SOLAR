"""工具数据模型 - 与数据库表字段对齐"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any, List
from enum import Enum


class ToolType(str, Enum):
    """工具类型"""
    BUILTIN = "builtin"
    MCP = "mcp"


@dataclass
class ToolInfo:
    """工具完整信息 - 对应数据库表字段（内置和MCP）"""
    name: str
    description: str
    func: Callable
    parameters: dict
    tool_type: ToolType = ToolType.BUILTIN

    # ===== 动态统计字段 =====
    estimated_wait_time: float = 0.0      # 加权平均等待时间（秒）
    last_execution_time: float = 0.0      # 最近一次实际耗时
    execution_count: int = 0              # 总调用次数（无论成败）
    success_count: int = 0                # 成功调用次数
    success_rate: float = 0.0             # 成功率 success_count / execution_count

    # ===== 控制字段 =====
    is_async: bool = False                # 是否异步函数
    is_available: bool = True             # 是否可用
    timeout: int = 240                    # 超时时间（秒）

    # ===== 扩展字段 =====
    last_error: Optional[str] = None      # 最近一次错误信息
    extra_metadata: Optional[Dict[str, Any]] = None  # 扩展 JSON 元数据

    def to_schema(self) -> dict:
        """转换为 OpenAI 函数格式"""
        # 确保 parameters 是有效的 JSON Schema
        params = self.parameters or {}
        if not isinstance(params, dict):
            params = {}
        # 如果缺少 type 或 type 不是 object，强制修正
        if params.get("type") != "object":
            # 保留原有 properties，外层包装为 object
            params = {
                "type": "object",
                "properties": params.get("properties", {}),
                "required": params.get("required", [])
            }
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params
            }
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（便于序列化或日志）"""
        return {
            "name": self.name,
            "description": self.description,
            "tool_type": self.tool_type.value,
            "estimated_wait_time": self.estimated_wait_time,
            "last_execution_time": self.last_execution_time,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "is_async": self.is_async,
            "is_available": self.is_available,
            "timeout": self.timeout,
            "last_error": self.last_error,
            "extra_metadata": self.extra_metadata,
        }


@dataclass
class ToolExecutionResult:
    """工具执行结果（返回给调用方）"""
    tool_name: str
    result: Any
    elapsed_time: float
    estimated_wait_time: float
    is_async: bool = False

    def to_str(self) -> str:
        """转换为字符串（供LLM阅读）"""
        return str(self.result)