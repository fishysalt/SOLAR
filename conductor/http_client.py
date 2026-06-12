"""HTTP 客户端 - 用于主 Agent 调用从 Agent"""

import aiohttp
import asyncio
from typing import Dict, Any, Optional, List


class AgentHTTPClient:
    """从 Agent HTTP 客户端"""
    
    # 硬编码 Agent 端口映射（确保路由表始终有数据）
    HARDCODED_AGENTS = {
        "creator": 7861,
        "scavenger": 7862,
    }
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        # 初始化时直接使用硬编码映射
        self._agents: Dict[str, str] = {}
        for name, port in self.HARDCODED_AGENTS.items():
            self._agents[name] = f"http://localhost:{port}"
        print(f"📡 HTTP 客户端初始化，已注册 Agent: {list(self._agents.keys())}")
    
    def register_agent(self, name: str, port: int):
        """注册从 Agent（动态添加时调用）"""
        self._agents[name] = f"http://localhost:{port}"
        print(f"📡 注册 Agent: {name} -> {self._agents[name]}")
    
    def unregister_agent(self, name: str):
        """注销从 Agent"""
        if name in self._agents:
            del self._agents[name]
            print(f"📡 注销 Agent: {name}")
    
    def is_registered(self, name: str) -> bool:
        """检查 Agent 是否已注册"""
        return name in self._agents
    
    def get_registered_agents(self) -> list:
        """获取已注册的 Agent 列表"""
        return list(self._agents.keys())
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def send_task(self, agent_name: str, instruction: str, input_files: list = None) -> Dict[str, Any]:
        """发送任务到从 Agent"""
        if agent_name not in self._agents:
            return {
                "status": "error", 
                "error": f"Agent {agent_name} 未注册。可用 Agent: {list(self._agents.keys())}"
            }
        
        session = await self._get_session()
        url = f"{self._agents[agent_name]}/api/task"
        
        print(f"🔵 [HTTP] 发送请求到 {url}")
        print(f"🔵 [HTTP] 指令: {instruction[:100]}...")
        
        try:
            timeout = aiohttp.ClientTimeout(total=180, connect=30)
            async with session.post(url, json={
                "instruction": instruction,
                "input_files": input_files or []
            }, timeout=timeout) as resp:
                print(f"🟢 [HTTP] 响应状态码: {resp.status}")
                
                if resp.status == 200:
                    result = await resp.json()
                    print(f"🟢 [HTTP] 响应成功")
                    return result
                else:
                    error_text = await resp.text()
                    print(f"🔴 [HTTP] 错误响应: {resp.status} - {error_text[:200]}")
                    return {"status": "error", "error": f"HTTP {resp.status}: {error_text[:200]}"}
                    
        except asyncio.TimeoutError:
            print(f"🔴 [HTTP] 请求超时（180秒）")
            return {"status": "error", "error": "请求超时"}
        except aiohttp.ClientConnectorError as e:
            print(f"🔴 [HTTP] 连接失败: {e}")
            return {"status": "error", "error": f"无法连接到 {agent_name}，请确保已启动"}
        except Exception as e:
            print(f"🔴 [HTTP] 异常: {type(e).__name__}: {e}")
            return {"status": "error", "error": f"连接失败: {str(e)}"}
    
    async def get_status(self, agent_name: str) -> Dict[str, Any]:
        """获取从 Agent 状态"""
        if agent_name not in self._agents:
            return {"status": "error", "error": f"Agent {agent_name} 未注册"}
        
        session = await self._get_session()
        url = f"{self._agents[agent_name]}/api/status"
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {"status": "error", "error": f"HTTP {resp.status}"}
        except asyncio.TimeoutError:
            return {"status": "error", "error": "状态检查超时"}
        except aiohttp.ClientConnectorError:
            return {"status": "error", "error": "无法连接，Agent 可能未启动"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def health_check(self, agent_name: str) -> bool:
        """健康检查"""
        result = await self.get_status(agent_name)
        return result.get("status") == "active" or result.get("status") == "ok"
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# 全局客户端
_http_client = None

def get_http_client() -> AgentHTTPClient:
    global _http_client
    if _http_client is None:
        _http_client = AgentHTTPClient()
    return _http_client