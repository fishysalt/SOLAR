"""Conductor 工具模块"""

from .registry import ToolRegistry, get_tool_registry, extract_rank_from_name
from .categories import ToolCategory, get_category_description


def get_conductor_tools() -> list:
    """获取 Conductor 的所有工具"""
    # 延迟导入，避免循环依赖
    from .builtin import CONDUCTOR_BUILTIN_TOOLS
    return CONDUCTOR_BUILTIN_TOOLS


def init_conductor_tools():
    """初始化并注册 Conductor 的工具"""
    registry = get_tool_registry()
    tools = get_conductor_tools()
    if tools:
        registry.register_multiple(tools)
        print(f"✅ Conductor 工具已注册，共 {len(registry.list_tools())} 个")
    else:
        print(f"ℹ️ Conductor 暂无工具需要注册")
    return registry


# 导出主要接口
__all__ = [
    "ToolRegistry",
    "get_tool_registry",
    "extract_rank_from_name",
    "ToolCategory",
    "get_category_description",
    "get_conductor_tools",
    "init_conductor_tools"
]