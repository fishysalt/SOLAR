"""记忆操作内置工具"""

from ..models import ToolInfo, ToolType


def view_memory_sync() -> str:
    """查看记忆（占位）"""
    return "记忆内容待实现"


def add_memory_sync(content: str) -> str:
    """添加记忆（占位）"""
    return f"已添加记忆: {content[:50]}..."


def search_memory_sync(keyword: str) -> str:
    """搜索记忆（占位）"""
    return f"搜索 '{keyword}' 的结果待实现"


# ========== 工具定义 ==========

VIEW_MEMORY_TOOL = ToolInfo(
    name="view_my_memory",
    description="查看当前短期记忆内容",
    parameters={"type": "object", "properties": {}, "required": []},
    tool_type=ToolType.BUILTIN,
    estimated_wait_time=0.05,
    func=view_memory_sync,
    is_async=False
)

ADD_MEMORY_TOOL = ToolInfo(
    name="add_to_my_memory",
    description="添加信息到记忆",
    parameters={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "要记忆的内容"}
        },
        "required": ["content"]
    },
    tool_type=ToolType.BUILTIN,
    estimated_wait_time=0.05,
    func=add_memory_sync,
    is_async=False
)

SEARCH_MEMORY_TOOL = ToolInfo(
    name="search_my_memory",
    description="搜索记忆",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["keyword"]
    },
    tool_type=ToolType.BUILTIN,
    estimated_wait_time=0.05,
    func=search_memory_sync,
    is_async=False
)