"""Agent 注册表 - 管理所有子 Agent 的连接信息"""

import asyncio
import aiohttp
from typing import Dict, Any, Optional, List
from datetime import datetime


class AgentRegistry:
    """子 Agent 注册表 - 单例"""
    
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
        
        # Agent 配置（静态配置）
        self._config = {
            "creator": {
                "name": "creator",
                "display_name": "✨ Creator",
                "api_port": 7861,
                "ui_port": 7961,
                "capabilities": ["video_generation", "model_generation", "web_search"],
                "description": "视频生成、3D建模、网页搜索"
            },
            "scavenger": {
                "name": "scavenger",
                "display_name": "🔍 Scavenger",
                "api_port": 7862,
                "ui_port": 7962,
                "capabilities": ["web_scraping", "data_extraction"],
                "description": "网络爬虫、数据提取"
            },            
        }
        
        # 运行时状态（缓存，但每次操作前会刷新）
        self._runtime_status: Dict[str, Dict] = {}
        
        self._session: Optional[aiohttp.ClientSession] = None
        
        print("📋 Agent 注册表已初始化")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    def get_agent_config(self, agent_name: str) -> Optional[Dict]:
        """获取 Agent 配置"""
        return self._config.get(agent_name)
    
    def get_all_agents(self) -> List[Dict]:
        """获取所有 Agent 配置"""
        return list(self._config.values())
    
    def get_api_url(self, agent_name: str) -> Optional[str]:
        """获取 Agent 的 API URL"""
        config = self._config.get(agent_name)
        if config:
            return f"http://localhost:{config['api_port']}"
        return None
    
    def get_ui_url(self, agent_name: str) -> Optional[str]:
        """获取 Agent 的 UI URL"""
        config = self._config.get(agent_name)
        if config:
            return f"http://localhost:{config['ui_port']}"
        return None
    
    async def check_agent_status(self, agent_name: str) -> Dict[str, Any]:
        """
        实时检查 Agent 状态（通过 HTTP 健康检查）
        
        Returns:
            {
                "status": "running" | "stopped" | "error",
                "api_url": str,
                "response_time": float,
                "error": str (if any),
                "capabilities": list (if available)
            }
        """
        config = self._config.get(agent_name)
        if not config:
            return {
                "status": "error",
                "error": f"未知的 Agent: {agent_name}"
            }
        
        api_url = f"http://localhost:{config['api_port']}"
        
        session = await self._get_session()
        start_time = datetime.now()
        
        try:
            # 尝试连接 /api/health
            async with session.get(f"{api_url}/api/health", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                response_time = (datetime.now() - start_time).total_seconds()
                
                if resp.status == 200:
                    health_data = await resp.json()
                    
                    # 尝试获取更详细的状态
                    capabilities = config.get("capabilities", [])
                    try:
                        async with session.get(f"{api_url}/api/status", timeout=aiohttp.ClientTimeout(total=2)) as status_resp:
                            if status_resp.status == 200:
                                status_data = await status_resp.json()
                                capabilities = status_data.get("capabilities", capabilities)
                    except:
                        pass
                    
                    return {
                        "status": "running",
                        "api_url": api_url,
                        "response_time": response_time,
                        "capabilities": capabilities,
                        "health": health_data
                    }
                else:
                    return {
                        "status": "error",
                        "api_url": api_url,
                        "error": f"HTTP {resp.status}"
                    }
                    
        except asyncio.TimeoutError:
            return {
                "status": "stopped",
                "api_url": api_url,
                "error": "连接超时（Agent 可能未启动）"
            }
        except aiohttp.ClientConnectorError:
            return {
                "status": "stopped",
                "api_url": api_url,
                "error": "无法连接（Agent 未启动或端口错误）"
            }
        except Exception as e:
            return {
                "status": "error",
                "api_url": api_url,
                "error": str(e)
            }
    
    async def send_task(self, agent_name: str, instruction: str, input_files: list = None) -> Dict[str, Any]:
        """
        发送任务到 Agent（实时 HTTP 调用）
        """
        config = self._config.get(agent_name)
        if not config:
            return {
                "status": "error",
                "error": f"未知的 Agent: {agent_name}"
            }
        
        api_url = f"http://localhost:{config['api_port']}"
        
        # 先检查 Agent 是否在线
        status = await self.check_agent_status(agent_name)
        if status["status"] != "running":
            return {
                "status": "error",
                "error": f"Agent {agent_name} 未运行。请先启动 {agent_name}（API: {api_url}）",
                "details": status.get("error", "")
            }
        
        session = await self._get_session()
        task_url = f"{api_url}/api/task"
        
        print(f"🔵 [Registry] 发送任务到: {task_url}")
        print(f"🔵 [Registry] 指令: {instruction[:100]}...")
        
        try:
            async with session.post(
                task_url,
                json={
                    "instruction": instruction,
                    "input_files": input_files or []
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"🟢 [Registry] 任务成功: {result.get('message', '')[:100]}...")
                    return result
                else:
                    error_text = await resp.text()
                    print(f"🔴 [Registry] HTTP {resp.status}: {error_text[:200]}")
                    return {
                        "status": "error",
                        "error": f"HTTP {resp.status}: {error_text[:200]}"
                    }
                    
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "error": f"请求超时 (60秒)，{agent_name} 可能正在处理大量任务"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"请求失败: {str(e)}"
            }
    
    async def get_all_status(self) -> Dict[str, Dict]:
        """获取所有 Agent 的实时状态"""
        results = {}
        for name in self._config.keys():
            results[name] = await self.check_agent_status(name)
        return results
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# 全局单例
_registry = None

def get_agent_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry