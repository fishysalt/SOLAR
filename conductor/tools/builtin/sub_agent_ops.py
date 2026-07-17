"""子Agent调用工具"""

from typing import Optional
from ...agent import get_conductor


def call_sub_agent_sync(agent_name: str, instruction: str) -> str:
    """
    同步调用子Agent（供工具使用）
    """
    conductor = get_conductor()
    import asyncio
    
    async def _call():
        from ...http_client import get_http_client
        client = get_http_client()
        result = await client.send_task(agent_name, instruction)
        if result.get("status") == "success":
            return result.get("message", "任务完成")
        else:
            return f"❌ 失败: {result.get('error', '未知错误')}"
    
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                return executor.submit(asyncio.run, _call()).result()
        else:
            return loop.run_until_complete(_call())
    except RuntimeError:
        return asyncio.run(_call())


def get_sub_agent_status_sync(agent_name: str) -> str:
    """获取子Agent状态（同步）"""
    import requests
    conductor = get_conductor()
    config = conductor.registry._config.get(agent_name)
    if not config:
        return f"❌ 未知 Agent: {agent_name}"
    
    api_url = f"http://localhost:{config['api_port']}"
    try:
        resp = requests.get(f"{api_url}/api/health", timeout=3)
        if resp.status_code == 200:
            return f"✅ {agent_name}: 运行中\n   API: {api_url}"
        else:
            return f"❌ {agent_name}: 未响应 (HTTP {resp.status_code})"
    except requests.exceptions.ConnectionError:
        return f"❌ {agent_name}: 未启动 (无法连接 {api_url})"
    except Exception as e:
        return f"❌ {agent_name}: 错误 - {str(e)}"


# ========== 工具定义（包含 func） ==========

CALL_SUB_AGENT_TOOL = {
    "name": "call_sub_agent",
    "description": "调用子Agent执行任务，适用于需要其他Agent能力的情况",
    "func": call_sub_agent_sync,  # ← 关键：必须有
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "子Agent名称: creator, scavenger, engineer"
            },
            "instruction": {
                "type": "string",
                "description": "要执行的任务描述"
            }
        },
        "required": ["agent_name", "instruction"]
    }
}

GET_SUB_AGENT_STATUS_TOOL = {
    "name": "get_sub_agent_status",
    "description": "获取子Agent的运行状态",
    "func": get_sub_agent_status_sync,  # ← 关键：必须有
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "子Agent名称"
            }
        },
        "required": ["agent_name"]
    }
}