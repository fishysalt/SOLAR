"""Conductor 记忆操作工具"""

from ..categories import ToolCategory


def view_my_memory(category: str = None, limit: int = 20) -> str:
    """
    查看 Conductor 自己的长期记忆
    
    Args:
        category: 记忆分类（可选: general/preference/knowledge）
        limit: 返回数量
    """
    from conductor.agent import get_conductor
    
    conductor = get_conductor()
    
    if category:
        results = conductor.memory.search_long_term(category, limit=limit)
    else:
        results = conductor.memory.get_long_term_all(limit)
    
    if not results:
        return "📭 暂无长期记忆"
    
    lines = ["📋 长期记忆列表:\n"]
    for i, mem in enumerate(results, 1):
        lines.append(f"{i}. ID:{mem['id']} | [{mem['category']}] {mem['content'][:100]}... (重要性: {mem['importance']})")
    
    return "\n".join(lines)


def add_to_my_memory(content: str, category: str = "general", importance: float = 0.5) -> str:
    """
    向 Conductor 的长期记忆添加内容
    
    Args:
        content: 要记住的内容
        category: 分类（general/preference/knowledge）
        importance: 重要性 0-1
    """
    from conductor.agent import get_conductor
    
    conductor = get_conductor()
    mem_id = conductor.memory.add_long_term(content, category, importance)
    
    return f"✅ 已添加到记忆 (ID: {mem_id})"


def search_my_memory(keyword: str, category: str = None) -> str:
    """
    搜索 Conductor 的长期记忆
    
    Args:
        keyword: 搜索关键词
        category: 分类过滤（可选）
    """
    from conductor.agent import get_conductor
    
    conductor = get_conductor()
    results = conductor.memory.search_long_term(keyword, category)
    
    if not results:
        return f"🔍 未找到包含 '{keyword}' 的记忆"
    
    lines = [f"🔍 搜索 '{keyword}' 结果:\n"]
    for i, mem in enumerate(results, 1):
        lines.append(f"{i}. ID:{mem['id']} | [{mem['category']}] {mem['content'][:100]}...")
    
    return "\n".join(lines)


def delete_from_my_memory(memory_id: int) -> str:
    """
    从 Conductor 的长期记忆中删除指定条目
    
    Args:
        memory_id: 要删除的记忆 ID（可以通过 view_my_memory 查看）
    """
    from conductor.agent import get_conductor
    
    conductor = get_conductor()
    success = conductor.memory.delete_long_term(memory_id)
    
    if success:
        return f"✅ 已删除记忆 ID: {memory_id}"
    else:
        return f"❌ 未找到记忆 ID: {memory_id}"


def clear_my_memory_by_category(category: str) -> str:
    """
    按分类清空 Conductor 的长期记忆
    
    Args:
        category: 分类名称 (general/preference/knowledge)
    """
    from conductor.agent import get_conductor
    
    conductor = get_conductor()
    count = conductor.memory.clear_long_term_by_category(category)
    
    return f"✅ 已清空分类 '{category}'，共删除 {count} 条记忆"


def clear_all_my_memory() -> str:
    """
    清空 Conductor 的所有长期记忆（危险操作，会提示确认）
    """
    from conductor.agent import get_conductor
    
    conductor = get_conductor()
    count = conductor.memory.clear_long_term()
    
    return f"✅ 已清空所有长期记忆，共删除 {count} 条"


# 工具定义
VIEW_MEMORY_TOOL = {
    "name": "view_my_memory",
    "description": "查看 Conductor 的长期记忆列表。可以按分类筛选，会显示每条记忆的 ID、分类和内容。",
    "func": view_my_memory,
    "parameters": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "记忆分类，可选: general/preference/knowledge"},
            "limit": {"type": "integer", "description": "返回数量", "default": 20}
        },
        "required": []
    }
}

ADD_MEMORY_TOOL = {
    "name": "add_to_my_memory",
    "description": "向 Conductor 的长期记忆添加重要信息。用户要求记住的内容应该用此工具存储。",
    "func": add_to_my_memory,
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "要记住的内容"},
            "category": {"type": "string", "description": "分类: general(通用)/preference(偏好)/knowledge(知识)", "default": "general"},
            "importance": {"type": "number", "description": "重要性 0-1", "default": 0.5}
        },
        "required": ["content"]
    }
}

SEARCH_MEMORY_TOOL = {
    "name": "search_my_memory",
    "description": "搜索 Conductor 的长期记忆中的内容。当用户询问之前的信息时使用。",
    "func": search_my_memory,
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "搜索关键词"},
            "category": {"type": "string", "description": "分类过滤"}
        },
        "required": ["keyword"]
    }
}

DELETE_MEMORY_TOOL = {
    "name": "delete_from_my_memory",
    "description": "从 Conductor 的长期记忆中删除指定条目。当用户要求忘记某个信息或删除记忆时使用。需要先通过 view_my_memory 查看记忆 ID。",
    "func": delete_from_my_memory,
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "integer", "description": "要删除的记忆 ID"}
        },
        "required": ["memory_id"]
    }
}

CLEAR_MEMORY_BY_CATEGORY_TOOL = {
    "name": "clear_my_memory_by_category",
    "description": "按分类清空 Conductor 的长期记忆。当用户要求清空某类记忆时使用。",
    "func": clear_my_memory_by_category,
    "parameters": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "分类名称: general/preference/knowledge"}
        },
        "required": ["category"]
    }
}

CLEAR_ALL_MEMORY_TOOL = {
    "name": "clear_all_my_memory",
    "description": "清空 Conductor 的所有长期记忆。这是危险操作，只有在用户明确要求清空所有记忆时才使用。",
    "func": clear_all_my_memory,
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
}