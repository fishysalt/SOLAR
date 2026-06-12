"""Creator 工具模块"""

from .registry import ToolRegistry, get_tool_registry
from .builtin import CREATOR_BUILTIN_TOOLS
from .mcp import init_mcp_tools, get_mcp_tools


def _convert_mcp_schema_to_openai(schema: dict) -> dict:
    """
    将 MCP 的 input_schema 转换为 OpenAI 兼容的格式
    
    MCP 可能使用 "bool" 而 OpenAI 要求 "boolean"
    以及其他格式差异
    """
    if not schema:
        return {"type": "object", "properties": {}}
    
    def convert_type(t):
        if t == "bool":
            return "boolean"
        return t
    
    converted = schema.copy()
    
    if "type" in converted:
        converted["type"] = convert_type(converted["type"])
    
    if "properties" in converted:
        for prop_name, prop_schema in converted["properties"].items():
            if isinstance(prop_schema, dict):
                if "type" in prop_schema:
                    prop_schema["type"] = convert_type(prop_schema["type"])
                if "items" in prop_schema and isinstance(prop_schema["items"], dict):
                    if "type" in prop_schema["items"]:
                        prop_schema["items"]["type"] = convert_type(prop_schema["items"]["type"])
    
    return converted


def get_creator_tools() -> list:
    """获取 Creator 的所有内置工具"""
    return CREATOR_BUILTIN_TOOLS


def init_creator_tools():
    """
    初始化并注册 Creator 的所有工具
    
    包括：
    1. builtin 工具（记忆操作等本地工具）
    2. MCP 外部工具（从 MCP Server 动态发现）
    """
    registry = get_tool_registry()
    
    # 1. 注册内置工具
    builtin_tools = get_creator_tools()
    if builtin_tools:
        registry.register_multiple(builtin_tools)
        print(f"✅ Creator 内置工具已注册，共 {len(builtin_tools)} 个")
    
    # 2. 初始化 MCP 并注册外部工具
    print("\n🔌 正在连接 MCP Server...")
    mcp_manager = init_mcp_tools()
    mcp_tools = get_mcp_tools()
    
    # 将每个 MCP 工具包装成本地工具格式
    for mcp_tool in mcp_tools:
        # 转换 schema 为 OpenAI 兼容格式
        converted_schema = _convert_mcp_schema_to_openai(mcp_tool.input_schema)
        
        # 创建包装函数
        def make_wrapper(server_name: str, tool_name: str):
            def wrapper(**kwargs) -> str:
                return mcp_manager.call_tool(server_name, tool_name, kwargs)
            return wrapper
        
        wrapper_func = make_wrapper(mcp_tool.server_name, mcp_tool.name)
        
        # 注册到工具注册器
        registry.register(
            name=f"mcp_{mcp_tool.server_name}_{mcp_tool.name}",
            description=f"[MCP:{mcp_tool.server_name}] {mcp_tool.description}",
            func=wrapper_func,
            parameters=converted_schema
        )
    
    if mcp_tools:
        print(f"✅ MCP 外部工具已注册，共 {len(mcp_tools)} 个")
    
    return registry


__all__ = [
    "ToolRegistry",
    "get_tool_registry",
    "get_creator_tools",
    "init_creator_tools",
]