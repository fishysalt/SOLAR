"""MCP 工具模块 - 引入外部 MCP Server 工具"""

from .client import MCPClient, MCPTool
from .http_client import HTTPMCPClient
from .manager import MCPServerManager, get_mcp_manager


def init_mcp_tools():
    """
    初始化所有 MCP 工具
    在 Creator Agent 启动时调用
    """
    print("\n🔌 正在初始化 MCP 工具...")
    print("=" * 40)
    
    manager = get_mcp_manager()
    
    # 加载配置文件（会自动连接 HTTP MCP Server）
    config_loaded = manager.load_config()
    
    if config_loaded:
        status = manager.get_server_status()
        if status:
            print(f"\n📊 MCP Server 状态:")
            for name, running in status.items():
                icon = "✅" if running else "❌"
                print(f"   {icon} {name}: {'运行中' if running else '已停止'}")
        else:
            print("\n📭 当前没有运行的 MCP Server")
            print("   请配置 creator/tools/mcp/config.json 添加 MCP Server")
    else:
        print("\n⚠️ MCP 配置加载失败")
    
    print("=" * 40)
    
    return manager


def get_mcp_tools():
    """获取所有 MCP 工具（供注册用）"""
    manager = get_mcp_manager()
    return manager.get_all_tools()


__all__ = [
    "MCPClient",
    "HTTPMCPClient",
    "MCPTool",
    "MCPServerManager",
    "get_mcp_manager",
    "init_mcp_tools",
    "get_mcp_tools",
]