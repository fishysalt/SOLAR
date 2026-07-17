"""内置工具：创建新的MCP工具配置（写入 mcp_agent_tools 表）"""

import json
import pymysql
from typing import Optional, Dict, Any


def create_mcp_tool(
    agent_name: str,
    tool_name: str,
    server_name: str,
    server_type: str,          # 'stdio' 或 'http'
    command: Optional[str] = None,
    args: Optional[list] = None,
    base_url: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    description: Optional[str] = None,
    parameters: Optional[Dict] = None,
    timeout: int = 240,
    extra_metadata: Optional[Dict] = None
) -> str:
    """
    创建（或更新）一个MCP工具配置，直接写入 mcp_agent_tools 表。
    
    参数直接对应表字段，唯一键为 (agent_name, tool_name)。
    如果已存在则更新，否则插入。
    
    返回执行结果信息。
    """
    # 从全局配置获取MySQL连接信息（共享同一个配置）
    from ..registry import get_tool_registry
    registry = get_tool_registry()
    # 确保registry已初始化mysql
    # 假设已调用 init_mysql
    
    try:
        conn = registry._get_mysql_connection()
        cursor = conn.cursor()
        
        # 检查是否存在
        cursor.execute(
            "SELECT id FROM mcp_agent_tools WHERE agent_name = %s AND tool_name = %s",
            (agent_name, tool_name)
        )
        exists = cursor.fetchone()
        
        if exists:
            # 更新
            cursor.execute("""
                UPDATE mcp_agent_tools
                SET server_name = %s, server_type = %s, command = %s, args = %s,
                    base_url = %s, headers = %s, description = %s, parameters = %s,
                    timeout = %s, extra_metadata = %s, updated_at = NOW()
                WHERE agent_name = %s AND tool_name = %s
            """, (
                server_name, server_type, command, json.dumps(args) if args else None,
                base_url, json.dumps(headers) if headers else None,
                description, json.dumps(parameters) if parameters else None,
                timeout, json.dumps(extra_metadata) if extra_metadata else None,
                agent_name, tool_name
            ))
            result = f"✅ MCP工具 '{tool_name}' 已更新"
        else:
            # 插入
            cursor.execute("""
                INSERT INTO mcp_agent_tools
                (agent_name, tool_name, server_name, server_type, command, args,
                 base_url, headers, description, parameters, timeout, extra_metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                agent_name, tool_name, server_name, server_type, command, json.dumps(args) if args else None,
                base_url, json.dumps(headers) if headers else None,
                description, json.dumps(parameters) if parameters else None,
                timeout, json.dumps(extra_metadata) if extra_metadata else None
            ))
            result = f"✅ MCP工具 '{tool_name}' 已创建"
        
        conn.commit()
        cursor.close()
        conn.close()
        return result
    except Exception as e:
        return f"❌ 创建MCP工具失败: {str(e)}"


# 工具定义（字典格式）
CREATE_MCP_TOOL = {
    "name": "create_mcp_tool",
    "description": "创建或更新MCP工具配置，该配置将写入数据库，使得Agent能动态加载此工具。",
    "func": create_mcp_tool,
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string", "description": "该工具归属于哪个Agent，如 'creator'"},
            "tool_name": {"type": "string", "description": "工具唯一名称，如 'web_search'"},
            "server_name": {"type": "string", "description": "MCP Server名称，用于分组标识"},
            "server_type": {"type": "string", "enum": ["stdio", "http"], "description": "连接类型"},
            "command": {"type": "string", "description": "stdio类型时必填，启动命令"},
            "args": {"type": "array", "items": {"type": "string"}, "description": "stdio类型时可选，命令参数"},
            "base_url": {"type": "string", "description": "http类型时必填，完整服务URL"},
            "headers": {"type": "object", "description": "http类型时可选，请求头（支持${ENV_VAR}占位符）"},
            "description": {"type": "string", "description": "工具功能描述"},
            "parameters": {"type": "object", "description": "工具参数的JSON Schema"},
            "timeout": {"type": "integer", "description": "超时时间（秒），默认240"},
            "extra_metadata": {"type": "object", "description": "扩展JSON字段，存储自定义属性"}
        },
        "required": ["agent_name", "tool_name", "server_name", "server_type"]
    }
}