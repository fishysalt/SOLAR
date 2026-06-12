"""MCP 工具包装器 - 将 MCP 工具包装成本地工具格式"""

from typing import Dict, Any, Callable
from .manager import get_mcp_manager


def wrap_mcp_tool(server_name: str, tool_name: str, description: str = None, parameters: Dict = None) -> Callable:
    """
    将 MCP 工具包装成可调用的函数
    
    Args:
        server_name: MCP Server 名称
        tool_name: 工具名称
        description: 工具描述（可选，覆盖 MCP 提供的描述）
        parameters: 参数 schema（可选，覆盖 MCP 提供的 schema）
    
    Returns:
        包装后的函数
    """
    manager = get_mcp_manager()
    
    def wrapper(**kwargs) -> str:
        return manager.call_tool(server_name, tool_name, kwargs)
    
    return wrapper


def create_tool_registration_item(server_name: str, tool_name: str, description: str, parameters: Dict) -> Dict:
    """
    创建工具注册项
    
    Returns:
        符合工具注册器格式的字典
    """
    return {
        "name": f"mcp_{server_name}_{tool_name}",
        "description": f"[MCP:{server_name}] {description}",
        "func": wrap_mcp_tool(server_name, tool_name),
        "parameters": parameters
    }