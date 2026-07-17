"""HTTP 客户端 - 用于主 Agent 调用从 Agent"""

import aiohttp
import asyncio
from typing import Dict, Any, Optional, List


class AgentHTTPClient:
    """从 Agent HTTP 客户端"""
    
    HARDCODED_AGENTS = {
        "creator": 7861,
        "scavenger": 7862,
        "engineer": 7863,
    }
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._agents: Dict[str, str] = {}
        for name, port in self.HARDCODED_AGENTS.items():
            self._agents[name] = f"http://localhost:{port}"
        print(f"📡 HTTP 客户端初始化，已注册 Agent: {list(self._agents.keys())}")
    
    def register_agent(self, name: str, port: int):
        self._agents[name] = f"http://localhost:{port}"
        print(f"📡 注册 Agent: {name} -> {self._agents[name]}")
    
    def unregister_agent(self, name: str):
        if name in self._agents:
            del self._agents[name]
            print(f"📡 注销 Agent: {name}")
    
    def is_registered(self, name: str) -> bool:
        return name in self._agents
    
    def get_registered_agents(self) -> list:
        return list(self._agents.keys())
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def send_task(
        self, 
        agent_name: str, 
        instruction: str, 
        input_files: list = None,
        **kwargs  # ← 支持额外参数（task_id等），未来扩展用
    ) -> Dict[str, Any]:
        """发送任务到从 Agent"""
        if agent_name not in self._agents:
            return {
                "status": "error", 
                "error": f"Agent {agent_name} 未注册。可用 Agent: {list(self._agents.keys())}"
            }
        
        session = await self._get_session()
        url = f"{self._agents[agent_name]}/api/task"
        
        # ========== 构建请求体 ==========
        payload = {
            "instruction": instruction,
            "input_files": input_files or []
        }
        # 如果有额外参数，也传入（如 task_id, callback_url 等）
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value
        
        print(f"🔵 [HTTP] 发送请求到 {url}")
        print(f"🔵 [HTTP] 指令: {instruction[:100]}...")
        
        try:
            timeout = aiohttp.ClientTimeout(total=180, connect=30)
            async with session.post(url, json=payload, timeout=timeout) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result
                else:
                    error_text = await resp.text()
                    return {"status": "error", "error": f"HTTP {resp.status}: {error_text[:200]}"}
                    
        except asyncio.TimeoutError:
            return {"status": "error", "error": "请求超时"}
        except aiohttp.ClientConnectorError as e:
            return {"status": "error", "error": f"无法连接到 {agent_name}"}
        except Exception as e:
            return {"status": "error", "error": f"连接失败: {str(e)}"}
    
    async def get_status(self, agent_name: str) -> Dict[str, Any]:
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
        result = await self.get_status(agent_name)
        return result.get("status") == "active" or result.get("status") == "ok"
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


_http_client = None


def get_http_client() -> AgentHTTPClient:
    global _http_client
    if _http_client is None:
        _http_client = AgentHTTPClient()
    return _http_client