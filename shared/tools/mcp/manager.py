"""MCP工具管理器 - 统一管理所有MCP Server"""

import json
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List

from ..registry import get_tool_registry, ToolInfo
from ..models import ToolType


class MCPManager:
    """MCP Server管理器"""
    
    def __init__(self, config_dir: Path = None):
        self.config_dir = config_dir or Path(__file__).parent / "configs"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._servers: Dict[str, Dict] = {}
        self._agent_server_map: Dict[str, List[str]] = {}
    
    def load_server_config(self, server_name: str) -> Optional[Dict]:
        """加载MCP Server配置"""
        config_path = self.config_dir / f"{server_name}.yaml"
        if not config_path.exists():
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def register_mcp_tools(self, agent_name: str, server_name: str, tools: List[Dict]):
        """注册MCP工具到指定Agent"""
        registry = get_tool_registry()
        
        for tool_def in tools:
            # 创建包装函数
            def make_wrapper(server_name, tool_name):
                async def wrapper(**kwargs):
                    # TODO: 实际调用MCP HTTP接口
                    return f"MCP {server_name}:{tool_name} 执行中..."
                return wrapper
            
            tool_info = ToolInfo(
                name=f"mcp_{server_name}_{tool_def['name']}",
                description=tool_def.get("description", ""),
                parameters=tool_def.get("parameters", {}),
                tool_type=ToolType.MCP,
                estimated_wait_time=10.0,
                func=make_wrapper(server_name, tool_def['name']),
                is_async=True
            )
            
            registry.register(agent_name, tool_info)
        
        if agent_name not in self._agent_server_map:
            self._agent_server_map[agent_name] = []
        self._agent_server_map[agent_name].append(server_name)
    
    def get_server_tools(self, server_name: str) -> List[Dict]:
        """获取Server的工具列表"""
        config = self.load_server_config(server_name)
        if config:
            return config.get("tools", [])
        return []


# ========== 全局单例 ==========

_mcp_manager = None

def get_mcp_manager(config_dir: Path = None) -> MCPManager:
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager(config_dir)
    return _mcp_manager