"""子 Agent 调用工具 - 使用注册表"""

from conductor.agent import get_conductor


def call_sub_agent(agent_name: str, instruction: str) -> str:
    """
    调用子 Agent 执行任务
    
    这是主 Agent 与子 Agent 通信的核心工具。
    
    Args:
        agent_name: 子 Agent 名称，如 "creator"
        instruction: 要执行的任务描述
    
    Returns:
        子 Agent 的回复
    """
    conductor = get_conductor()
    return conductor.call_sub_agent_sync(agent_name, instruction)


def get_sub_agent_status(agent_name: str = None) -> str:
    """
    获取子 Agent 的运行状态
    
    Args:
        agent_name: 子 Agent 名称，不传则返回所有
    """
    conductor = get_conductor()
    return conductor.get_sub_agent_status_sync(agent_name)


# 工具定义
CALL_SUB_AGENT_TOOL = {
    "name": "call_sub_agent",
    "description": """调用子 Agent 执行任务。

使用场景：
- 用户要求生成视频、3D模型 → 调用 creator
- 任何需要专门能力的任务

参数：
- agent_name: 子 Agent 名称（如 creator）
- instruction: 要执行的任务描述，要清晰具体

示例：
- agent_name="creator", instruction="请生成一个现代风格的椅子3D模型"
""",
    "func": call_sub_agent,
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "子 Agent 名称",
                "enum": ["creator","scavenger"]
            },
            "instruction": {
                "type": "string",
                "description": "要交给子 Agent 执行的任务描述"
            }
        },
        "required": ["agent_name", "instruction"]
    }
}

GET_SUB_AGENT_STATUS_TOOL = {
    "name": "get_sub_agent_status",
    "description": "获取子 Agent 的运行状态（实时检测）",
    "func": get_sub_agent_status,
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "子 Agent 名称，不传则返回所有"
            }
        },
        "required": []
    }
}