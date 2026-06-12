"""工具注册器 - 支持 LLM 驱动的工具调用"""

import re
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass


@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    func: Callable
    description: str
    parameters: dict
    
    def to_schema(self) -> dict:
        """转换为 OpenAI 函数格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


class ToolRegistry:
    """工具注册器（单例）"""
    
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
        self._tools: Dict[str, ToolInfo] = {}
        print("🔧 Creator 工具注册器已初始化")
    
    def register(self, name: str, description: str, func: Callable, parameters: dict):
        """注册工具"""
        tool = ToolInfo(
            name=name,
            func=func,
            description=description,
            parameters=parameters
        )
        self._tools[name] = tool
        print(f"   🔧 注册工具: {name}")
    
    def register_multiple(self, tools: List[dict]):
        """批量注册"""
        for tool in tools:
            self.register(**tool)
    
    def get_tool(self, name: str) -> Optional[ToolInfo]:
        """获取工具"""
        return self._tools.get(name)
    
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
        """获取所有工具的 schema"""
        return [tool.to_schema() for tool in self._tools.values()]
    
    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())
    
    def get_tools_summary(self) -> str:
        """获取工具摘要"""
        if not self._tools:
            return "暂无可用工具"
        
        lines = ["## 可用工具列表\n"]
        for tool in self._tools.values():
            lines.append(f"- **{tool.name}**: {tool.description}")
        return "\n".join(lines)


# 全局单例
_tool_registry = None

def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry