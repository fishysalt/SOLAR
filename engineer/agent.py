"""engineer Agent - ReAct异步任务系统（自进化引擎）"""

import json
import sys
import asyncio
import threading
import concurrent.futures
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))

from conductor.core.file_transfer import get_file_transfer
from conductor.memory.agent_memory import AgentMemory
from conductor.llm_config import get_llm_config
from conductor.utils import log_with_timestamp

from .models import Task, TaskStatus, SubtaskStatus, SubTask, CancelRequest
from .utils import (
    log_with_timestamp as log,
    log_process,
    is_task_cancelled,
    mark_task_cancelled,
    clear_cancelled_task,
    send_callback
)
from .rag.knowledge_base import KnowledgeBase


class EngineerAgent:
    """engineer Agent - 自进化引擎，ReAct异步任务系统"""

    def __init__(self):
        self.name = "engineer"
        self.display_name = "🔧 Engineer"

        # 文件通道
        self.file_transfer = get_file_transfer()

        # 记忆系统
        memory_dir = Path(__file__).parent / "memory"
        
        # RAG 知识库
        rag_dir = Path(__file__).parent / "rag"
        self.knowledge_base = KnowledgeBase(rag_dir)

        # LLM 配置
        self.llm_config = get_llm_config()
        if not self.llm_config.validate():
            log(self.name, "WARNING", "LLM API Key 未配置")

        self.client = OpenAI(**self.llm_config.get_openai_kwargs())
        self.model = self.llm_config.model
        self.temperature = self.llm_config.temperature

        # LLM 摘要回调
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
                log(self.name, "WARNING", f"摘要生成失败: {e}")
                return None

        self.memory = AgentMemory(self.name, memory_dir, llm_callback=llm_summary_callback)

        # 调试：输出记忆路径
        print(f"🔍 [DEBUG] Engineer 记忆目录: {memory_dir}")
        permanent_file = memory_dir / "permanent.yaml"
        print(f"🔍 [DEBUG] Engineer permanent.yaml 是否存在: {permanent_file.exists()}")
        if permanent_file.exists():
            try:
                with open(permanent_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    print(f"🔍 [DEBUG] Engineer permanent.yaml 内容长度: {len(content)} 字符")
            except:
                pass
        test_prompt = self.memory.get_permanent_prompt()
        print(f"🔍 [DEBUG] Engineer get_permanent_prompt() 长度: {len(test_prompt)} 字符")

        # 工具注册器
        from .tools import get_tool_registry, init_engineer_tools
        self.tools = get_tool_registry()
        init_engineer_tools()

        # ========== 数据目录 ==========
        self.input_dir = Path(__file__).parent / "data" / "input"
        self.output_dir = Path(__file__).parent / "data" / "output"
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # ========== 任务管理 ==========
        self._tasks: Dict[str, Task] = {}
        self._task_lock = threading.Lock()
        self._task_counter = 0

        # ========== 过程消息回调（调试用） ==========
        self._process_callback = None

        log(self.name, "INFO", f"初始化完成（ReAct异步任务系统）")
        log(self.name, "INFO", f"记忆目录: {memory_dir}")
        log(self.name, "INFO", f"RAG 文档数: {self.knowledge_base.get_stats()['document_count']}")
        log(self.name, "INFO", f"LLM: {self.llm_config.provider}/{self.model}")
        log(self.name, "INFO", f"已注册 {len(self.tools.list_tools())} 个工具")

    # ========== 过程消息回调 ==========

    def set_process_callback(self, callback):
        """设置过程消息回调（调试用）"""
        self._process_callback = callback
        log(self.name, "INFO", "📡 过程消息回调已注册")

    def _emit_process(self, content: str, emoji: str = "🔧"):
        """发送过程消息"""
        log_process(self.name, content, emoji)
        if self._process_callback:
            try:
                self._process_callback(content, emoji)
            except Exception as e:
                log(self.name, "WARNING", f"过程回调失败: {e}")

    # ========== 任务管理 ==========

    def _generate_task_id(self) -> str:
        with self._task_lock:
            self._task_counter += 1
            return f"eng_task_{self._task_counter:06d}"

    def _get_task(self, task_id: str) -> Optional[Task]:
        with self._task_lock:
            return self._tasks.get(task_id)

    def _update_task_status(self, task_id: str, status: TaskStatus):
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = status
                task.updated_at = datetime.now()

    def _create_task_with_id(self, task_id: str, user_id: str, instruction: str) -> Task:
        """
        使用指定的task_id创建任务（由Conductor传入或UI生成）
        初始化任务独立记忆
        """
        task = Task(task_id=task_id, user_id=user_id, instruction=instruction)

        # ========== 初始化任务独立记忆 ==========
        try:
            permanent_prompt = self.memory.get_permanent_prompt()
            all_messages = self.memory.short_term.get_messages()
            recent_messages = all_messages[-5:] if len(all_messages) > 5 else all_messages

            isolated = [
                {"role": "system", "content": permanent_prompt},
                {"role": "system", "content": "【以下是你执行任务时可以参考的最近对话上下文】"}
            ]

            for msg in recent_messages:
                content = msg.get("content", "")
                if len(content) > 500:
                    content = content[:500] + "..."
                isolated.append({
                    "role": msg.get("role", "user"),
                    "content": content
                })

            isolated.append({"role": "user", "content": instruction})
            task.isolated_memory = isolated

            log(self.name, "INFO", f"📋 任务独立记忆初始化: {len(isolated)} 条")

        except Exception as e:
            log(self.name, "WARNING", f"独立记忆初始化失败: {e}")
            task.isolated_memory = [
                {"role": "system", "content": self.memory.get_permanent_prompt()},
                {"role": "user", "content": instruction}
            ]

        with self._task_lock:
            self._tasks[task_id] = task

        return task

    # ========== 任务提交入口（供UI调用） ==========

    def submit_task(self, user_id: str, instruction: str) -> str:
        """
        提交任务 - UI调用入口（同步方法）
        
        与 Conductor.submit_task 保持一致的设计：
        - 同步方法，立即返回 task_id
        - 内部启动后台异步任务
        """
        # 生成 task_id
        with self._task_lock:
            self._task_counter += 1
            task_id = f"eng_task_{self._task_counter:06d}"
        
        # 创建任务
        task = self._create_task_with_id(task_id, user_id, instruction)
        task.callback_url = None  # UI 调用不需要回调
        
        log(self.name, "INFO", f"📋 任务已提交: {task_id} (用户: {user_id})")
        
        # 启动后台执行（不阻塞）
        asyncio.create_task(self._execute_task(task_id))
        
        return task_id

    # ========== 核心：处理任务（供Conductor调用） ==========

    async def handle_task(
        self,
        instruction: str,
        input_files: list = None,
        task_id: str = None,
        subtask_id: str = "",
        callback_url: str = None,
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """
        处理任务 - 由Conductor通过HTTP调用
        
        与 submit_task 的区别：
        - 使用 Conductor 传入的 task_id
        - 任务完成后发送回调
        """
        # 如果没有task_id，使用UI方式（兼容旧调用）
        if not task_id:
            task_id = self._generate_task_id()
            log(self.name, "INFO", f"📥 收到任务（无task_id，自动生成）: {instruction[:50]}...")
        else:
            log(self.name, "INFO", f"📥 收到任务: {task_id} | {instruction[:50]}...")

        # 检查是否已被取消
        if is_task_cancelled(task_id):
            log(self.name, "INFO", f"⏹️ 任务 {task_id} 已被取消，跳过执行")
            return {
                "status": "cancelled",
                "message": f"任务 {task_id} 已被取消",
                "task_id": task_id
            }

        # 记录开始前的文件
        before_files = set(self._list_output_files())

        # 处理输入文件
        local_files = self._process_input_files(input_files or [])

        # 创建任务
        task = self._create_task_with_id(task_id, user_id, instruction)
        task.subtask_id = subtask_id
        task.callback_url = callback_url

        # 添加到短期记忆
        self.memory.add_short_term("user", instruction)
        if local_files:
            file_info = f"用户提供了输入文件: {[f.name for f in local_files]}"
            self.memory.add_short_term("system", file_info)

        # ========== 执行任务（ReAct循环） ==========
        self._emit_process(f"▶️ 开始执行任务: {task_id[:12]}...", "🚀")
        self._update_task_status(task_id, TaskStatus.RUNNING)

        result = await self._execute_task(task_id)

        # 检查新文件
        after_files = set(self._list_output_files())
        new_files = list(after_files - before_files)

        if result.get("status") == "success":
            result["output_files"] = new_files
        result["task_id"] = task_id

        # 添加到短期记忆
        self.memory.add_short_term("assistant", result.get("message", ""))

        # ========== 发送回调 ==========
        if callback_url and task_id:
            status = result.get("status", "error")
            if status == "success":
                await send_callback(
                    callback_url=callback_url,
                    task_id=task_id,
                    subtask_id=subtask_id,
                    status="completed",
                    result=result.get("message", "任务完成"),
                    output_files=new_files
                )
            elif status == "cancelled":
                await send_callback(
                    callback_url=callback_url,
                    task_id=task_id,
                    subtask_id=subtask_id,
                    status="cancelled",
                    error="用户取消"
                )
            else:
                await send_callback(
                    callback_url=callback_url,
                    task_id=task_id,
                    subtask_id=subtask_id,
                    status="failed",
                    error=result.get("error", "未知错误")
                )

            clear_cancelled_task(task_id)

        log(self.name, "INFO", f"📤 任务完成: {result.get('status')}")
        return result

    # ========== ReAct 核心循环 ==========

    async def _execute_task(self, task_id: str) -> Dict[str, Any]:
        """ReAct循环执行任务"""
        task = self._get_task(task_id)
        if not task:
            return {"status": "error", "error": f"任务不存在: {task_id}"}

        try:
            while task.iteration_count < task.max_iterations:
                task.iteration_count += 1
                self._emit_process(f"🔄 迭代 {task.iteration_count}/{task.max_iterations}")

                # 检查取消
                if is_task_cancelled(task_id):
                    self._emit_process("⏹️ 任务已取消", "⏹️")
                    return {"status": "cancelled", "message": "任务被取消"}

                try:
                    self._emit_process("🧠 思考中...", "🧠")
                    decision = await self._decide_next_action(task)

                    if decision is None:
                        return {"status": "error", "error": "无法解析LLM决策"}

                    action = decision.get("action", "unknown")

                    # 发送决策消息
                    if action == "reply":
                        content = decision.get("content", "")[:80]
                        self._emit_process(f"📋 决策: 直接回复 → {content}...", "💬")
                    elif action == "call_tool":
                        tool = decision.get("tool_name", "unknown")
                        self._emit_process(f"📋 决策: 调用工具 {tool}", "🔧")
                    elif action == "finish":
                        result = decision.get("result", "")[:50]
                        self._emit_process(f"📋 决策: 任务完成 ✅ → {result}", "✅")
                    elif action == "fail":
                        reason = decision.get("reason", "")[:50]
                        self._emit_process(f"📋 决策: 任务失败 ❌ → {reason}", "❌")
                    else:
                        self._emit_process(f"📋 决策: {action}", "📋")

                except Exception as e:
                    log(self.name, "ERROR", f"LLM决策异常: {e}", error=True)
                    return {"status": "error", "error": f"LLM决策异常: {str(e)}"}

                # ========== 处理决策 ==========
                action = decision.get("action")

                if action == "finish":
                    if not task.final_result:
                        task.final_result = decision.get("result", "任务已完成")
                    self._update_task_status(task_id, TaskStatus.COMPLETED)
                    task.completed_at = datetime.now()
                    self._emit_process(f"✅ 任务完成: {task.final_result[:50]}...", "✅")
                    return {"status": "success", "message": task.final_result}

                if action == "fail":
                    task.error = decision.get("reason", "LLM决定终止任务")
                    self._update_task_status(task_id, TaskStatus.FAILED)
                    self._emit_process(f"❌ 任务失败: {task.error[:50]}", "❌")
                    return {"status": "error", "error": task.error}

                if action == "reply":
                    reply = decision.get("content", "已处理")
                    self._record_step(task, "reply", decision, reply)
                    if not task.final_result:
                        task.final_result = reply
                    self.memory.add_short_term("assistant", reply)
                    continue

                if action == "call_tool":
                    tool_name = decision.get("tool_name")
                    tool_args = decision.get("args", {})

                    if not tool_name:
                        task.error = "缺少tool_name"
                        self._update_task_status(task_id, TaskStatus.FAILED)
                        return {"status": "error", "error": task.error}

                    # 创建子任务记录
                    subtask_id = f"{task_id}_sub_{len(task.subtasks)+1:03d}"
                    subtask = SubTask(
                        id=subtask_id,
                        tool_name=tool_name,
                        instruction=json.dumps(tool_args)[:200]
                    )
                    task.subtasks.append(subtask)

                    # 执行工具
                    subtask.status = SubtaskStatus.RUNNING
                    subtask.started_at = datetime.now()
                    self._emit_process(f"🔧 执行工具: {tool_name}", "🔧")

                    try:
                        result = self.tools.execute(tool_name, **tool_args)
                        subtask.status = SubtaskStatus.COMPLETED
                        subtask.result = result
                        subtask.completed_at = datetime.now()
                        self._emit_process(f"✅ 工具 {tool_name} 执行完成", "✅")
                    except Exception as e:
                        subtask.status = SubtaskStatus.FAILED
                        subtask.error = str(e)
                        subtask.completed_at = datetime.now()
                        self._emit_process(f"❌ 工具 {tool_name} 失败: {str(e)[:50]}", "❌")

                    task.updated_at = datetime.now()
                    continue

                # 未知action
                task.error = f"未知操作: {action}"
                self._update_task_status(task_id, TaskStatus.FAILED)
                return {"status": "error", "error": task.error}

            # 达到最大迭代次数
            task.error = f"达到最大迭代次数 ({task.max_iterations})"
            self._update_task_status(task_id, TaskStatus.FAILED)
            return {"status": "error", "error": task.error}

        except Exception as e:
            log(self.name, "ERROR", f"任务执行异常: {task_id} - {e}", error=True)
            return {"status": "error", "error": str(e)}

    # ========== LLM 决策 ==========

    async def _decide_next_action(self, task: Task) -> Optional[Dict[str, Any]]:
        """LLM决定下一步行动"""
        prompt = self._build_react_prompt(task)

        # 提取固定记忆
        permanent_prompt = ""
        for msg in task.isolated_memory:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if len(content) > 100 and "【" not in content and "】" not in content:
                    permanent_prompt = content
                    break

        if not permanent_prompt:
            permanent_prompt = self.memory.get_permanent_prompt()

        # 获取可用工具列表
        tools_summary = self.tools.get_tools_summary() if self.tools.list_tools() else "暂无可用工具"

        def _sync_llm_call():
            return self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"""{permanent_prompt}

你是一个工程师Agent，负责执行任务。你可以调用工具来完成工作。

可用工具：
{tools_summary}

可用操作：
1. call_tool: 调用工具执行任务
2. reply: 直接回复用户（不需要调用工具）
3. finish: 任务已完成
4. fail: 任务无法继续

规则：
- 如果任务很简单，可以直接reply完成
- 如果需要工具帮助，使用call_tool
- 每次只做一件事
- 完成后用finish结束
- 只返回JSON格式的决策"""},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=600
            )

        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(executor, _sync_llm_call)

            content = response.choices[0].message.content
            return self._parse_decision(content)

        except Exception as e:
            log(self.name, "ERROR", f"LLM决策失败: {e}", error=True)
            return {"action": "fail", "reason": f"LLM调用失败: {str(e)}"}

    def _build_react_prompt(self, task: Task) -> str:
        """构建ReAct决策提示 - 使用任务独立记忆"""
        # 提取上下文
        context_lines = []
        for msg in task.isolated_memory:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                if "【" in content and "】" in content:
                    context_lines.append(f"[上下文] {content}")
            elif role == "user":
                if content != task.instruction:
                    context_lines.append(f"用户: {content[:100]}")
            elif role == "assistant":
                context_lines.append(f"助手: {content[:100]}")

        context_str = "\n".join(context_lines[-3:]) if context_lines else "无历史上下文"

        # 历史步骤
        history = ""
        for step in task.reasoning_history[-5:]:
            history += f"\n步骤 {step['step']}:\n"
            history += f"  思考: {step.get('reasoning', '')}\n"
            history += f"  执行: {step.get('action_display', '')}\n"
            if step.get('result'):
                history += f"  结果: {str(step['result'])[:100]}\n"

        # 子任务状态
        subtask_status = ""
        for st in task.subtasks:
            status_icon = {
                SubtaskStatus.PENDING: "⏳",
                SubtaskStatus.RUNNING: "▶️",
                SubtaskStatus.WAITING: "⏳",
                SubtaskStatus.COMPLETED: "✅",
                SubtaskStatus.FAILED: "❌",
                SubtaskStatus.CANCELLED: "⏹️"
            }.get(st.status, "❓")
            subtask_status += f"\n- {status_icon} {st.tool_name}: {st.instruction[:50]}"
            if st.result:
                subtask_status += f" → {str(st.result)[:50]}"

        return f"""【任务】
{task.instruction}

【历史上下文】
{context_str}

【已完成步骤】
{history or "还没有完成任何步骤"}

【工具执行记录】
{subtask_status or "还没有调用工具"}

【当前状态】
- 迭代次数: {task.iteration_count}/{task.max_iterations}
- 任务状态: {task.status.value}

【决策规则】
1. 如果任务已经完成 → action: finish
2. 如果任务无法继续 → action: fail
3. 如果不需要调用工具，直接回复用户 → action: reply
4. 如果需要调用工具 → action: call_tool

【返回格式】
只返回JSON，不要有其他内容。

示例1（调用工具）:
{{"action": "call_tool", "tool_name": "diagnose_error", "args": {{"error_id": "err_001"}}, "reasoning": "需要诊断错误"}}

示例2（直接回复）:
{{"action": "reply", "content": "好的，我来帮你处理这个任务。", "reasoning": "任务简单，不需要调用工具"}}

示例3（任务完成）:
{{"action": "finish", "result": "错误已修复完成", "reasoning": "所有步骤已完成"}}

示例4（任务失败）:
{{"action": "fail", "reason": "无法找到对应的工具", "reasoning": "所需工具不存在"}}"""

    def _parse_decision(self, content: str) -> Optional[Dict[str, Any]]:
        """解析LLM返回的决策"""
        try:
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except json.JSONDecodeError as e:
            log(self.name, "WARNING", f"JSON解析失败: {e}")

        return {"action": "reply", "content": content[:200], "reasoning": "无法解析为结构化决策"}

    def _record_step(self, task: Task, action: str, decision: Dict, result: Any = None):
        """记录ReAct步骤"""
        task.reasoning_history.append({
            "step": len(task.reasoning_history) + 1,
            "action": action,
            "action_display": decision.get("tool_name", action) if action == "call_tool" else action,
            "reasoning": decision.get("reasoning", ""),
            "result": result
        })

    # ========== 取消任务 ==========

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        mark_task_cancelled(task_id)

        task = self._get_task(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now()
            log(self.name, "INFO", f"⏹️ 任务已取消: {task_id}")

        return True

    # ========== 原有方法 ==========

    def _process_input_files(self, input_files: List[str]) -> List[Path]:
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
                log(self.name, "INFO", f"收到输入文件: {filename} -> {dest}")
            else:
                log(self.name, "WARNING", f"未找到输入文件: {filename}")

        return local_files

    def _list_input_files(self) -> List[str]:
        files = list(self.input_dir.glob("*"))
        return [f.name for f in files if f.is_file()]

    def _list_output_files(self) -> List[str]:
        files = list(self.output_dir.glob("*"))
        return [f.name for f in files if f.is_file()]

    # ========== 兼容旧接口 ==========

    def get_status(self) -> Dict[str, Any]:
        tools_count = len(self.tools.list_tools()) if self.tools else 0
        return {
            "name": self.name,
            "display_name": self.display_name,
            "status": "active",
            "capabilities": ["error_diagnosis", "tool_generation", "code_repair"],
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
        return self.memory.delete_long_term(memory_id)

    def delete_memories_batch(self, ids: List[int]) -> int:
        return self.memory.delete_long_term_batch(ids)

    def clear_memory_by_category(self, category: str) -> int:
        return self.memory.clear_long_term_by_category(category)

    def clear_all_memory(self) -> int:
        return self.memory.clear_long_term()

    def get_short_term_stats(self) -> dict:
        return self.memory.get_short_term_stats()

    def clear_short_term(self):
        self.memory.clear_short_term()

    # ========== RAG 管理方法 ==========

    def add_knowledge_document(self, content: str, filename: str = None) -> str:
        return self.knowledge_base.add_document(content, filename)

    def search_knowledge(self, query: str) -> List[Dict]:
        return self.knowledge_base.search(query)

    def get_all_knowledge_documents(self) -> List[Dict]:
        return self.knowledge_base.get_all_documents()

    def get_knowledge_document_content(self, filename: str) -> Optional[str]:
        return self.knowledge_base.get_document_content(filename)

    def delete_knowledge_document(self, filename: str) -> bool:
        return self.knowledge_base.delete_document(filename)

    def get_knowledge_stats(self) -> dict:
        return self.knowledge_base.get_stats()

    def reload_knowledge(self):
        self.knowledge_base.reload()

    # ========== 文件管理方法 ==========

    def get_input_files(self) -> List[str]:
        return self._list_input_files()

    def get_output_files(self) -> List[str]:
        return self._list_output_files()

    def clear_input_files(self):
        for f in self.input_dir.iterdir():
            if f.is_file():
                f.unlink()
        log(self.name, "INFO", "输入目录已清空")

    def clear_output_files(self):
        for f in self.output_dir.iterdir():
            if f.is_file():
                f.unlink()
        log(self.name, "INFO", "输出目录已清空")


# ========== 单例 ==========

_engineer = None


def get_engineer() -> EngineerAgent:
    global _engineer
    if _engineer is None:
        _engineer = EngineerAgent()
    return _engineer