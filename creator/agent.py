"""Creator 核心逻辑 - 接入 LLM + 长期记忆 + RAG + 文件传输 + MCP 外部工具"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))

from conductor.core.file_transfer import get_file_transfer
from conductor.core.memory.agent_memory import AgentMemory
from conductor.llm_config import get_llm_config
from conductor.utils import log_with_timestamp
from .rag.knowledge_base import KnowledgeBase


class CreatorAgent:
    """具备视频生成、3D建模、搜索能力的从 Agent，支持 MCP 外部工具"""
    
    def __init__(self):
        self.name = "creator"
        self.display_name = "✨ Creator"
        self.capabilities = [
            "video_generation",
            "model_generation", 
            "web_search"
        ]
        
        # 文件通道
        self.file_transfer = get_file_transfer()
        
        # 独立记忆系统
        memory_dir = Path(__file__).parent / "memory"
        
        # RAG 知识库
        rag_dir = Path(__file__).parent / "rag"
        self.knowledge_base = KnowledgeBase(rag_dir)
        
        # LLM 配置
        self.llm_config = get_llm_config()
        if not self.llm_config.validate():
            log_with_timestamp(self.name, "WARNING", "LLM API Key 未配置，将使用简单模式")
        
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
        
        # 记忆系统（传入 LLM 回调）
        self.memory = AgentMemory(self.name, memory_dir, llm_callback=llm_summary_callback)
        
        # ========== 工具注册器（统一管理本地工具 + MCP 外部工具）==========
        from .tools import get_tool_registry, init_creator_tools
        self.tools = get_tool_registry()
        
        # init_creator_tools() 会同时注册：
        # 1. builtin 工具（记忆操作等本地工具）
        # 2. MCP 外部工具（从 config.json 读取并自动发现）
        init_creator_tools()
        
        self.current_task = None
        self.input_dir = Path(__file__).parent / "data" / "input"
        self.output_dir = Path(__file__).parent / "data" / "output"
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        log_with_timestamp(self.name, "INFO", f"初始化完成")
        log_with_timestamp(self.name, "INFO", f"记忆目录: {memory_dir}")
        log_with_timestamp(self.name, "INFO", f"RAG 目录: {rag_dir}")
        log_with_timestamp(self.name, "INFO", f"输入目录: {self.input_dir}")
        log_with_timestamp(self.name, "INFO", f"输出目录: {self.output_dir}")
        log_with_timestamp(self.name, "INFO", f"RAG 文档数: {self.knowledge_base.get_stats()['document_count']}")
        log_with_timestamp(self.name, "INFO", f"LLM 提供商: {self.llm_config.provider}")
        log_with_timestamp(self.name, "INFO", f"LLM 模型: {self.model}")
        log_with_timestamp(self.name, "INFO", f"已注册 {len(self.tools.list_tools())} 个工具（含 MCP 外部工具）")
        log_with_timestamp(self.name, "INFO", f"能力: {', '.join(self.capabilities)}")
    
    def _retrieve_relevant_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """检索相关的长期记忆"""
        return self.memory.search_long_term(keyword=query, limit=limit)
    
    def _retrieve_relevant_knowledge(self, query: str) -> List[Dict]:
        """
        检索相关的 RAG 知识
    
        策略：
        1. 先从 RAG 记录中搜索历史成功/失败经验
        2. 再从静态知识库文件中检索
        """
        from .tools.builtin.rag_manager import search_rag_structured
    
        results = []
    
        # 策略1：从 RAG 记录中搜索结构化经验
        structured_results = search_rag_structured(query)
        if structured_results:
            log_with_timestamp(self.name, "INFO", f"📚 RAG 记录检索到 {len(structured_results)} 条相关经验")
            for item in structured_results[:5]:
                results.append({
                    "source": f"rag_record_{item['category']}",
                    "content": self._format_rag_record(item),
                    "type": "experience",
                    "structured": item
                })
    
        # 策略2：从知识库文件中检索
        kb_results = self.knowledge_base.search(query, top_k=3)
        for item in kb_results:
            results.append({
                "source": item.get("source", "knowledge_base"),
                "content": item.get("content", ""),
                "type": "knowledge"
            })
    
        if results:
            log_with_timestamp(self.name, "INFO", f"📚 共检索到 {len(results)} 条相关知识")
    
        return results
    
    def _format_rag_record(self, record: Dict) -> str:
        """格式化单条 RAG 记录为可读文本"""
        status = "✅ 成功" if record.get("success") else "❌ 失败"
        tool = record.get("tool", "unknown")
        input_str = json.dumps(record.get("input", {}), ensure_ascii=False)[:200]
    
        lines = [f"**{status}** | 工具: `{tool}`"]
        lines.append(f"参数: {input_str}")
    
        if record.get("success"):
            output = record.get("output", "")[:200]
            lines.append(f"结果: {output}")
        else:
            error = record.get("error", "")[:200]
            lines.append(f"错误: {error}")
    
        if record.get("time"):
            lines.append(f"时间: {record['time'][:16]}")
    
        return "\n".join(lines)
    def _build_system_prompt(self, user_query: str = "") -> str:
        """构建系统提示 - 动态包含相关记忆、知识和工具"""
        permanent_prompt = self.memory.get_permanent_prompt()
    
        # 检索相关长期记忆
        relevant_memories = []
        if user_query:
            relevant_memories = self._retrieve_relevant_memories(user_query)
            if relevant_memories:
                log_with_timestamp(self.name, "INFO", f"🧠 检索到 {len(relevant_memories)} 条相关记忆")
    
        # 检索相关 RAG 知识
        relevant_knowledge = []
        if user_query:
            relevant_knowledge = self._retrieve_relevant_knowledge(user_query)
            if relevant_knowledge:
                log_with_timestamp(self.name, "INFO", f"📚 检索到 {len(relevant_knowledge)} 条相关知识")
    
        # 获取工具摘要
        tools_info = self.tools.get_tools_summary() if self.tools and self.tools.list_tools() else ""
    
        # 构建记忆部分
        memory_section = ""
        if relevant_memories:
            memory_lines = ["## 相关记忆（用户之前告诉过你的信息）\n"]
            for mem in relevant_memories:
                memory_lines.append(f"- ID:{mem['id']} | [{mem['category']}] {mem['content']}")
            memory_section = "\n".join(memory_lines)
    
        # 构建知识库部分
        knowledge_section = ""
        if relevant_knowledge:
            knowledge_lines = ["## 相关经验与知识（请参考）\n"]
            knowledge_lines.append("**重要提示**：以下是历史成功经验和知识库内容，请参考它们来完成任务。")
            knowledge_lines.append("")
    
            for item in relevant_knowledge:
                if item.get("type") == "experience":
                    knowledge_lines.append(f"### 📝 历史经验")
                    knowledge_lines.append(f"{item['content']}")
                else:
                    knowledge_lines.append(f"### 📚 知识库: {item['source']}")
                    knowledge_lines.append(f"{item['content']}")
                knowledge_lines.append("")
    
            knowledge_section = "\n".join(knowledge_lines)
    
        return f"""{permanent_prompt}

    {memory_section}

    {knowledge_section}

    {tools_info}

    ## 你的能力
    你是 Creator Agent，专门负责内容生成。你的能力包括：
    1. 调用mcp server的工具完成生成型任务
    2. 3D建模 - 根据描述生成 GLB 格式的 3D 模型
    3. 网页搜索 - 搜索互联网信息
    4. 视频生成 - 根据描述生成视频
    5. 图像生成 - 根据描述生成图像

    ## 使用知识库的指引（重要）
    - 当上面的「相关知识库信息」中有内容时，**优先使用这些知识**回答用户问题
    - 知识库中的信息是经过验证的权威内容，不要自行编造替代
    - 如果知识库信息足以回答问题，直接引用并说明来源

    ## 使用工具和记忆的指引
    - 当用户要求你记住某事时，使用 add_to_my_memory 工具存储到长期记忆
    - 当用户询问之前的信息时，使用 search_my_memory 工具搜索记忆
    - 当用户要求查看记忆列表时，使用 view_my_memory 工具
    - 当用户要求忘记某事或删除记忆时，使用 delete_from_my_memory 工具
    ## 工具使用优先级
        1. **MCP 工具优先**：名称以 `mcp_` 开头的工具调用,如果存在能满
        足同一功能的多个mcp工具，那就询问用户优先使用哪个（并且将选择存入长期记忆）
        2. **本地工具备选**：如果 MCP 工具调用失败或不可用，再使用本地工具
    ## RAG 知识库自更新规则

    每次任务完成后，**必须**调用 `add_rag_record` 记录结果：

    ## 记录格式
    ```json
    {{
    "time": "当前时间",
    "tool": "工具名称",
    "input": {{"参数名": "参数值"}},
    "success": true/false,
    "output": "成功时的输出",
    "error": "失败时的错误信息"
    }}
    ## 文件传输
    - 如果用户提供了输入文件，它们会被放在输入目录中
    - 如果你生成了输出文件，请放到输出目录，并在回复中说明文件名

    ## 回复风格
    - 专业、友好、简洁
    - 使用知识库信息时，可以说"根据知识库..."
    - 使用记忆中的信息时，可以说"根据你之前提到的..."

    ## 当前时间
    {__import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    """
    
    def _get_conversation_context(self) -> List[Dict]:
        """获取对话上下文"""
        return self.memory.get_short_term_context()
    
    def _process_input_files(self, input_files: List[str]) -> List[Path]:
        """处理输入文件：从共享文件夹移动到本地输入目录"""
        local_files = []
        if not input_files:
            return local_files
        
        for filename in input_files:
            dest = self.file_transfer.receive_file(
                source_agent="conductor",
                filename=filename,
                target_dir=self.input_dir
            )
            if dest:
                local_files.append(dest)
                log_with_timestamp(self.name, "INFO", f"收到输入文件: {filename} -> {dest}")
            else:
                log_with_timestamp(self.name, "WARNING", f"未找到输入文件: {filename}")
        
        return local_files
    
    def _list_input_files(self) -> List[str]:
        """列出当前输入目录中的文件"""
        files = list(self.input_dir.glob("*"))
        return [f.name for f in files if f.is_file()]
    
    def _list_output_files(self) -> List[str]:
        """列出当前输出目录中的文件"""
        files = list(self.output_dir.glob("*"))
        return [f.name for f in files if f.is_file()]
    
    def handle_task(self, instruction: str, input_files: list = None) -> Dict[str, Any]:
        """
        处理自然语言任务 - 使用 LLM + 记忆检索 + RAG + Tools
        
        这是 Conductor 调用 Creator 的入口点。
        """
        log_with_timestamp(self.name, "INFO", f"📥 收到任务: {instruction[:100]}...")
        
        # 1. 处理输入文件
        local_files = self._process_input_files(input_files or [])
        
        # 2. 添加到短期记忆
        self.memory.add_short_term("user", instruction)
        
        # 如果有输入文件，也记录到记忆
        if local_files:
            file_info = f"用户提供了输入文件: {[f.name for f in local_files]}"
            self.memory.add_short_term("system", file_info)
        
        # 3. 构建消息
        messages = [
            {"role": "system", "content": self._build_system_prompt(instruction)}
        ]
        
        # 添加对话上下文
        context = self._get_conversation_context()
        messages.extend(context)
        
        # 添加输入文件信息（如果有）
        if local_files:
            file_list = "\n".join([f"- {f.name}" for f in local_files])
            messages.append({
                "role": "system",
                "content": f"用户上传了以下文件，你可以根据需要读取：\n{file_list}"
            })
        
        # 添加当前指令
        messages.append({"role": "user", "content": instruction})
        
        # 4. 调用 LLM
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools.get_schemas() if self.tools and self.tools.list_tools() else None,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=self.llm_config.max_tokens
            )
            
            message = response.choices[0].message
            
            # 处理工具调用
            if message.tool_calls:
                log_with_timestamp(self.name, "INFO", f"🔧 LLM 请求调用 {len(message.tool_calls)} 个工具")
                
                # 添加 assistant 消息
                assistant_msg = {
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
                }
                messages.append(assistant_msg)
                
                # 执行工具
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    
                    log_with_timestamp(self.name, "INFO", f"🔧 执行工具: {tool_name}")
                    result = self.tools.execute(tool_name, **tool_args)
                    
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "content": result
                    })
                
                # 再次调用 LLM 生成最终回复
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.llm_config.max_tokens
                )
                reply = final_response.choices[0].message.content or ""
            else:
                reply = message.content or ""
            
            # 5. 检查是否有输出文件
            output_files = self._list_output_files()
            
            result = {
                "status": "success",
                "message": reply,
                "capability_used": None,
                "output_files": output_files
            }
            
            log_with_timestamp(self.name, "INFO", f"📤 任务完成，输出文件: {output_files}")
            
        except Exception as e:
            log_with_timestamp(self.name, "ERROR", str(e), error=True)
            
            # 降级：使用简单模式
            result = self._simple_handle(instruction)
        
        # 6. 添加到短期记忆
        self.memory.add_short_term("assistant", result["message"])
        
        return result
    
    def _simple_handle(self, instruction: str) -> Dict[str, Any]:
        """简单模式（无 LLM 时的降级）"""
        instruction_lower = instruction.lower()
        
        if "自我介绍" in instruction_lower or "介绍" in instruction_lower:
            response = f"""✨ 你好！我是 Creator Agent，我的能力包括：

1. **视频生成** - 根据描述生成视频内容
2. **3D建模** - 生成 GLB 格式的 3D 模型
3. **网页搜索** - 搜索互联网信息

目前这些功能正在开发中，敬请期待！"""
        else:
            # 尝试从知识库检索
            knowledge = self.knowledge_base.search(instruction, top_k=1)
            if knowledge:
                response = f"根据知识库信息：\n\n{knowledge[0]['content']}\n\n（如需更详细的帮助，请等待功能完善）"
            else:
                response = f"⚠️ 收到任务：「{instruction}」\n\nCreator Agent 的功能正在开发中，暂时无法执行具体任务。"
        
        return {
            "status": "pending",
            "message": response,
            "capability_used": None,
            "output_files": self._list_output_files()
        }
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        tools_count = len(self.tools.list_tools()) if self.tools else 0
        return {
            "name": self.name,
            "display_name": self.display_name,
            "status": "active",
            "capabilities": self.capabilities,
            "memory_stats": self.memory.get_stats(),
            "rag_stats": self.knowledge_base.get_stats(),
            "tools_count": tools_count,
            "llm_provider": self.llm_config.provider,
            "llm_model": self.model,
            "input_files": self._list_input_files(),
            "output_files": self._list_output_files()
        }
    
    # ========== 记忆管理方法 ==========
    
    def delete_memory(self, memory_id: int) -> bool:
        """删除单条长期记忆"""
        return self.memory.delete_long_term(memory_id)
    
    def delete_memories_batch(self, ids: List[int]) -> int:
        """批量删除长期记忆"""
        return self.memory.delete_long_term_batch(ids)
    
    def clear_memory_by_category(self, category: str) -> int:
        """按分类清空长期记忆"""
        return self.memory.clear_long_term_by_category(category)
    
    def clear_all_memory(self) -> int:
        """清空所有长期记忆"""
        return self.memory.clear_long_term()
    
    def get_short_term_stats(self) -> dict:
        """获取短期记忆统计"""
        return self.memory.get_short_term_stats()
    
    def clear_short_term(self):
        """清空短期记忆"""
        self.memory.clear_short_term()
    
    # ========== RAG 管理方法 ==========
    
    def add_knowledge_document(self, content: str, filename: str = None) -> str:
        """添加知识文档"""
        return self.knowledge_base.add_document(content, filename)
    
    def search_knowledge(self, query: str) -> List[Dict]:
        """搜索知识库"""
        return self.knowledge_base.search(query)
    
    def get_all_knowledge_documents(self) -> List[Dict]:
        """获取所有知识文档"""
        return self.knowledge_base.get_all_documents()
    
    def get_knowledge_document_content(self, filename: str) -> Optional[str]:
        """获取知识文档内容"""
        return self.knowledge_base.get_document_content(filename)
    
    def delete_knowledge_document(self, filename: str) -> bool:
        """删除知识文档"""
        return self.knowledge_base.delete_document(filename)
    
    def get_knowledge_stats(self) -> dict:
        """获取知识库统计"""
        return self.knowledge_base.get_stats()
    
    def reload_knowledge(self):
        """重新加载知识库"""
        self.knowledge_base.reload()
    
    # ========== 文件管理方法 ==========
    
    def get_input_files(self) -> List[str]:
        """获取输入文件列表"""
        return self._list_input_files()
    
    def get_output_files(self) -> List[str]:
        """获取输出文件列表"""
        return self._list_output_files()
    
    def clear_input_files(self):
        """清空输入目录"""
        for f in self.input_dir.iterdir():
            if f.is_file():
                f.unlink()
        log_with_timestamp(self.name, "INFO", "输入目录已清空")
    
    def clear_output_files(self):
        """清空输出目录"""
        for f in self.output_dir.iterdir():
            if f.is_file():
                f.unlink()
        log_with_timestamp(self.name, "INFO", "输出目录已清空")


# 单例
_creator = None


def get_creator() -> CreatorAgent:
    global _creator
    if _creator is None:
        _creator = CreatorAgent()
    return _creator