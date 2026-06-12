"""HTTP 客户端 - 用于主 Agent 调用从 Agent"""

import aiohttp
import asyncio
from typing import Dict, Any, Optional, List


class AgentHTTPClient:
    """从 Agent HTTP 客户端"""
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._agents: Dict[str, str] = {}  # name -> base_url
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    def register_agent(self, name: str, port: int):
        """注册从 Agent（注意：port 是 API 端口，不是 UI 端口）"""
        base_url = f"http://localhost:{port}"
        self._agents[name] = base_url
        print(f"📡 [HTTP Client] 注册 Agent: {name} -> {base_url}")
        print(f"📡 [HTTP Client] 当前已注册: {list(self._agents.keys())}")
    
    def unregister_agent(self, name: str):
        if name in self._agents:
            del self._agents[name]
            print(f"📡 [HTTP Client] 注销 Agent: {name}")
    
    def get_registered_agents(self) -> List[str]:
        return list(self._agents.keys())
    
    async def send_task(self, agent_name: str, instruction: str, input_files: list = None) -> Dict[str, Any]:
        """
        发送任务到从 Agent
        
        Args:
            agent_name: 子 Agent 名称
            instruction: 自然语言指令
            input_files: 输入文件列表
        """
        # 1. 检查是否已注册
        if agent_name not in self._agents:
            return {
                "status": "error", 
                "error": f"❌ Agent '{agent_name}' 未注册。已注册的 Agent: {list(self._agents.keys())}"
            }
        
        base_url = self._agents[agent_name]
        url = f"{base_url}/api/task"
        
        print(f"🔵 [HTTP Client] 发送请求到: {url}")
        print(f"🔵 [HTTP Client] 指令: {instruction[:100]}...")
        
        session = await self._get_session()
        
        try:
            async with session.post(
                url, 
                json={
                    "instruction": instruction,
                    "input_files": input_files or []
                },
                timeout=aiohttp.ClientTimeout(total=240)
            ) as resp:
                print(f"🟢 [HTTP Client] 响应状态码: {resp.status}")
                
                if resp.status == 200:
                    result = await resp.json()
                    print(f"🟢 [HTTP Client] 响应成功: {result.get('message', '')[:100]}...")
                    return result
                else:
                    error_text = await resp.text()
                    print(f"🔴 [HTTP Client] HTTP {resp.status}: {error_text[:200]}")
                    return {
                        "status": "error", 
                        "error": f"HTTP {resp.status}: {error_text[:200]}"
                    }
                    
        except aiohttp.ClientConnectorError as e:
            print(f"🔴 [HTTP Client] 连接失败: {e}")
            return {
                "status": "error",
                "error": f"❌ 无法连接到 {agent_name} (端口可能不对)。期望地址: {base_url}"
            }
        except asyncio.TimeoutError:
            print(f"🔴 [HTTP Client] 请求超时")
            return {
                "status": "error",
                "error": f"❌ 请求超时 (240秒)，{agent_name} 可能处理太慢或未响应"
            }
        except Exception as e:
            print(f"🔴 [HTTP Client] 异常: {type(e).__name__}: {e}")
            return {
                "status": "error",
                "error": f"❌ 请求失败: {str(e)}"
            }
    
    async def get_status(self, agent_name: str) -> Dict[str, Any]:
        """获取从 Agent 状态"""
        if agent_name not in self._agents:
            return {"status": "error", "error": f"Agent {agent_name} 未注册"}
        
        url = f"{self._agents[agent_name]}/api/status"
        session = await self._get_session()
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"status": "error", "error": f"HTTP {resp.status}"}
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