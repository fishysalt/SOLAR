"""Agent 记忆管理 - 三类记忆（适配新版存储层）"""

import json
import yaml
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import sqlite3

from .memory_store import MemoryStore


class ShortTermMemory:
    """短期记忆 - 滑动窗口 + LLM 自动摘要（适配Redis存储）"""
    
    def __init__(self, agent_name: str, store: MemoryStore, max_messages: int = 30, llm_callback=None):
        self.agent_name = agent_name
        self.store = store
        self.max_messages = max_messages
        self._llm_callback = llm_callback
        self._current_user_id = "default"
        self._current_session_id = "default"
    
    def set_user(self, user_id: str, session_id: str = "default"):
        """设置当前用户（用于Redis key）"""
        self._current_user_id = user_id
        self._current_session_id = session_id
    
    def add(self, role: str, content: str):
        """添加消息到短期记忆（Redis）"""
        messages = self.get_messages()
        messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # 检查是否需要压缩
        if len(messages) > self.max_messages:
            messages = self._compress(messages)
        
        # 存储到Redis
        self._save_messages(messages)
    
    def get_messages(self) -> List[Dict]:
        """获取所有消息"""
        key = self._short_term_key()
        data = self.store.redis_client.get(key)
        if data:
            return json.loads(data)
        return []
    
    def get_context(self) -> List[Dict]:
        """获取上下文（用于LLM）"""
        messages = self.get_messages()
        # 返回最近的消息，适配旧接口
        return messages
    
    def _short_term_key(self) -> str:
        return f"{self.agent_name}:memory:short:{self._current_user_id}:{self._current_session_id}"
    
    def _save_messages(self, messages: List[Dict]):
        """保存消息到Redis"""
        key = self._short_term_key()
        self.store.redis_client.setex(
            key,
            24 * 3600,  # 24小时
            json.dumps(messages, ensure_ascii=False)
        )
    
    def _compress(self, messages: List[Dict]) -> List[Dict]:
        """压缩消息（保留最近一半 + 摘要）"""
        if not self._llm_callback:
            # 没有LLM回调，简单截断
            return messages[-self.max_messages // 2:]
        
        try:
            # 生成摘要
            messages_to_summarize = messages[:-self.max_messages // 2]
            conversation_text = "\n".join([
                f"{m['role']}: {m['content']}" for m in messages_to_summarize
            ])
            summary = self._llm_callback(f"请总结以下对话：\n{conversation_text}")
            
            # 保留摘要 + 最近消息
            result = [
                {"role": "system", "content": f"[摘要] {summary}"}
            ]
            result.extend(messages[-self.max_messages // 2:])
            return result
        except Exception as e:
            print(f"压缩失败: {e}")
            return messages[-self.max_messages // 2:]
    
    def clear(self):
        """清空短期记忆"""
        self.store.redis_client.delete(self._short_term_key())


class LongTermMemory:
    """长期记忆 - 适配MySQL存储（兼容旧接口）"""
    
    def __init__(self, agent_name: str, store: MemoryStore, memory_dir: Path):
        self.agent_name = agent_name
        self.store = store
        self._current_user_id = "default"
    
    def set_user(self, user_id: str):
        self._current_user_id = user_id
    
    def add(self, content: str, category: str = "general", importance: float = 0.5, metadata: dict = None):
        """添加长期记忆（直接写入MySQL）"""
        # 这里我们只添加摘要类型，用于兼容旧接口
        # 实际的长期记忆现在通过任务摘要存储
        return self.store.save_summary_memory(
            task_id=f"manual_{datetime.now().timestamp()}",
            user_id=self._current_user_id,
            summary=content,
            key_points=[],
            lessons_learned="",
            useful_tools_used=[],
            instruction_preview=content[:200],
            result_preview="",
            tags=[category],
            importance_score=importance,
            completed_at=datetime.now()
        )
    
    def search(self, keyword: str = None, category: str = None, limit: int = 10) -> List[Dict]:
        """搜索长期记忆"""
        if keyword:
            return self.store.search_summaries(self._current_user_id, keyword, limit)
        else:
            return self.store.get_recent_summaries(self._current_user_id, limit)
    
    def get_all(self, limit: int = 50) -> List[Dict]:
        """获取所有长期记忆"""
        return self.store.get_recent_summaries(self._current_user_id, limit)
    
    def delete(self, memory_id: int) -> bool:
        """删除长期记忆"""
        # 通过id删除需要额外查询，简化处理
        return False
    
    def get_stats(self) -> dict:
        return self.store.get_stats()


class PermanentMemory:
    """固定记忆 - 从YAML文件加载（不变）"""
    
    def __init__(self, agent_name: str, memory_dir: Path):
        self.agent_name = agent_name
        self._lock = threading.Lock()
        self.config_path = memory_dir / "permanent.yaml"
        self._data = self._load()
    
    def _load(self) -> dict:
        if not self.config_path.exists():
            return self._get_default()
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    def _get_default(self) -> dict:
        default = {
            "identity": f"你是 {self.agent_name}，一个智能助手。",
            "capabilities": "暂无能力描述",
            "response_style": "简洁、专业",
            "communication_protocol": "使用自然语言与用户交流"
        }
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default, f, allow_unicode=True)
        return default
    
    def reload(self):
        with self._lock:
            self._data = self._load()
    
    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)
    
    def get_prompt(self) -> str:
        with self._lock:
            parts = []
            if self._data.get("identity"):
                parts.append(self._data["identity"])
            if self._data.get("capabilities"):
                parts.append(f"\n## 能力\n{self._data['capabilities']}")
            if self._data.get("response_style"):
                parts.append(f"\n## 回复风格\n{self._data['response_style']}")
            if self._data.get("communication_protocol"):
                parts.append(f"\n## 通信协议\n{self._data['communication_protocol']}")
            return "\n".join(parts)


class AgentMemory:
    """Agent 记忆管理器（适配新版存储层）"""
    
    def __init__(self, agent_name: str, memory_dir: Path, config: Dict = None, llm_callback=None):
        self.agent_name = agent_name
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # 存储层
        self.store = MemoryStore(agent_name, config or {})
        
        # 固定记忆（YAML，不变）
        self.permanent = PermanentMemory(agent_name, self.memory_dir)
        
        # 短期记忆（适配Redis）
        self.short_term = ShortTermMemory(
            agent_name, 
            self.store,
            max_messages=30,
            llm_callback=llm_callback
        )
        
        # 长期记忆（适配MySQL）
        self.long_term = LongTermMemory(agent_name, self.store, self.memory_dir)
        
        self._llm_callback = llm_callback
    
    def set_user(self, user_id: str, session_id: str = "default"):
        """设置当前用户"""
        self.short_term.set_user(user_id, session_id)
        self.long_term.set_user(user_id)
    
    # ========== 短期记忆接口 ==========
    
    def add_short_term(self, role: str, content: str):
        self.short_term.add(role, content)
    
    def get_short_term_context(self) -> List[Dict]:
        return self.short_term.get_context()
    
    def get_short_term_messages(self) -> List[Dict]:
        return self.short_term.get_messages()
    
    def clear_short_term(self):
        self.short_term.clear()
    
    # ========== 长期记忆接口 ==========
    
    def add_long_term(self, content: str, category: str = "general", importance: float = 0.5) -> int:
        return self.long_term.add(content, category, importance)
    
    def search_long_term(self, keyword: str = None, category: str = None, limit: int = 10) -> List[Dict]:
        return self.long_term.search(keyword, category, limit)
    
    def get_long_term_all(self, limit: int = 50) -> List[Dict]:
        return self.long_term.get_all(limit)
    
    def delete_long_term(self, memory_id: int) -> bool:
        return self.long_term.delete(memory_id)
    
    def delete_long_term_batch(self, ids: List[int]) -> int:
        count = 0
        for mid in ids:
            if self.delete_long_term(mid):
                count += 1
        return count
    
    def clear_long_term(self) -> int:
        return 0  # MySQL删除全部
    
    # ========== 固定记忆接口 ==========
    
    def get_permanent_prompt(self) -> str:
        return self.permanent.get_prompt()
    
    def get_permanent(self, key: str, default=None):
        return self.permanent.get(key, default)
    
    def reload_permanent(self):
        self.permanent.reload()
    
    # ========== 统计 ==========
    
    def get_stats(self) -> dict:
        return {
            "short_term": {
                "message_count": len(self.short_term.get_messages())
            },
            "long_term": self.long_term.get_stats(),
            "permanent": {
                "config_path": str(self.permanent.config_path)
            }
        }
    
    def close(self):
        pass