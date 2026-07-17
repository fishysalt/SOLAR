"""Creator Agent - 常规Agent，ReAct异步任务系统（统一框架版，数据库驱动工具）"""

import json
import yaml
import sys
import asyncio
import threading
import concurrent.futures
import re

import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from openai import OpenAI
from shared.states import get_state_registry
sys.path.insert(0, str(Path(__file__).parent.parent))
# 新的工具调用模式（数据库驱动）
from shared.tools import get_tool_registry, ToolInfo, ToolType
from .core.file_transfer import get_file_transfer
from .memory.agent_memory import AgentMemory
from creator.llm_config import get_llm_config
from .memory.memory_store import MemoryStore
from .rag import RAGManager
from .rag import RAGExperience
from .utils import (
    log_with_timestamp as log,
    log_process,
    is_task_cancelled,
    mark_task_cancelled,
    clear_cancelled_task,
    send_callback
)
from .rag.knowledge_base import KnowledgeBase


# ========== 任务数据模型 ==========
from shared.states.handlers.common import TaskStatus

class Task:
    """主任务 - 所有信息存储在 isolated_memory 中"""
    def __init__(self, task_id: str, user_id: str, instruction: str):
        self.task_id = task_id
        self.user_id = user_id
        self.instruction = instruction
        self.status = TaskStatus.CREATED
        self.level: int = 1
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.completed_at = None
        self.iteration_count = 0
        self.max_iterations = 20
        self.state_path: List[str] = []
        
        # ========== 唯一信息存储 ==========
        self.isolated_memory: List[Dict[str, str]] = []
        
        # 最终结果
        self.final_result = None
        self.error = None
        
        # ========== 回调信息 ==========
        self.subtask_id: str = ""
        self.callback_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "instruction": self.instruction[:100],
            "status": self.status.value,
            "level": self.level,
            "final_result": self.final_result[:500] if self.final_result else None,
            "error": self.error[:200] if self.error else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "iteration": self.iteration_count,
            "memory_count": len(self.isolated_memory)
        }


# ========== 提示词模板 ==========

PROMPT_SUMMARIZE = """你是一个信息筛选助手。以下是用户最近完成的3个任务的摘要。

{summaries}

【当前新任务】
{instruction}

规则：
1. 只提取与当前任务直接相关的信息（用户偏好、常见做法、已知限制、参考案例）
2. 如果没有任何信息对当前任务有帮助，只返回"无"
3. 输出简洁，不超过150字
"""


# ========== CreatorAgent 主类 ==========

class CreatorAgent:
    def __init__(self):
        self.name = "creator"
        self.display_name = "✨ Creator"

        # 文件通道
        self.file_transfer = get_file_transfer()

        # ========== 1. LLM 配置 ==========
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
                    max_tokens=800
                )
                return response.choices[0].message.content
            except Exception as e:
                log(self.name, "WARNING", f"摘要生成失败: {e}")
                return None

        # ========== 2. 加载配置 ==========
        config_path = Path(__file__).parent / "config.yaml"
        self.config = self._load_config(config_path)

        # ========== 3. RAG 知识库 ==========
        rag_dir = Path(__file__).parent / "rag"
        self.knowledge_base = KnowledgeBase(rag_dir)
        #embedding
        self.use_embedding = False
        if self.use_embedding:
            from sentence_transformers import SentenceTransformer

            self._embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        else:
            self._embedding_model = None
        # ========== 4. 记忆系统 ==========
        memory_dir = Path(__file__).parent / "memory"
        self.memory = AgentMemory(
            self.name, 
            memory_dir, 
            self.config.get("memory", {}), 
            llm_callback=llm_summary_callback
        )

        # ========== 5. 记忆存储层 ==========
        self.store = MemoryStore(self.name, self.config.get("memory", {}))

        # ========== 6. RAG 管理器 ==========
        mysql_config = self.config.get("memory", {}).get("mysql", {})
        self.rag_manager = RAGManager(mysql_config)

        # ========== 7. 工具注册器 ==========
        self.tools = get_tool_registry()
        self.tools.init_mysql(mysql_config)
        self.states = get_state_registry()
        #状态注册
        # 在 __init__ 中，初始化 tools 后
        self.states = get_state_registry()
        self.states.init_mysql(mysql_config)
        state_count = self.states.load_states_for_agent(self.name)
        log(self.name, "INFO", f"已加载 {state_count} 个状态")
        # ========== 从数据库加载属于本 Agent 的所有工具 ==========
        loaded_count = self.tools.load_tools_for_agent(self.name)
        log(self.name, "INFO", f"已从数据库加载 {loaded_count} 个工具")

        # ========== 8. 数据目录 ==========
        self.input_dir = Path(__file__).parent / "data" / "input"
        self.output_dir = Path(__file__).parent / "data" / "output"
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # ========== 9. 任务管理 ==========
        self._tasks: Dict[str, Task] = {}
        self._task_lock = threading.Lock()

        # ========== 10. 过程消息回调 ==========
        self._process_callback = None

        log(self.name, "INFO", f"初始化完成（统一框架版）")
        log(self.name, "INFO", f"记忆目录: {memory_dir}")
        log(self.name, "INFO", f"RAG 文档数: {self.knowledge_base.get_stats()['document_count']}")
        log(self.name, "INFO", f"LLM: {self.llm_config.provider}/{self.model}")
        log(self.name, "INFO", f"已注册 {len(self.tools.list_tools(self.name))} 个工具（本Agent）")

    # ========== 配置加载 ==========

    def _load_config(self, config_path: Path) -> dict:
        if not config_path.exists():
            return self._get_default_config()
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _get_default_config(self) -> dict:
        return {
            "name": "creator",
            "memory": {
                "summary_limit": 3,
                "short_term_window": 30,
                "redis": {
                    "host": "localhost",
                    "port": 6379,
                    "db": 0
                },
                "mysql": {
                    "host": "localhost",
                    "port": 3306,
                    "database": "solar_ma",
                    "user": "root",
                    "password": ""
                }
            }
        }

    # ========== 过程消息回调 ==========

    def set_process_callback(self, callback):
        self._process_callback = callback
        log(self.name, "INFO", "📡 过程消息回调已注册")

    def _emit_process(self, content: str, emoji: str = "✨"):
        log_process(self.name, content, emoji)
        if self._process_callback:
            try:
                self._process_callback(content, emoji)
            except Exception as e:
                log(self.name, "WARNING", f"过程回调失败: {e}")

    # ========== 任务管理 ==========

    def _generate_task_id(self) -> str:
        import random
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = f"{random.randint(0, 65535):04x}"
        return f"crt_task_{timestamp}_{random_suffix}"

    def _get_task(self, task_id: str) -> Optional[Task]:
        with self._task_lock:
            return self._tasks.get(task_id)

    def _update_task_status(self, task_id: str, status: TaskStatus):
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = status
                task.updated_at = datetime.now()

    # ========== 创建任务 ==========

    def _create_task(self, user_id: str, instruction: str) -> Task:
        task_id = self._generate_task_id()
        task = Task(task_id, user_id, instruction)

        # 1. 获取最近3个任务摘要
        recent_summaries = self.store.get_recent_summaries_sync(user_id, limit=3)

        # 2. LLM 筛选有用信息
        useful_info = self._extract_useful_info(recent_summaries, instruction)

        # 3. 获取 RAG 经验上下文
        rag_context = self._get_rag_context(instruction)

        # 4. 初始化 isolated_memory
        permanent_prompt = self.memory.get_permanent_prompt()
        task.isolated_memory = [
            {"role": "system", "content": permanent_prompt},
            {"role": "system", "content": useful_info if useful_info else "无历史参考信息"},
            {"role": "system", "content": rag_context if rag_context else "无历史经验参考"},
            {"role": "user", "content": instruction}
        ]

        # 5. 存储到Redis
        self.store.save_task_memory(task.task_id, task.isolated_memory)

        with self._task_lock:
            self._tasks[task_id] = task

        log(self.name, "INFO", f"📋 任务创建: {task_id} (记忆: {len(task.isolated_memory)} 条)")
        return task

    def _create_task_with_id(self, task_id: str, user_id: str, instruction: str) -> Task:
        """使用指定task_id创建任务（供handle_task调用）"""
        task = Task(task_id, user_id, instruction)

        recent_summaries = self.store.get_recent_summaries_sync(user_id, limit=3)
        useful_info = self._extract_useful_info(recent_summaries, instruction)
        rag_context = self._get_rag_context(instruction)

        permanent_prompt = self.memory.get_permanent_prompt()
        task.isolated_memory = [
            {"role": "system", "content": permanent_prompt},
            {"role": "system", "content": useful_info if useful_info else "无历史参考信息"},
            {"role": "system", "content": rag_context if rag_context else "无历史经验参考"},
            {"role": "user", "content": instruction}
        ]

        self.store.save_task_memory(task.task_id, task.isolated_memory)

        with self._task_lock:
            self._tasks[task_id] = task

        log(self.name, "INFO", f"📋 任务创建: {task_id}")
        return task

    def _extract_useful_info(self, summaries: List[Dict], instruction: str) -> str:
        if not summaries:
            return ""

        summary_text = ""
        for i, s in enumerate(summaries, 1):
            summary_text += f"\n任务{i}: {s.get('summary', '')[:300]}"
            if s.get('key_points'):
                summary_text += f"\n  关键点: {', '.join(s.get('key_points', [])[:3])}"

        prompt = PROMPT_SUMMARIZE.format(
            summaries=summary_text,
            instruction=instruction
        )

        try:
            response = self._call_llm_sync(prompt, temperature=0.3)
            result = response.strip()
            if result == "无" or len(result) < 5:
                return ""
            return result
        except Exception as e:
            log(self.name, "WARNING", f"历史信息提炼失败: {e}")
            return ""

    def _extract_keywords(self, instruction: str) -> List[str]:
        words = instruction.replace('，', ' ').replace('、', ' ').split()
        return [w for w in words if len(w) > 1][:5]
#rag========
    def _get_rag_context(self, instruction: str) -> str:
        if self.use_embedding and self._embedding_model is not None:
            return self._get_rag_context_embedding(instruction)
        else:
            return self._get_rag_context_keyword(instruction)
    def _get_rag_embedding(self, instruction: str) -> str:
        try:
            print(f"[DEBUG] _get_rag_context 开始, instruction='{instruction[:50]}...'")
            
            # 获取所有分类
            categories = self.rag_manager.get_all_categories(self.name)
            if not categories:
                print("[DEBUG] 无分类 → 返回空字符串")
                return ""
            
            cat_names = [cat.category for cat in categories]
            print(f"[DEBUG] 分类列表: {cat_names}")

            # 编码分类和指令
            print("[DEBUG] 开始编码分类...")
            cat_embs = self._embedding_model.encode(cat_names, convert_to_numpy=True)
            print(f"[DEBUG] 分类编码完成, shape: {cat_embs.shape}")
            
            print("[DEBUG] 开始编码指令...")
            inst_emb = self._embedding_model.encode(instruction, convert_to_numpy=True)
            print(f"[DEBUG] 指令编码完成, shape: {inst_emb.shape}")

            # 计算余弦相似度
            print("[DEBUG] 计算余弦相似度...")
            sim = np.dot(cat_embs, inst_emb) / (np.linalg.norm(cat_embs, axis=1) * np.linalg.norm(inst_emb))
            best_idx = np.argmax(sim)
            max_sim = sim[best_idx]
            
            print(f"[DEBUG] 最高相似度: {max_sim:.4f}, 对应分类: '{cat_names[best_idx]}'")
            
            threshold = 0.25  # 可调
            if max_sim < threshold:
                print(f"[DEBUG] 相似度 {max_sim:.4f} < 阈值 {threshold} → 无匹配，返回空字符串")
                return ""

            matched_category = cat_names[best_idx]
            print(f"[DEBUG] 匹配成功: '{matched_category}'")

            # 检索经验
            print(f"[DEBUG] 开始检索分类 '{matched_category}' 的经验...")
            experiences = self.rag_manager.get_experiences(
                agent_name=self.name,
                category=matched_category,
                user_id=None,
                limit=5
            )
            if not experiences:
                print(f"[DEBUG] 分类 '{matched_category}' 下无经验 → 返回空字符串")
                return ""
            
            print(f"[DEBUG] 获取到 {len(experiences)} 条经验")

            # 构建返回内容
            lines = ["【历史工作经验参考】"]
            from datetime import datetime
            for idx, exp in enumerate(experiences):
                created_at = exp.get('created_at')
                if isinstance(created_at, datetime):
                    created_at_str = created_at.strftime("%Y-%m-%d %H:%M")
                else:
                    created_at_str = str(created_at)[:16] if created_at else ""
                summary = exp.get('summary', '')[:150] if exp.get('summary') else ""
                lines.append(f"- [{created_at_str}] {summary}")
                print(f"[DEBUG] 经验 {idx+1}: {created_at_str} - {summary[:30]}...")

            result = "\n".join(lines)
            print(f"[DEBUG] 成功构建上下文，长度 {len(result)} 字符")
            return result

        except Exception as e:
            print(f"[DEBUG] 异常: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            log(self.name, "WARNING", f"RAG 检索失败: {e}")
            return ""

    def _get_rag_context_keyword(self, instruction: str) -> str:
        # 原有的关键词匹配实现（从旧版恢复）
        try:
            keywords = self._extract_keywords(instruction)
            categories = self.rag_manager.get_all_categories(self.name)
            if not categories:
                return ""

            matched_category = None
            for cat in categories:
                for kw in keywords:
                    if kw.lower() in cat.category.lower():
                        matched_category = cat.category
                        break
                if matched_category:
                    break

            if not matched_category:
                matched_category = categories[0].category if categories else ""

            experiences = self.rag_manager.get_experiences(
                agent_name=self.name,
                category=matched_category,
                user_id=None,
                limit=5
            )

            if not experiences:
                return ""

            lines = ["【历史工作经验参考】"]
            for exp in experiences:
                created_at = exp.get('created_at')
                if isinstance(created_at, datetime):
                    created_at_str = created_at.strftime("%Y-%m-%d %H:%M")
                else:
                    created_at_str = str(created_at)[:16] if created_at else ""
                summary = exp.get('summary', '')[:150] if exp.get('summary') else ""
                lines.append(f"- [{created_at_str}] {summary}")

            return "\n".join(lines)

        except Exception as e:
            log(self.name, "WARNING", f"RAG 检索失败: {e}")
            return ""

    def _call_llm_sync(self, prompt: str, temperature: float = 0.3) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=1000
        )
        return response.choices[0].message.content

    async def _call_llm_async(self, system_prompt: str, user_prompt: str) -> str:
        def _sync_call():
            return self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )

        with concurrent.futures.ThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(executor, _sync_call)
        return response.choices[0].message.content

    # ========== 提交任务（UI调试） ==========

    def submit_task(self, user_id: str, instruction: str) -> str:
        task = self._create_task(user_id, instruction)
        log(self.name, "INFO", f"📋 任务已提交: {task.task_id}")
        asyncio.create_task(self._execute_task(task.task_id))
        return task.task_id

    # ========== 核心：处理任务（creator调用） ==========

    async def handle_task(
        self,
        instruction: str,
        input_files: list = None,
        task_id: str = None,
        subtask_id: str = "",
        callback_url: str = None,
        user_id: str = "default"
    ) -> Dict[str, Any]:
        if not task_id:
            task_id = self._generate_task_id()
            log(self.name, "INFO", f"📥 收到任务（无task_id，自动生成）: {instruction[:50]}...")
        else:
            log(self.name, "INFO", f"📥 收到任务: {task_id} | {instruction[:50]}...")

        if is_task_cancelled(task_id):
            log(self.name, "INFO", f"⏹️ 任务 {task_id} 已被取消，跳过执行")
            return {
                "status": "cancelled",
                "message": f"任务 {task_id} 已被取消",
                "task_id": task_id
            }

        before_files = set(self._list_output_files())
        local_files = self._process_input_files(input_files or [])

        task = self._create_task_with_id(task_id, user_id, instruction)
        task.subtask_id = subtask_id
        task.callback_url = callback_url

        self.memory.add_short_term("user", instruction)
        if local_files:
            file_info = f"用户提供了输入文件: {[f.name for f in local_files]}"
            self.memory.add_short_term("system", file_info)

        self._emit_process(f"▶️ 开始执行任务: {task_id[:12]}...", "🚀")
        self._update_task_status(task_id, TaskStatus.RUNNING)

        result = await self._execute_task(task_id)

        after_files = set(self._list_output_files())
        new_files = list(after_files - before_files)

        if result.get("status") == "success":
            result["output_files"] = new_files
        result["task_id"] = task_id

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

    # ========== 核心执行循环 ==========

    async def _execute_task(self, task_id: str) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return {"status": "error", "error": f"任务不存在: {task_id}"}

        self._update_task_status(task_id, TaskStatus.RUNNING)
        self._emit_process(f"▶️ 执行任务: {task_id[:12]}...", "🚀")

        try:
            while task.iteration_count < task.max_iterations:
                task.iteration_count += 1

                if task.status == TaskStatus.CANCELLED:
                    self._emit_process("⏹️ 任务已取消", "⏹️")
                    return {"status": "cancelled", "message": "任务被取消"}

                # 1. LLM 决策
                decision = await self._decide_next_state(task)
                if decision is None:
                    task.error = "无法解析LLM决策"
                    self._update_task_status(task_id, TaskStatus.FAILED)
                    return {"status": "failed", "error": task.error}

                state_id = decision.get("state")
                data = decision.get("data", {})

                log(self.name, "INFO", f"📋 选择状态: {state_id}")
                self._emit_process(f"📋 选择: {state_id}", "📋")

                # 2. 执行状态
                result = await self._execute_state(task, state_id, data)

                # 3. 如果状态执行返回了结果（reply或fail），直接返回
                if result is not None:
                    return result

                # 4. 检查是否应该结束循环
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    break

            # 达到最大迭代次数
            if task.iteration_count >= task.max_iterations and task.status != TaskStatus.COMPLETED:
                task.error = f"达到最大迭代次数 ({task.max_iterations})"
                self._update_task_status(task_id, TaskStatus.FAILED)
                return {"status": "failed", "error": task.error}

        except Exception as e:
            log(self.name, "ERROR", f"任务执行异常: {task_id} - {e}", error=True)
            self._update_task_status(task_id, TaskStatus.FAILED)
            task.error = str(e)
            return {"status": "failed", "error": str(e)}

        # 如果循环结束但没有返回结果（理论上不会发生）
        return {"status": "failed", "error": "任务执行结束但未返回结果"}

    async def _decide_next_state(self, task: Task) -> Optional[Dict[str, Any]]:
        memory_text = self._format_memory(task.isolated_memory)
        states_desc = self._build_states_description(task.level)  # 动态生成状态列表

        user_prompt = f"""{memory_text}

    {states_desc}

    请根据当前任务状态，从上述可用状态中选择最合适的下一步状态。只返回JSON。"""

        system_prompt = r"""你是任务执行专家，负责决定任务的下一个状态。

通用规则：
- 根据当前任务上下文和提供的可用状态列表，选择最合适的下一步状态。
- 如果调用工具（call_tool）且结果需要保存到本地，默认输出目录为 "E:\Agents\SOLAR_MA\creator\data\output"。
- 如果任务完成并返回链接（reply），请确保返回完整的链接，包括所有权限参数（如 expired=xxx）。
- 只返回JSON，不要附加其他文字。"""

        try:
            tools_schemas = self.tools.get_schemas(self.name) if self.tools else None
            
            def _sync_call():
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    tools=tools_schemas,
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=1000
                )
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(executor, _sync_call)
            
            message = response.choices[0].message
            content = message.content
            if not content:
                log(self.name, "WARNING", f"LLM 返回空内容，响应对象: {message}")
                # 可以返回一个默认的 fail 状态，避免任务卡死
                return {"state": "fail", "data": {"error": "LLM 返回空响应，请重试"}}
            log(self.name, "INFO", f"LLM 原始响应: {content[:2000]}...")
            return self._parse_json(content)
            
        except Exception as e:
            log(self.name, "ERROR", f"LLM决策失败: {e}", error=True)
            return None
    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        if not content:
            print("LLM返回内容为空")
            return None
        # 去除可能的 Markdown 代码块
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        # 尝试提取第一个完整 JSON 对象
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError as e:
                log(self.name, "WARNING", f"JSON 解析失败: {e}\n内容片段: {content[start:end][:2000]}")
        return None

    def _format_memory(self, memory: List[Dict]) -> str:
        lines = ["【任务完整上下文】"]
        for item in memory:
            role = item.get("role", "unknown")
            content = item.get("content", "")
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)

    def _build_states_description(self, level: int) -> str:
        """从状态注册器动态构建状态描述"""
        states = self.states.get_agent_state_list(self.name, level)
        if not states:
            return "【可用状态】\n无可用状态"

        lines = ["【可用状态】"]
        for s in states:
            lines.append(f"- {s.state_id}: {s.description}")
        lines.append("")
        lines.append('{"state": "状态ID", "reasoning": "理由", "data": {...}}')
        lines.append("")
        return "\n".join(lines)

    # ========== 状态执行 ==========

    async def _execute_state(self, task: Task, state_id: str, data: Dict) -> Optional[Dict[str, Any]]:
        """执行状态（由状态注册器动态路由）"""
        state_info = self.states.get_state(state_id)
        if not state_info:
            log(self.name, "WARNING", f"未找到匹配状态: {state_id}")
            # 尝试获取 fail 状态
            fail_state = self.states.get_state("fail")
            if fail_state:
                return await fail_state.handler(self, task, {"error": f"未知状态: {state_id}"})
            else:
                return {"status": "failed", "error": f"未知状态: {state_id}"}

        # 更新执行计数
        self.states.update_state_execution(state_id)

        task.state_path.append(state_id)
        try:
            result = await state_info.handler(self, task, data)
            if state_info.is_final and result is not None:
                return result
            return result
        except Exception as e:
            log(self.name, "ERROR", f"状态执行异常 {state_id}: {e}", error=True)
            fail_state = self.states.get_state("fail")
            if fail_state:
                return await fail_state.handler(self, task, {"error": f"状态执行失败: {str(e)}"})
            else:
                return {"status": "failed", "error": f"状态执行失败: {str(e)}"}
    async def _fallback_fail(self, task: Task, data: Dict) -> Dict[str, Any]:
        """紧急失败处理（不经过状态机）"""
        error = data.get("error", "状态执行出现错误（选择状态后执行时出现错误）")
        task.error = error
        task.completed_at = datetime.now()
        self._update_task_status(task.task_id, TaskStatus.FAILED)
        return await self._finalize_task(task, success=False, error=error)

    # ========== 状态处理器 ==========
    #已迭代为状态注册器动态路由，不再需要单独定义
    # ========== 统一回传方法 ==========

    async def _finalize_task(self, task: Task, success: bool, message: str = None, error: str = None) -> Dict[str, Any]:
        """
        统一任务完结方法
        
        1. 更新任务状态
        2. 存储任务记忆到MySQL（完整版 + 摘要版）
        3. 存储RAG工作经验
        4. 清理Redis
        5. 发送过程消息
        6. 返回结果
        """
        # 1. 更新状态
        if success:
            self._update_task_status(task.task_id, TaskStatus.COMPLETED)
            self._emit_process(f"✅ 任务完成: {message[:50] if message else '无结果'}...", "✅")
            log(self.name, "INFO", f"✅ 任务完成: {task.task_id}")
        else:
            self._update_task_status(task.task_id, TaskStatus.FAILED)
            self._emit_process(f"❌ 任务失败: {error[:50] if error else '未知错误'}", "❌")
            log(self.name, "WARNING", f"❌ 任务失败: {task.task_id} - {error}")

        # 2. 存储任务记忆到MySQL
        await self._save_task_memory(task)

        # 3. 存储RAG工作经验
        await self._save_rag_experience(task)

        # 4. 清理Redis
        self.store.delete_task_memory(task.task_id)

        # 5. 返回结果
        if success:
            return {
                "status": "success",
                "message": message or "任务完成",
                "output_files": self._list_output_files(),
                "task_id": task.task_id
            }
        else:
            return {
                "status": "failed",
                "error": error or "未知错误",
                "task_id": task.task_id
            }

    # ========== 任务存储 ==========

    async def _save_task_memory(self, task: Task):
        """存储任务记忆到MySQL（完整版 + 摘要版）"""
        # 完整版
        self.store.save_raw_memory(
            task_id=task.task_id,
            user_id=task.user_id,
            instruction=task.instruction,
            final_result=task.final_result,
            isolated_memory=task.isolated_memory,
            subtasks=[],
            duration=(task.completed_at - task.created_at).total_seconds(),
            iteration_count=task.iteration_count,
            completed_at=task.completed_at
        )

        # 摘要版
        summary_data = await self._generate_task_summary(task)
        self.store.save_summary_memory(
            task_id=task.task_id,
            user_id=task.user_id,
            summary=summary_data.get("summary", ""),
            key_points=summary_data.get("key_points", []),
            lessons_learned=summary_data.get("lessons_learned", ""),
            useful_tools_used=summary_data.get("useful_tools_used", []),
            instruction_preview=task.instruction[:200],
            result_preview=task.final_result[:200] if task.final_result else "",
            tags=summary_data.get("tags", []),
            importance_score=summary_data.get("importance_score", 0.5),
            completed_at=task.completed_at
        )

        log(self.name, "INFO", f"💾 任务记忆已存储: {task.task_id}")

    async def _generate_task_summary(self, task: Task) -> Dict:
        """LLM 生成任务摘要"""
        memory_snippet = self._format_memory(task.isolated_memory[-10:])

        prompt = f"""请为以下任务生成摘要。

【任务指令】{task.instruction}
【执行结果】{task.final_result if task.final_result else "无"}
【执行记录摘要】{memory_snippet[:800]}

返回JSON格式：
{{
    "summary": "任务摘要（80-150字）",
    "key_points": ["关键点1", "关键点2", "关键点3"],
    "lessons_learned": "",
    "useful_tools_used": [],
    "tags": [],
    "importance_score": 0.5
}}"""

        try:
            response = await self._call_llm_async("生成任务摘要", prompt)
            result = self._parse_json(response)
            if result:
                return result
        except Exception as e:
            log(self.name, "WARNING", f"摘要生成失败: {e}")

        return {
            "summary": f"任务: {task.instruction[:50]}... 结果: {task.final_result[:50] if task.final_result else '完成'}",
            "key_points": [],
            "lessons_learned": "",
            "useful_tools_used": [],
            "tags": [],
            "importance_score": 0.5
        }

    # ========== RAG 工作经验 ==========

    async def _generate_rag_experience_summary(self, task: Task) -> str:
        memory_snippet = self._format_memory(task.isolated_memory[-15:])

        prompt = f"""你是一个经验提炼专家。请从以下任务执行记录中提取工作经验。

【任务执行记录】
{memory_snippet}

【任务结果】
{task.final_result if task.final_result else "未明确记录"}

请生成一条工作经验总结，要求：
1. 包含：任务目标、执行方法、执行结果
2. 精简，不超过80字
3. 格式自然

只输出总结内容，不要其他格式。"""

        try:
            response = await self._call_llm_async("生成工作经验", prompt)
            return response.strip()[:300]
        except Exception as e:
            log(self.name, "WARNING", f"工作经验生成失败: {e}")
            return f"任务: {task.instruction[:50]}... 结果: {task.final_result[:50] if task.final_result else '完成'}"

    async def _save_rag_experience(self, task: Task):
        try:
            experience_summary = await self._generate_rag_experience_summary(task)

            # 1. 先分类
            category = self.rag_manager.classify_category(
                agent_name=self.name,
                instruction=task.instruction,
                summary=experience_summary,
                llm_call_func=self._call_llm_sync
            )

            state_path_str = "→".join(task.state_path) if task.state_path else "created→completed"

            # 2. 构建经验对象（包含 category）
            exp = RAGExperience(
                task_id=task.task_id,
                user_id=task.user_id,
                instruction=task.instruction,
                summary=experience_summary,
                state_path=state_path_str,
                key_steps="[]",
                result_preview=task.final_result[:500] if task.final_result else "",
                success=task.status == TaskStatus.COMPLETED,
                time_cost=int((task.completed_at - task.created_at).total_seconds()),
                category=category  # ← 传入分类
            )

            # 3. 保存
            self.rag_manager.save_experience(self.name, exp)  # save_experience 内部使用 exp.category

            log(self.name, "INFO", f"📚 RAG 经验已保存: {category}")

        except Exception as e:
            log(self.name, "WARNING", f"RAG 经验生成失败: {e}")

    def _process_input_files(self, input_files: List[str]) -> List[Path]:
        local_files = []
        if not input_files:
            return local_files

        for filename in input_files:
            dest = self.file_transfer.receive_file(
                source_agent="creator",
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

    # ========== 取消任务 ==========

    def cancel_task(self, task_id: str) -> bool:
        mark_task_cancelled(task_id)

        task = self._get_task(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now()
            log(self.name, "INFO", f"⏹️ 任务已取消: {task_id}")

        return True

    # ========== 任务查询 ==========

    def get_all_tasks(self) -> List[Task]:
        with self._task_lock:
            return list(self._tasks.values())

    def get_task_summary(self, task_id: str) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return {"error": f"任务 {task_id} 不存在"}
        return task.to_dict()

    # ========== 兼容旧接口 ==========

    def get_status(self) -> Dict[str, Any]:
        tools_count = len(self.tools.list_tools(self.name)) if self.tools else 0
        return {
            "name": self.name,
            "display_name": self.display_name,
            "status": "active",
            "capabilities": ["video_generation", "model_generation", "web_search"],
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

_creator = None


def get_creator() -> CreatorAgent:
    global _creator
    if _creator is None:
        _creator = CreatorAgent()
    return _creator