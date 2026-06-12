"""Conductor 核心逻辑 - 使用 Agent 注册表"""

import json
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from openai import OpenAI

from .core.message_bus import get_message_bus, Message
from .core.file_transfer import get_file_transfer
from .core.memory.agent_memory import AgentMemory
from .llm_config import get_llm_config
from .utils import log_with_timestamp, generate_msg_id, extract_schedule_command
from .agent_registry import get_agent_registry


class ConductorAgent:
    """主控 Agent"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.name = "conductor"
        
        # 加载配置文件
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        self.config = self._load_config(config_path)
        
        # 子 Agent 列表（从配置加载，但状态实时查询）
        self.sub_agents = self.config.get("sub_agents", [])
        
        # Agent 注册表
        self.registry = get_agent_registry()
        
        # 消息总线和文件传输
        self.bus = get_message_bus()
        self.bus.subscribe(self.name, self._on_message)
        self.file_transfer = get_file_transfer()
        
        # LLM 配置
        self.llm_config = get_llm_config()
        if not self.llm_config.validate():
            log_with_timestamp(self.name, "WARNING", "LLM API Key 未配置")
        
        # OpenAI 客户端
        self.client = OpenAI(**self.llm_config.get_openai_kwargs())
        self.model = self.llm_config.model
        self.temperature = self.llm_config.temperature
        
        # 创建 LLM 摘要回调
        def llm_summary_callback(prompt: str) -> str:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=300
                )
                return response.choices[0].message.content
            except Exception as e:
                log_with_timestamp(self.name, "WARNING", f"摘要生成失败: {e}")
                return None
        
        # 记忆系统
        memory_dir = Path(__file__).parent / "memory"
        self.memory = AgentMemory(self.name, memory_dir, llm_callback=llm_summary_callback)
        
        # 工具注册器
        from .tools import get_tool_registry, init_conductor_tools
        self.tools = get_tool_registry()
        init_conductor_tools()
        
        log_with_timestamp(self.name, "INFO", f"Conductor 初始化完成")
        log_with_timestamp(self.name, "INFO", f"记忆目录: {memory_dir}")
        log_with_timestamp(self.name, "INFO", f"LLM: {self.llm_config.provider}/{self.model}")
        log_with_timestamp(self.name, "INFO", f"已注册 {len(self.tools.list_tools())} 个工具")
    
    def _load_config(self, config_path: Path) -> dict:
        if not config_path.exists():
            return self._get_default_config()
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _get_default_config(self) -> dict:
        return {
            "name": "conductor",
            "sub_agents": [
                {"name": "creator", "enabled": True, "description": "内容生成 Agent"}
            ],
            "communication": {"timeout": 60},
            "memory": {"short_term_window": 30}
        }
    
    def _build_system_prompt(self) -> str:
        permanent_prompt = self.memory.get_permanent_prompt()
        sub_agent_info = self._get_sub_agent_info()
        tools_info = self.tools.get_tools_summary() if self.tools.list_tools() else ""
        
        return f"""{permanent_prompt}

{sub_agent_info}

{tools_info}

## 如何调用子 Agent

使用 `call_sub_agent` 工具。参数：
- `agent_name`: 子 Agent 名称（如 creator）
- `instruction`: 要执行的任务描述

示例：`call_sub_agent(agent_name="creator", instruction="请生成一个椅子模型")`

## 当前时间
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
    
    def _get_sub_agent_info(self) -> str:
        """获取子 Agent 信息（从注册表）"""
        agents = self.registry.get_all_agents()
        
        if not agents:
            return "暂无可用子 Agent"
        
        lines = ["## 可用子 Agent\n"]
        for agent in agents:
            lines.append(f"- **{agent['name']}**: {agent.get('description', '')}")
            lines.append(f"  API: http://localhost:{agent['api_port']}")
            if agent.get("capabilities"):
                lines.append(f"  能力: {', '.join(agent['capabilities'])}")
        return "\n".join(lines)
    
    def _get_conversation_context(self) -> List[Dict]:
        return self.memory.get_short_term_context()
    
    async def _execute_tool_calls(self, tool_calls: List) -> List[Dict]:
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            
            log_with_timestamp(self.name, "INFO", f"执行工具: {tool_name}")
            result = self.tools.execute(tool_name, **tool_args)
            
            results.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "content": result
            })
        return results
    
    async def _schedule_to_agent(self, agent_name: str, instruction: str) -> Dict[str, Any]:
        """
        调度任务到子 Agent（通过注册表实时调用）
        """
        log_with_timestamp(self.name, "INFO", f"📤 调度到 {agent_name}: {instruction[:100]}...")
        
        # 通过注册表发送任务（实时 HTTP）
        result = await self.registry.send_task(agent_name, instruction)
        
        if result.get("status") == "success":
            log_with_timestamp(self.name, "INFO", f"✅ 调度成功")
        else:
            log_with_timestamp(self.name, "WARNING", f"❌ 调度失败: {result.get('error')}")
        
        return result
    
    async def chat(self, user_input: str) -> str:
        """对话入口"""
        log_with_timestamp(self.name, "INFO", f"收到: {user_input[:50]}...")
        
        self.memory.add_short_term("user", user_input)
        
        messages = [{"role": "system", "content": self._build_system_prompt()}]
        messages.extend(self._get_conversation_context())
        messages.append({"role": "user", "content": user_input})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools.get_schemas() if self.tools.list_tools() else None,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=self.llm_config.max_tokens
            )
            
            message = response.choices[0].message
            reply = message.content or ""
            
            if message.tool_calls:
                log_with_timestamp(self.name, "INFO", f"调用 {len(message.tool_calls)} 个工具")
                
                messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]
                })
                
                tool_results = await self._execute_tool_calls(message.tool_calls)
                messages.extend(tool_results)
                
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.llm_config.max_tokens
                )
                reply = final_response.choices[0].message.content or ""
            
            # 兼容旧格式
            schedule = extract_schedule_command(reply)
            if schedule:
                agent_name, instruction = schedule
                log_with_timestamp(self.name, "INFO", f"检测到旧格式调度: {agent_name}")
                result = await self._schedule_to_agent(agent_name, instruction)
                if result.get("status") == "success":
                    reply = f"✅ 已调度 {agent_name}\n\n{result.get('message', '')}"
                else:
                    reply = f"❌ 调度失败: {result.get('error', '未知错误')}"
            
            self.memory.add_short_term("assistant", reply)
            return reply
            
        except Exception as e:
            error_msg = f"❌ 出错: {str(e)}"
            log_with_timestamp(self.name, "ERROR", str(e), error=True)
            return error_msg
    
    def _on_message(self, message: Message):
        log_with_timestamp(self.name, "INFO", f"收到消息: {message.msg_type}")
    
    # ========== 供工具调用的同步方法 ==========
    
    def call_sub_agent_sync(self, agent_name: str, instruction: str) -> str:
        """同步调用子 Agent（供工具使用）"""
        import asyncio
        
        async def _call():
            result = await self.registry.send_task(agent_name, instruction)
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
    
    def get_sub_agent_status_sync(self, agent_name: str = None) -> str:
        """同步获取子 Agent 状态"""
        import asyncio
        
        async def _get():
            if agent_name:
                return await self.registry.check_agent_status(agent_name)
            else:
                return await self.registry.get_all_status()
        
        result = asyncio.run(_get())
        
        if agent_name:
            status = result
            if status["status"] == "running":
                return f"✅ {agent_name}: 运行中\n   API: {status['api_url']}\n   响应时间: {status['response_time']:.2f}s"
            else:
                return f"❌ {agent_name}: {status['status']}\n   {status.get('error', '')}"
        else:
            lines = ["## 子 Agent 状态（实时检测）\n"]
            for name, status in result.items():
                icon = "🟢" if status["status"] == "running" else "⚫"
                lines.append(f"{icon} **{name}**: {status['status']}")
                if status.get("api_url"):
                    lines.append(f"   API: {status['api_url']}")
            return "\n".join(lines)


# 单例
_conductor = None

def get_conductor() -> ConductorAgent:
    global _conductor
    if _conductor is None:
        _conductor = ConductorAgent()
    return _conductor