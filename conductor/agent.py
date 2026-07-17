"""Conductor 核心逻辑 - ReAct异步任务系统（统一框架版，状态驱动）"""

import json
import yaml
import re
import asyncio
import threading
import concurrent.futures
from .rag import RAGManager
import numpy as np

# 在 __init__ 中，初始化 LLM 后

from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from openai import OpenAI
from .safety import safe_process, SAFETY_REJECT_MESSAGE, set_llm_func_for_safety
from .core.message_bus import get_message_bus, Message
from .core.file_transfer import get_file_transfer
from .memory.agent_memory import AgentMemory
from .memory.memory_store import MemoryStore
from .llm_config import get_llm_config
from .utils import log_with_timestamp
from .agent_registry import get_agent_registry
from shared.states import get_state_registry  # ✅ 新增：导入状态注册器
from shared.states.handlers.common import TaskStatus

# ========== 任务数据模型 ==========
#改为从公共模块导入


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
        self.isolated_memory: List[Dict[str, str]] = []
        self.final_result = None
        self.error = None

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


# ========== 提示词模板（保留） ==========

PROMPT_SUMMARIZE = """你是一个信息筛选助手。以下是用户最近完成的3个任务的摘要。

{summaries}

【当前新任务】
{instruction}

规则：
1. 只提取与当前任务直接相关的信息（用户偏好、常见做法、已知限制、参考案例）
2. 如果没有任何信息对当前任务有帮助，只返回"无"
3. 输出简洁，不超过150字
"""


# ========== ConductorAgent 主类 ==========

class ConductorAgent:
    def __init__(self, config_path: Optional[Path] = None):
        self.name = "conductor"

        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        self.config = self._load_config(config_path)
        self.sub_agents = self.config.get("sub_agents", [])
        self.registry = get_agent_registry()
        self.bus = get_message_bus()
        self.bus.subscribe(self.name, self._on_message)
        self.file_transfer = get_file_transfer()
        mysql_config = self.config.get("memory", {}).get("mysql", {})
        self.rag_manager = RAGManager(mysql_config)
        self.llm_config = get_llm_config()
        if not self.llm_config.validate():
            log_with_timestamp(self.name, "WARNING", "LLM API Key 未配置")

        self.client = OpenAI(**self.llm_config.get_openai_kwargs())
        self.model = self.llm_config.model
        self.temperature = self.llm_config.temperature
        set_llm_func_for_safety(self._call_llm_sync)

        # ========== 记忆系统 ==========
        memory_dir = Path(__file__).parent / "memory"
        self.memory = AgentMemory(self.name, memory_dir, self.config.get("memory", {}))
        self.store = MemoryStore(self.name, self.config.get("memory", {}))
        #embedding
        self.use_embedding = False
        if self.use_embedding:
            from sentence_transformers import SentenceTransformer

            self._embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        else:
            self._embedding_model = None
        # ========== 工具注册器 ==========
        from .tools import get_tool_registry, init_conductor_tools
        self.tools = get_tool_registry()
        init_conductor_tools()
        log_with_timestamp(self.name, "INFO", f"已注册 {len(self.tools.list_tools())} 个工具")

        # ========== ✅ 状态注册器（新增） ==========
        self.states = get_state_registry()
        self.states.init_mysql(mysql_config)
        state_count = self.states.load_states_for_agent(self.name)
        log_with_timestamp(self.name, "INFO", f"已加载 {state_count} 个状态")

        # ========== 任务管理 ==========
        self._tasks: Dict[str, Task] = {}
        self._user_tasks: Dict[str, List[str]] = {}
        self._task_counter = 0
        self._task_lock = threading.Lock()

        self.api_host = "localhost"
        self.api_port = 7860
        self.callback_base_url = f"http://{self.api_host}:{self.api_port}"
        self._process_callback = None

        log_with_timestamp(self.name, "INFO", f"Conductor 初始化完成（统一框架版）")
        log_with_timestamp(self.name, "INFO", f"回调地址: {self.callback_base_url}/api/callback")
        log_with_timestamp(self.name, "INFO", f"LLM: {self.llm_config.provider}/{self.model}")

    # ========== 过程消息回调 ==========

    def set_process_callback(self, callback):
        self._process_callback = callback
        log_with_timestamp(self.name, "INFO", "📡 过程消息回调已注册")

    def _emit_process(self, content: str, emoji: str = "🤔"):
        if self._process_callback:
            try:
                self._process_callback(content, emoji)
            except Exception as e:
                log_with_timestamp(self.name, "WARNING", f"过程回调失败: {e}")

    # ========== 基础方法 ==========

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
            "memory": {"summary_limit": 3}
        }

    def _on_message(self, message: Message):
        log_with_timestamp(self.name, "INFO", f"收到消息: {message.msg_type}")

    def _generate_task_id(self) -> str:
        import random
        import time
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = f"{random.randint(0, 65535):04x}"
        return f"task_{timestamp}_{random_suffix}"

    def _get_task(self, task_id: str) -> Optional[Task]:
        with self._task_lock:
            return self._tasks.get(task_id)

    def _update_task_status(self, task_id: str, status: TaskStatus):
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = status
                task.updated_at = datetime.now()

    # ========== 创建任务（保持不变） ==========

    def _create_task(self, user_id: str, instruction: str) -> Task:
        task_id = self._generate_task_id()

        is_safe, processed_instruction = safe_process(instruction)

        if not is_safe:
            log_with_timestamp(
                self.name,
                "WARNING",
                f"⚠️ 安全过滤拦截: 用户 {user_id} 的输入被拒绝"
            )
            task = Task(task_id, user_id, instruction)
            task.status = TaskStatus.FAILED
            task.error = processed_instruction
            task.final_result = processed_instruction
            task.completed_at = datetime.now()

            with self._task_lock:
                self._tasks[task_id] = task
                if user_id not in self._user_tasks:
                    self._user_tasks[user_id] = []
                self._user_tasks[user_id].append(task_id)

            self.store.save_task_memory(task.task_id, task.isolated_memory)
            self._emit_process(f"⚠️ 安全过滤拦截: 输入被拒绝", "⚠️")
            return task

        instruction = processed_instruction
        task = Task(task_id, user_id, instruction)

        recent_summaries = self.store.get_recent_summaries_sync(user_id, limit=3)
        long_term_info = self._search_long_term_memory(user_id, instruction, limit=10)
        useful_info = self._extract_useful_info_v2(
            recent_summaries=recent_summaries,
            long_term_memories=long_term_info,
            instruction=instruction
        )
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
            if user_id not in self._user_tasks:
                self._user_tasks[user_id] = []
            self._user_tasks[user_id].append(task_id)

        log_with_timestamp(
            self.name, "INFO",
            f"📋 任务创建: {task_id} (记忆: {len(task.isolated_memory)} 条)"
        )
        return task

    def _search_long_term_memory(self, user_id: str, instruction: str, limit: int = 10) -> List[Dict]:
        keywords = self._extract_keywords(instruction)
        results = []
        for keyword in keywords[:3]:
            results.extend(self.store.search_summaries(user_id, keyword, limit=limit//2))

        seen = set()
        unique_results = []
        for r in results:
            if r.get('task_id') not in seen:
                seen.add(r.get('task_id'))
                unique_results.append(r)

        return unique_results[:limit]

    def _extract_keywords(self, instruction: str) -> List[str]:
        words = instruction.replace('，', ' ').replace('、', ' ').split()
        return [w for w in words if len(w) > 1][:5]

    def _extract_useful_info_v2(
        self,
        recent_summaries: List[Dict],
        long_term_memories: List[Dict],
        instruction: str
    ) -> str:
        info_text = ""

        if recent_summaries:
            info_text += "【最近完成的任务】\n"
            for i, s in enumerate(recent_summaries, 1):
                info_text += f"任务{i}: {s.get('summary', '')[:300]}\n"
                if s.get('key_points'):
                    info_text += f"  关键点: {', '.join(s.get('key_points', [])[:3])}\n"

        if long_term_memories:
            info_text += "\n【长期记忆中的相关信息】\n"
            for i, m in enumerate(long_term_memories, 1):
                info_text += f"记忆{i}: {m.get('summary', '')[:300]}\n"
                if m.get('key_points'):
                    info_text += f"  关键点: {', '.join(m.get('key_points', [])[:3])}\n"

        if not info_text:
            return ""

        prompt = f"""你是一个信息筛选助手。以下是用户的历史记忆信息，请提取对当前任务有帮助的部分。

{info_text}

【当前任务】
{instruction}

规则：
1. 只提取与当前任务直接相关的信息
2. 相关包括：用户偏好、常见做法、已知限制、参考案例
3. 如果没有任何信息有帮助，返回"无"
4. 输出简洁，不超过200字
"""

        try:
            response = self._call_llm_sync(prompt, temperature=0.3)
            result = response.strip()
            if result == "无" or len(result) < 5:
                return ""
            return result
        except Exception as e:
            log_with_timestamp(self.name, "WARNING", f"历史信息提炼失败: {e}")
            return ""
 #rag===========
    def _get_rag_context(self, instruction: str) -> str:
        if self.use_embedding and self._embedding_model is not None:
            return self._get_rag_context_embedding(instruction)
        else:
            return self._get_rag_context_keyword(instruction)
        
    def _get_rag_embedding(self, instruction: str) -> str:
        try:
            print(f"[DEBUG] _get_rag_context 开始, instruction='{instruction[:50]}...'")
            
            categories = self.rag_manager.get_all_categories(self.name)
            if not categories:
                print("[DEBUG] 无分类 → 返回空字符串")
                return ""
            
            cat_names = [cat.category for cat in categories]
            print(f"[DEBUG] 分类列表: {cat_names}")

            print("[DEBUG] 开始编码分类...")
            cat_embs = self._embedding_model.encode(cat_names, convert_to_numpy=True)
            print(f"[DEBUG] 分类编码完成, shape: {cat_embs.shape}")
            
            print("[DEBUG] 开始编码指令...")
            inst_emb = self._embedding_model.encode(instruction, convert_to_numpy=True)
            print(f"[DEBUG] 指令编码完成, shape: {inst_emb.shape}")

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
            log_with_timestamp(self.name, "WARNING", f"RAG 检索失败: {e}")
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
            log_with_timestamp(self.name, "WARNING", f"RAG 检索失败: {e}")
            return ""

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
            log_with_timestamp(self.name, "WARNING", f"历史信息提炼失败: {e}")
            return ""

    def _call_llm_sync(self, prompt: str, temperature: float = 0.3) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=500
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
                max_tokens=600
            )

        with concurrent.futures.ThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(executor, _sync_call)
        return response.choices[0].message.content

    # ========== 提交任务 ==========

    def submit_task(self, user_id: str, instruction: str) -> str:
        task = self._create_task(user_id, instruction)
        log_with_timestamp(self.name, "INFO", f"📋 任务已提交: {task.task_id}")
        asyncio.create_task(self._execute_task(task.task_id))
        return task.task_id

    async def chat(self, user_input: str, user_id: str = "default") -> str:
        log_with_timestamp(self.name, "INFO", f"收到: {user_input[:50]}...")
        task = self._create_task(user_id, user_input)
        asyncio.create_task(self._execute_task(task.task_id))
        return f"✅ 任务已创建: {task.task_id}"

    # ========== 用户回复（保留特殊逻辑） ==========

    def reply_to_task(self, task_id: str, user_input: str) -> str:
        """
        处理用户对任务的回复
        
        Args:
            task_id: 任务ID
            user_input: 用户输入内容
        
        Returns:
            操作结果信息
        """
        import threading
        import asyncio
        import traceback
        
        task = self._get_task(task_id)
        if not task:
            return f"❌ 任务 {task_id} 不存在"

        if task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED]:
            return f"⚠️ 任务 {task_id} 状态为 {task.status.value}，无法继续"

        # ========== 确认词检测 ==========
        confirm_words = ["确认", "好的", "结束", "可以", "没问题", "就这样", "ok", "yes", "是", "完成", "行"]
        user_input_clean = user_input.strip().lower()
        
        is_pure_confirmation = False
        for word in confirm_words:
            if user_input_clean == word or user_input_clean.startswith(word):
                is_pure_confirmation = True
                break

        # ========== 确认词分支 ==========
        if is_pure_confirmation and task.status == TaskStatus.AWAITING_CONFIRMATION:
            log_with_timestamp(self.name, "INFO", f"✅ 检测到确认词，直接完成任务: {task_id}")
            
            if "complete" not in task.state_path:
                task.state_path.append("complete")
            
            # 直接执行完成（使用 asyncio.create_task，因为此时可能在事件循环中）
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._handle_complete(task, {"reasoning": "用户确认结束"}))
            except RuntimeError:
                # 如果没有运行中的事件循环，使用线程
                def _run_complete():
                    asyncio.run(self._handle_complete(task, {"reasoning": "用户确认结束"}))
                threading.Thread(target=_run_complete, daemon=True).start()
            
            return f"✅ 任务 {task_id} 已确认完成。\n\n结果：{task.final_result or '无结果'}"

        # ========== 非确认词：继续执行 ==========
        print(f"[DEBUG] 用户回复: {user_input[:50]}...")
        log_with_timestamp(self.name, "INFO", f"📝 用户回复: {user_input[:50]}...")
        
        # 追加用户回复到记忆
        task.isolated_memory.append({"role": "user", "content": user_input})
        
        # 重置迭代和等级
        task.iteration_count = 0
        task.level = 1
        self._update_task_status(task_id, TaskStatus.RUNNING)
        self._emit_process(f"📝 用户回复: {user_input[:50]}...", "📝")

        # ========== 启动 _execute_task（健壮版本） ==========
        def _run_task():
            try:
                print(f"[DEBUG] 线程启动，准备执行 _execute_task, task_id={task_id}")
                # 使用 asyncio.run 确保独立事件循环
                asyncio.run(self._execute_task(task_id))
                print(f"[DEBUG] 线程执行 _execute_task 完成, task_id={task_id}")
            except Exception as e:
                print(f"[DEBUG] 线程执行 _execute_task 异常: {e}")
                traceback.print_exc()
                log_with_timestamp(self.name, "ERROR", f"线程执行 _execute_task 异常: {e}", error=True)

        # 启动独立线程
        thread = threading.Thread(target=_run_task, daemon=True)
        thread.start()
        print(f"[DEBUG] 已启动线程执行 _execute_task, task_id={task_id}")

        return f"✅ 已收到回复，继续执行任务 {task_id}"
    # ========== 核心执行循环（修改：使用状态注册器） ==========

    async def _execute_task(self, task_id: str):
        print(f"[DEBUG] _execute_task 开始, task_id='{task_id}'")
        task = self._get_task(task_id)
        if not task:
            log_with_timestamp(self.name, "ERROR", f"任务不存在: {task_id}", error=True)
            return

        self._update_task_status(task_id, TaskStatus.RUNNING)
        self._emit_process(f"▶️ 执行任务: {task_id[:12]}...", "🚀")
        log_with_timestamp(self.name, "INFO", f"▶️ _execute_task 开始: {task_id}, 迭代: {task.iteration_count}")

        try:
            while task.iteration_count < task.max_iterations:
                task.iteration_count += 1
                log_with_timestamp(self.name, "INFO", f"🔄 迭代 {task.iteration_count}/{task.max_iterations}")

                if task.status == TaskStatus.CANCELLED:
                    self._emit_process("⏹️ 任务已取消", "⏹️")
                    break

                # 1. LLM 决策
                log_with_timestamp(self.name, "INFO", f"🧠 调用 _decide_next_state...")
                decision = await self._decide_next_state(task)

                log_with_timestamp(self.name, "INFO", f"📋 decision 返回: {decision}")

                if decision is None:
                    log_with_timestamp(self.name, "WARNING", "decision 为 None，继续下一轮迭代")
                    continue

                state_id = decision.get("state")
                data = decision.get("data", {})

                log_with_timestamp(self.name, "INFO", f"📋 选择状态: {state_id}")
                self._emit_process(f"📋 选择: {state_id}", "📋")

                # 2. 执行状态（使用动态路由）
                await self._execute_state(task, state_id, data)

                # 3. 检查是否应该结束循环
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.AWAITING_CONFIRMATION]:
                    log_with_timestamp(self.name, "INFO", f"⏹️ 任务状态变化: {task.status.value}，结束循环")
                    break

            if task.iteration_count >= task.max_iterations and task.status not in [TaskStatus.COMPLETED, TaskStatus.AWAITING_CONFIRMATION]:
                task.error = f"达到最大迭代次数 ({task.max_iterations})"
                self._update_task_status(task_id, TaskStatus.FAILED)

        except Exception as e:
            log_with_timestamp(self.name, "ERROR", f"任务执行异常: {task_id} - {e}", error=True)
            self._update_task_status(task_id, TaskStatus.FAILED)
            task.error = str(e)
            import traceback
            traceback.print_exc()

    async def _decide_next_state(self, task: Task) -> Optional[Dict[str, Any]]:
        """LLM 决定下一个状态（使用动态状态列表）"""
        memory_text = self._format_memory(task.isolated_memory)
        states_desc = self._build_states_description(task.level)

        user_prompt = f"""{memory_text}

{states_desc}

【任务要求】
请根据当前任务状态，从上述可用状态中选择最合适的下一步状态。

选择 reply 时：
1. 你是在直接回复用户
2. data 中必须包含 content 字段，内容是给用户的回复
3. 回复内容要自然、有用

只返回JSON，不要其他内容。"""

        system_prompt = """你是任务执行专家，负责决定任务的下一个状态。

规则：
1. 根据任务进度和用户意图选择状态
2. 如果需要调用子Agent，选择 call_agent，data 中包含 agent_name 和 instruction
3. 如果需要调用本地工具，选择 call_tool，data 中包含 tool_name 和 args
4. 如果需要回复用户，选择 reply，data 中必须包含 content
5. 如果用户确认结束，选择 complete

只返回JSON。"""

        try:
            content = await self._call_llm_async(system_prompt, user_prompt)
            log_with_timestamp(self.name, "INFO", f"LLM 原始响应: {content[:200]}...")
            return self._parse_json(content)
        except Exception as e:
            log_with_timestamp(self.name, "ERROR", f"LLM决策失败: {e}", error=True)
            return None

    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        if not content:
            return None

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        try:
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass

        log_with_timestamp(self.name, "WARNING", f"无法解析 JSON: {content[:100]}...")
        return None

    def _format_memory(self, memory: List[Dict]) -> str:
        lines = ["【任务完整上下文】"]
        for item in memory:
            role = item.get("role", "unknown")
            content = item.get("content", "")
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)

    # ✅ 修改：使用状态注册器动态构建状态描述
    def _build_states_description(self, level: int) -> str:
        """从状态注册器动态构建状态描述，按当前等级过滤"""
        states = self.states.get_agent_state_list(self.name, level)
        if not states:
            return "【可用状态】\n无可用状态"

        lines = ["【可用状态】"]
        for s in states:
            lines.append(f"- {s.state_id}: {s.description}")
        lines.append("")
        lines.append('{"state": "状态ID", "reasoning": "理由", "data": {...}}')
        return "\n".join(lines)

    # ========== ✅ 状态执行（使用动态路由） ==========

    async def _execute_state(self, task: Task, state_id: str, data: Dict):
        """执行状态（由状态注册器动态路由）"""
        state_info = self.states.get_state(state_id)
        if not state_info:
            log_with_timestamp(self.name, "WARNING", f"未知状态: {state_id}")
            return

        # 更新执行计数
        self.states.update_state_execution(state_id)

        task.state_path.append(state_id)
        try:
            await state_info.handler(self, task, data)
        except Exception as e:
            log_with_timestamp(self.name, "ERROR", f"状态执行异常 {state_id}: {e}", error=True)

    # ========== 状态处理器包装方法（供 reply_to_task 和动态路由调用） ==========

    async def _handle_complete(self, task: Task, data: Dict) -> Dict[str, Any]:
        """包装 complete 状态处理器，供 reply_to_task 调用"""
        from shared.states.handlers.complete import handle_complete
        return await handle_complete(self, task, data)

    # _handle_reply 不再需要单独存在，因为 _execute_state 会动态调用 shared.states.handlers.conductor_reply

    # ========== 任务存储（保留） ==========

    async def _save_task_memory(self, task: Task):
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

        log_with_timestamp(self.name, "INFO", f"💾 任务记忆已存储: {task.task_id}")

    async def _generate_task_summary(self, task: Task) -> Dict:
        memory_snippet = self._format_memory(task.isolated_memory[-10:])

        prompt = f"""请为以下任务生成摘要。

【任务指令】{task.instruction}
【执行结果】{task.final_result if task.final_result else "无"}
【执行记录摘要】{memory_snippet[:800]}

返回JSON格式：
{{
    "summary": "任务摘要（80-150字，概述做了什么、怎么做的、结果如何）",
    "key_points": ["关键点1", "关键点2", "关键点3"],
    "lessons_learned": "经验教训（如果有），否则为空字符串",
    "useful_tools_used": ["工具1", "工具2"],
    "tags": ["标签1", "标签2"],
    "importance_score": 0.5
}}"""

        try:
            response = await self._call_llm_async("生成任务摘要", prompt)
            result = self._parse_json(response)
            if result:
                return result
        except Exception as e:
            log_with_timestamp(self.name, "WARNING", f"摘要生成失败: {e}")

        return {
            "summary": f"任务: {task.instruction[:50]}... 结果: {task.final_result[:50] if task.final_result else '完成'}",
            "key_points": [],
            "lessons_learned": "",
            "useful_tools_used": [],
            "tags": [],
            "importance_score": 0.5
        }

    async def _generate_rag_experience_summary(self, task: Task) -> str:
        memory_snippet = self._format_memory(task.isolated_memory[-15:])

        prompt = f"""你是一个经验提炼专家。请从以下任务执行记录中提取工作经验。

【任务执行记录】
{memory_snippet}

【任务结果】
{task.final_result if task.final_result else "未明确记录"}

请生成一条工作经验总结，要求：
1. 包含：任务目标、执行方法（调用了什么/做了什么）、执行结果
2. 精简，不超过 80 字
3. 格式自然，便于后续检索参考

只输出总结内容，不要其他格式。"""

        try:
            response = await self._call_llm_async("生成工作经验", prompt)
            return response.strip()[:300]
        except Exception as e:
            log_with_timestamp(self.name, "WARNING", f"工作经验生成失败: {e}")
            return f"任务: {task.instruction[:50]}... 结果: {task.final_result[:50] if task.final_result else '完成'}"

    async def _save_rag_experience(self, task: Task):
        try:
            experience_summary = await self._generate_rag_experience_summary(task)

            category = self.rag_manager.classify_category(
                agent_name=self.name,
                instruction=task.instruction,
                summary=experience_summary,
                llm_call_func=self._call_llm_sync
            )

            state_path_str = "→".join(task.state_path) if task.state_path else "created→completed"

            from .rag import RAGExperience

            exp = RAGExperience(
                task_id=task.task_id,
                user_id=task.user_id,
                instruction=task.instruction,
                summary=experience_summary,
                state_path=state_path_str,
                key_steps="[]",
                result_preview=task.final_result[:500] if task.final_result else "",
                success=task.status == TaskStatus.COMPLETED,
                time_cost=int((task.completed_at - task.created_at).total_seconds())
            )

            saved_category = self.rag_manager.save_experience(self.name, exp)
            log_with_timestamp(self.name, "INFO", f"📚 RAG 经验已保存: {saved_category}")

        except Exception as e:
            log_with_timestamp(self.name, "WARNING", f"RAG 经验生成失败: {e}")

    # ========== 任务查询和取消 ==========

    def get_task_summary(self, task_id: str) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return {"error": f"任务 {task_id} 不存在"}
        return task.to_dict()

    def get_user_tasks(self, user_id: str) -> List[Task]:
        with self._task_lock:
            task_ids = self._user_tasks.get(user_id, [])
            return [self._tasks[tid] for tid in task_ids if tid in self._tasks]

    async def cancel_task(self, task_id: str, reason: str = "user_cancelled") -> bool:
        task = self._get_task(task_id)
        if not task:
            return False
        if task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
            return False
        self._update_task_status(task_id, TaskStatus.CANCELLED)
        log_with_timestamp(self.name, "INFO", f"⏹️ 任务已取消: {task_id}")
        self._emit_process(f"⏹️ 任务已取消: {reason}", "⏹️")
        return True


# ========== 单例 ==========

_conductor = None


def get_conductor() -> ConductorAgent:
    global _conductor
    if _conductor is None:
        _conductor = ConductorAgent()
    return _conductor