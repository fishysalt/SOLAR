"""MCP Server 管理器 - 管理多个 MCP Server 连接"""

import json
import threading
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

from .client import MCPClient, MCPTool


class MCPServerManager:
    """
    MCP Server 管理器
    负责管理多个 MCP Server 的连接、工具发现和生命周期
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self._clients: Dict[str, MCPClient] = {}
        self._all_tools: List[MCPTool] = []
        self._config_path = Path(__file__).parent / "config.json"
        self._lock = threading.Lock()
        
        print("🔌 MCP Server 管理器已初始化")
    
    def _load_env_file(self):
        """加载 creator 目录下的 .env 文件"""
        # 获取 creator 根目录
        current_dir = Path(__file__).parent  # creator/tools/mcp
        creator_root = current_dir.parent.parent  # creator/
        env_path = creator_root / ".env"
        
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            print(f"   📝 已加载环境变量: {env_path}")
            # 验证 API Key 是否加载成功
            api_key = os.environ.get("DASHSCOPE_API_KEY")
            if api_key:
                print(f"   🔑 DASHSCOPE_API_KEY 已加载 (长度: {len(api_key)})")
            else:
                print(f"   ⚠️ DASHSCOPE_API_KEY 未找到")
        else:
            print(f"   ⚠️ 未找到 .env 文件: {env_path}")
    
    def load_config(self, config_path: Path = None) -> bool:
        """
        加载配置文件并启动所有配置的 MCP Server
        """
        # 先加载环境变量
        self._load_env_file()
        
        if config_path is None:
            config_path = self._config_path

        if not config_path.exists():
            print(f"   ⚠️ MCP 配置文件不存在: {config_path}")
            self._create_default_config()
            return False

        try:
            from .http_client import HTTPMCPClient

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            servers = config.get("servers", [])

            for server_config in servers:
                if not server_config.get("enabled", True):
                    print(f"   ⏭️ 跳过未启用的 Server: {server_config.get('name')}")
                    continue

                server_type = server_config.get("type", "stdio")

                if server_type == "http":
                    # HTTP 类型 MCP Server
                    name = server_config["name"]
                    base_url = server_config["baseUrl"]
                    headers = server_config.get("headers", {})

                    # 替换环境变量
                    # 替换环境变量（支持 Bearer ${VAR} 格式）
                    for key, value in headers.items():
                        if isinstance(value, str) and "${" in value:
                            import re
                        def replace_env(match):
                            env_var = match.group(1)
                            return os.environ.get(env_var, "")
                        headers[key] = re.sub(r'\${([^}]+)}', replace_env, value)
                        print(f"   🔑 已设置 {key}: {headers[key][:30]}...")
                    
                    print(f"   🌐 连接 MCP HTTP Server: {name}")
                    client = HTTPMCPClient(name, base_url, headers)
                    success = client.initialize()

                    if success:
                        with self._lock:
                            self._clients[name] = client
                            for tool in client.tools:
                                self._all_tools.append(tool)
                        print(f"   ✅ MCP HTTP Server 已连接: {name} ({len(client.tools)} 个工具)")
                        # 打印工具列表
                        for tool in client.tools:
                            desc = tool.description[:50] + "..." if len(tool.description) > 50 else tool.description
                            print(f"      - {tool.name}: {desc}")
                    else:
                        print(f"   ❌ MCP HTTP Server 连接失败: {name}")

                else:
                    # stdio 类型（原有逻辑）
                    self.add_server(
                        name=server_config["name"],
                        command=server_config["command"],
                        args=server_config.get("args", []),
                        env=server_config.get("env", {})
                    )

            return True

        except Exception as e:
            print(f"   ❌ 加载 MCP 配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_default_config(self):
        """创建默认配置文件"""
        default_config = {
            "servers": [
                {
                    "name": "example",
                    "command": "echo",
                    "args": ["'MCP server not configured'"],
                    "enabled": False,
                    "description": "示例配置，请根据实际 MCP Server 修改"
                }
            ],
            "_comment": {
                "name": "MCP Server 名称，用于标识",
                "command": "启动命令（如 npx、python、node）",
                "args": "命令参数列表",
                "env": "环境变量（如 API_KEY）",
                "enabled": "是否启用（true/false）"
            }
        }
        
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        
        print(f"   📝 已创建默认 MCP 配置文件: {self._config_path}")
    
    def add_server(self, name: str, command: str, args: List[str] = None, env: Dict[str, str] = None) -> bool:
        """动态添加 MCP Server"""
        with self._lock:
            if name in self._clients:
                print(f"   ⚠️ MCP Server 已存在: {name}")
                return False
            
            client = MCPClient(name, command, args or [], env or {})
            
            success = client.start()
            if success:
                self._clients[name] = client
                for tool in client.tools:
                    self._all_tools.append(tool)
                print(f"   ✅ MCP Server 已添加: {name} ({len(client.tools)} 个工具)")
                return True
            else:
                print(f"   ❌ MCP Server 启动失败: {name}")
                return False
    
    def remove_server(self, name: str) -> bool:
        """移除 MCP Server"""
        with self._lock:
            if name not in self._clients:
                return False
            
            client = self._clients[name]
            client.stop()
            
            self._all_tools = [t for t in self._all_tools if t.server_name != name]
            del self._clients[name]
            
            print(f"   🛑 MCP Server 已移除: {name}")
            return True
    
    def get_all_tools(self) -> List[MCPTool]:
        """获取所有已发现的外部工具"""
        with self._lock:
            return self._all_tools.copy()
    
    def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """调用指定 Server 的工具"""
        with self._lock:
            client = self._clients.get(server_name)
            if not client:
                return f"❌ MCP Server 不存在: {server_name}"
            
            if not client.is_running():
                return f"❌ MCP Server 未运行: {server_name}"
        
        return client.call_tool(tool_name, arguments)
    
    def get_server_status(self) -> Dict[str, bool]:
        """获取所有 Server 的状态"""
        status = {}
        with self._lock:
            for name, client in self._clients.items():
                status[name] = client.is_running()
        return status
    
    def stop_all(self):
        """停止所有 MCP Server"""
        with self._lock:
            for name, client in self._clients.items():
                client.stop()
            self._clients.clear()
            self._all_tools.clear()
        
        print("🔌 所有 MCP Server 已停止")


# 全局单例
_manager = None

def get_mcp_manager() -> MCPServerManager:
    global _manager
    if _manager is None:
        _manager = MCPServerManager()
    return _manager