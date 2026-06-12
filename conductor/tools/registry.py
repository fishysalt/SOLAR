"""工具注册器 - 支持 LLM 驱动的工具降级"""

import re
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass

from .categories import ToolCategory, infer_category_from_name, get_category_description


@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    original_name: str
    rank: int
    category: ToolCategory
    func: Callable
    description: str
    parameters: dict
    
    def to_schema(self) -> dict:
        """转换为 OpenAI 函数格式"""
        return {
            "type": "function",
            "function": {
                "name": self.original_name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


def extract_rank_from_name(tool_name: str) -> tuple:
    """
    从工具名称中提取 rank 和真实名称
    格式: [rankN]_toolname 或 toolname
    """
    pattern = r'^\[rank(\d+)\]_(.+)$'
    match = re.match(pattern, tool_name)
    if match:
        return int(match.group(1)), match.group(2)
    return 999, tool_name


class ToolRegistry:
    """
    工具注册器
    
    设计原则：
    1. 代码只负责注册和存储工具
    2. 工具分类由 LLM 根据 description 自行判断
    3. 降级顺序由 rank 决定，但使用哪个工具由 LLM 选择
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
        
        # 存储所有工具（按 clean_name）
        self._tools: Dict[str, ToolInfo] = {}
        
        # 按类别分组的工具（用于降级建议）
        self._by_category: Dict[ToolCategory, List[ToolInfo]] = {}
        
        print("🔧 工具注册器已初始化")
    
    def _ensure_category(self, category: ToolCategory):
        """确保类别存在"""
        if category not in self._by_category:
            self._by_category[category] = []
    
    def register(self, name: str, description: str, func: Callable, parameters: dict, 
                 category: ToolCategory = None):
        """
        注册工具
        
        Args:
            name: 工具名称（可带 [rankN]_ 前缀）
            description: 工具描述（LLM 会据此判断）
            func: 执行函数
            parameters: 参数 schema
            category: 类别（不传则根据名称自动推断）
        """
        rank, clean_name = extract_rank_from_name(name)
        
        # 确定类别
        if category is None:
            category = infer_category_from_name(clean_name)
        
        tool = ToolInfo(
            name=clean_name,
            original_name=name,
            rank=rank,
            category=category,
            func=func,
            description=description,
            parameters=parameters
        )
        
        self._tools[clean_name] = tool
        self._ensure_category(category)
        self._by_category[category].append(tool)
        
        # 按 rank 排序
        self._by_category[category].sort(key=lambda t: t.rank)
        
        print(f"   🔧 注册: {name} (rank={rank}, category={category.value})")
    
    def register_multiple(self, tools: List[dict]):
        """批量注册"""
        for tool in tools:
            self.register(**tool)
    
    def get_tool(self, name: str) -> Optional[ToolInfo]:
        """获取工具信息"""
        _, clean_name = extract_rank_from_name(name)
        return self._tools.get(clean_name)
    
    def execute(self, name: str, **kwargs) -> str:
        """执行工具"""
        tool = self.get_tool(name)
        if not tool:
            return f"❌ 工具不存在: {name}"
        
        try:
            result = tool.func(**kwargs)
            return str(result)
        except Exception as e:
            return f"❌ 工具执行失败: {str(e)}"
    
    def get_schemas(self) -> List[dict]:
        """获取所有工具的 schema（供 LLM 选择）"""
        return [tool.to_schema() for tool in self._tools.values()]
    
    def get_tools_summary(self) -> str:
        """
        获取工具摘要（供 LLM 决策）
        
        LLM 会根据这个信息来决定使用哪个工具以及降级策略
        """
        lines = ["## 可用工具列表\n"]
        
        for tool in self._tools.values():
            lines.append(f"### {tool.original_name}")
            lines.append(f"描述: {tool.description}")
            lines.append(f"类别: {tool.category.value}")
            lines.append(f"优先级: {tool.rank}")
            lines.append("")
        
        return "\n".join(lines)
    
    def get_tools_by_category_summary(self) -> str:
        """
        按类别获取工具摘要（供 LLM 做降级决策）
        """
        lines = ["## 按类别分类的工具\n"]
        
        for category, tools in self._by_category.items():
            if not tools:
                continue
            
            lines.append(f"### {category.value}")
            lines.append(f"说明: {get_category_description(category)}")
            for tool in tools:
                lines.append(f"  - {tool.original_name}: {tool.description}")
            lines.append("")
        
        return "\n".join(lines)
    
    def get_fallback_suggestion(self, failed_tool: str, original_task: str) -> dict:
        """
        生成降级建议（供 LLM 参考）
        
        最终由 LLM 决策是否采纳
        """
        tool = self.get_tool(failed_tool)
        if not tool:
            return {
                "has_fallback": False,
                "message": f"工具 {failed_tool} 不存在",
                "suggested_tools": []
            }
        
        # 获取同类别下优先级更低的工具
        category_tools = self._by_category.get(tool.category, [])
        lower_rank_tools = [t for t in category_tools if t.rank > tool.rank]
        
        if not lower_rank_tools:
            return {
                "has_fallback": False,
                "message": f"没有比 {failed_tool} 更低优先级的同类别工具",
                "suggested_tools": []
            }
        
        return {
            "has_fallback": True,
            "failed_tool": failed_tool,
            "failed_category": tool.category.value,
            "category_description": get_category_description(tool.category),
            "original_task": original_task,
            "suggested_tools": [
                {
                    "name": t.original_name,
                    "description": t.description,
                    "rank": t.rank
                }
                for t in lower_rank_tools
            ]
        }
    
    def list_tools(self, include_rank: bool = True) -> List[str]:
        """列出所有工具名称"""
        if include_rank:
            return [t.original_name for t in self._tools.values()]
        return [t.name for t in self._tools.values()]
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "total_tools": len(self._tools),
            "by_category": {
                cat.value: len(tools) for cat, tools in self._by_category.items() if tools
            }
        }
    
    def reload_categories(self):
        """重新加载类别配置（热更新）"""
        from . import categories
        import importlib
        importlib.reload(categories)
        print("📁 工具类别配置已重载")


# 全局单例
_tool_registry = None

def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry