"""Conductor 状态查询工具 - 使用 HTTP 检测真实状态"""

import asyncio
from conductor.agent import get_conductor
from conductor.http_client import get_http_client


def _run_async(coro):
    """安全运行异步函数"""
    try:
        # 尝试获取当前事件循环
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果循环已在运行，创建新任务
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            # 循环未运行，直接运行
            return loop.run_until_complete(coro)
    except RuntimeError:
        # 没有事件循环，创建新的
        return asyncio.run(coro)


def get_agent_status(agent_name: str = None) -> str:
    """
    获取 Agent 运行状态（通过 HTTP 健康检查）
    
    Args:
        agent_name: 子 Agent 名称，不传则返回所有
    """
    conductor = get_conductor()
    client = get_http_client()
    
    async def check_status(agent):
        """异步检查单个 Agent 状态"""
        if agent in client._agents:
            try:
                result = await client.get_status(agent)
                if result.get("status") == "active" or result.get("status") == "ok":
                    return "running", result
                else:
                    return "error", result
            except Exception:
                return "not_responding", None
        else:
            return "not_registered", None
    
    async def check_all():
        results = {}
        for agent in conductor.sub_agents:
            name = agent["name"]
            status, detail = await check_status(name)
            results[name] = {"status": status, "detail": detail, "config": agent}
        return results
    
    if agent_name:
        # 检查单个 Agent
        if agent_name not in [a["name"] for a in conductor.sub_agents]:
            return f"❌ 未知 Agent: {agent_name}"
        
        status, detail = _run_async(check_status(agent_name))
        
        if status == "running":
            caps = ', '.join(detail.get('capabilities', [])) if detail else '未知'
            return f"✅ {agent_name}: 运行中\n   API: {client._agents.get(agent_name, '未知')}\n   能力: {caps}"
        elif status == "not_responding":
            return f"⚠️ {agent_name}: API 无响应（进程可能已崩溃）"
        else:
            return f"⏸️ {agent_name}: 未启动（未在 HTTP 客户端注册）"
    else:
        # 返回所有 Agent 状态
        results = _run_async(check_all())
        
        lines = ["📊 Agent 状态（HTTP 实时检测）:\n"]
        lines.append("| Agent | 状态 | API 地址 | 能力 |")
        lines.append("|-------|------|----------|------|")
        
        for name, info in results.items():
            status = info["status"]
            config = info["config"]
            
            if status == "running":
                status_icon = "🟢 运行中"
                api_url = client._agents.get(name, "-")
                caps = ', '.join(config.get("capabilities", []))[:30]
            elif status == "not_responding":
                status_icon = "🔴 无响应"
                api_url = client._agents.get(name, "-")
                caps = ', '.join(config.get("capabilities", []))[:30]
            else:
                status_icon = "⚫ 未启动"
                api_url = "-"
                caps = ', '.join(config.get("capabilities", []))[:30]
            
            lines.append(f"| {name} | {status_icon} | {api_url} | {caps} |")
        
        return "\n".join(lines)


def list_available_agents() -> str:
    """列出所有可用的子 Agent（从配置读取）"""
    conductor = get_conductor()
    
    lines = ["📋 可用子 Agent:\n"]
    lines.append("| Agent | 描述 | 能力 | 状态 |")
    lines.append("|-------|------|------|------|")
    
    for agent in conductor.sub_agents:
        name = agent["name"]
        desc = agent.get("description", "-")[:30]
        caps = ', '.join(agent.get("capabilities", []))[:30]
        enabled = "✅ 已启用" if agent.get("enabled", True) else "⏸️ 已禁用"
        lines.append(f"| {name} | {desc} | {caps} | {enabled} |")
    
    return "\n".join(lines)


def get_agent_capabilities(agent_name: str = None) -> str:
    """
    获取 Agent 的能力详情
    
    Args:
        agent_name: 子 Agent 名称，不传则返回所有
    """
    conductor = get_conductor()
    client = get_http_client()
    
    async def get_capabilities(name):
        if name in client._agents:
            result = await client.get_status(name)
            return result.get("capabilities", [])
        return []
    
    if agent_name:
        caps = _run_async(get_capabilities(agent_name))
        if caps:
            return f"**{agent_name}** 的能力:\n" + "\n".join([f"- {c}" for c in caps])
        else:
            return f"无法获取 {agent_name} 的能力（Agent 未启动或未响应）"
    else:
        lines = ["## 各 Agent 能力详情\n"]
        for agent in conductor.sub_agents:
            name = agent["name"]
            caps = _run_async(get_capabilities(name))
            if caps:
                lines.append(f"### {name}")
                for c in caps:
                    lines.append(f"- {c}")
                lines.append("")
            else:
                lines.append(f"### {name}（未启动或无能力信息）")
        return "\n".join(lines)


# 工具定义
GET_AGENT_STATUS_TOOL = {
    "name": "get_agent_status",
    "description": "获取子 Agent 的运行状态。会通过 HTTP 健康检查检测真实状态。",
    "func": get_agent_status,
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string", "description": "子 Agent 名称，不传则返回所有"}
        },
        "required": []
    }
}

LIST_AGENTS_TOOL = {
    "name": "list_available_agents",
    "description": "列出所有可用的子 Agent 及其描述和能力。",
    "func": list_available_agents,
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

GET_AGENT_CAPABILITIES_TOOL = {
    "name": "get_agent_capabilities",
    "description": "获取指定 Agent 的详细能力列表。",
    "func": get_agent_capabilities,
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string", "description": "子 Agent 名称"}
        },
        "required": []
    }
}