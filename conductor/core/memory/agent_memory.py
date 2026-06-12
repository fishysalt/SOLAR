"""Agent 记忆管理 - 三类记忆（完整压缩实现）"""

import json
import yaml
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import sqlite3


class ShortTermMemory:
    """短期记忆 - 滑动窗口 + LLM 自动摘要"""
    
    def __init__(self, max_messages: int = 30, llm_callback=None):
        """
        Args:
            max_messages: 最大消息条数（达到后触发压缩）
            llm_callback: LLM 回调函数，用于生成摘要
        """
        self.max_messages = max_messages
        self.messages: List[Dict[str, Any]] = []
        self.summary: Optional[str] = None
        self._lock = threading.Lock()
        self._llm_callback = llm_callback
    
    def set_llm_callback(self, callback):
        """设置 LLM 回调（在 Agent 初始化时设置）"""
        self._llm_callback = callback
    
    def add(self, role: str, content: str):
        """添加消息"""
        with self._lock:
            self.messages.append({
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat()
            })
            self._check_and_compress()
    
    def _check_and_compress(self):
        """检查是否需要压缩"""
        if len(self.messages) >= self.max_messages:
            self._compress()
    
    def _compress(self):
        """执行压缩：生成摘要，清除旧消息"""
        if len(self.messages) == 0:
            return
        
        # 生成摘要（使用 LLM）
        summary = self._generate_summary()
        
        if summary:
            # 如果有旧摘要，合并
            if self.summary:
                self.summary = f"【历史】{self.summary}\n【新增】{summary}"
            else:
                self.summary = summary
        
        # 保留最近一半的消息
        keep_count = self.max_messages // 2
        self.messages = self.messages[-keep_count:]
        
        print(f"   📝 短期记忆已压缩，保留 {keep_count} 条，摘要已更新")
    
    def _generate_summary(self) -> Optional[str]:
        """调用 LLM 生成摘要"""
        if not self._llm_callback:
            # 没有 LLM 回调时，使用简单摘要
            return self._simple_summary()
        
        try:
            # 准备要摘要的消息
            messages_to_summarize = self.messages[:-self.max_messages//2] if len(self.messages) > self.max_messages//2 else self.messages
            
            if not messages_to_summarize:
                return None
            
            # 构建对话文本
            conversation_text = []
            for msg in messages_to_summarize:
                role = "用户" if msg["role"] == "user" else "助手"
                conversation_text.append(f"{role}: {msg['content']}")
            
            conversation = "\n".join(conversation_text)
            
            # 调用 LLM 生成摘要
            summary_prompt = f"""请总结以下对话的核心内容，保留关键信息和上下文。用简洁的一段话概括：

{conversation}

总结："""
            
            # 这里需要调用 LLM，但为了解耦，使用回调
            result = self._llm_callback(summary_prompt)
            return result.strip() if result else None
            
        except Exception as e:
            print(f"   ⚠️ LLM 摘要生成失败: {e}")
            return self._simple_summary()
    
    def _simple_summary(self) -> str:
        """简单摘要（无 LLM 时的降级方案）"""
        if not self.messages:
            return ""
        
        # 提取前几条消息的关键词
        important_topics = []
        for msg in self.messages[:5]:
            content = msg["content"][:50]
            important_topics.append(content)
        
        return f"对话涉及: {'; '.join(important_topics)}..."
    
    def needs_compression(self) -> bool:
        """检查是否需要压缩"""
        with self._lock:
            return len(self.messages) >= self.max_messages
    
    def get_messages(self) -> List[Dict]:
        with self._lock:
            return self.messages.copy()
    
    def get_context(self) -> List[Dict]:
        """获取上下文（包含摘要和历史消息）"""
        with self._lock:
            context = []
            if self.summary:
                context.append({
                    "role": "system",
                    "content": f"[对话历史摘要] {self.summary}"
                })
            context.extend(self.messages)
            return context
    
    def clear(self):
        """手动清空短期记忆"""
        with self._lock:
            self.messages = []
            self.summary = None
            print("   🗑️ 短期记忆已手动清空")
    
    def get_stats(self) -> dict:
        with self._lock:
            return {
                "message_count": len(self.messages),
                "has_summary": self.summary is not None,
                "max_messages": self.max_messages,
                "summary_length": len(self.summary) if self.summary else 0
            }


class LongTermMemory:
    """长期记忆 - 持久化存储（线程安全）"""
    
    def __init__(self, agent_name: str, memory_dir: Path):
        self.agent_name = agent_name
        self._local = threading.local()
        self._lock = threading.Lock()
        
        self.db_path = memory_dir / "long_term" / "memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"   📂 长期记忆数据库: {self.db_path}")
        
        self._init_db()
    
    def _get_connection(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._local.cursor = self._local.conn.cursor()
        return self._local.conn, self._local.cursor
    
    def _init_db(self):
        conn, cursor = self._get_connection()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT,
                importance REAL DEFAULT 0.5,
                created_at TEXT,
                metadata TEXT
            )
        """)
        conn.commit()
    
    def add(self, content: str, category: str = "general", importance: float = 0.5, metadata: dict = None) -> int:
        with self._lock:
            conn, cursor = self._get_connection()
            cursor.execute(
                "INSERT INTO memories (content, category, importance, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
                (content, category, importance, datetime.now().isoformat(), json.dumps(metadata or {}))
            )
            conn.commit()
            return cursor.lastrowid
    
    def search(self, keyword: str = None, category: str = None, limit: int = 10) -> List[Dict]:
        with self._lock:
            _, cursor = self._get_connection()
            
            if keyword:
                query = "SELECT id, content, category, importance, created_at FROM memories WHERE content LIKE ?"
                params = [f"%{keyword}%"]
            else:
                query = "SELECT id, content, category, importance, created_at FROM memories WHERE 1=1"
                params = []
            
            if category:
                query += " AND category = ?"
                params.append(category)
            
            query += " ORDER BY importance DESC, created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "content": row[1],
                    "category": row[2],
                    "importance": row[3],
                    "created_at": row[4]
                })
            return results
    
    def get_all(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            _, cursor = self._get_connection()
            cursor.execute(
                "SELECT id, content, category, importance, created_at FROM memories ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "content": row[1],
                    "category": row[2],
                    "importance": row[3],
                    "created_at": row[4]
                })
            return results
    
    def delete(self, memory_id: int) -> bool:
        with self._lock:
            conn, cursor = self._get_connection()
            cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_by_category(self, category: str) -> int:
        with self._lock:
            conn, cursor = self._get_connection()
            cursor.execute("DELETE FROM memories WHERE category = ?", (category,))
            conn.commit()
            return cursor.rowcount
    
    def delete_by_ids(self, ids: List[int]) -> int:
        if not ids:
            return 0
        with self._lock:
            conn, cursor = self._get_connection()
            placeholders = ','.join('?' * len(ids))
            cursor.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids)
            conn.commit()
            return cursor.rowcount
    
    def clear_all(self) -> int:
        with self._lock:
            conn, cursor = self._get_connection()
            cursor.execute("DELETE FROM memories")
            conn.commit()
            return cursor.rowcount
    
    def get_stats(self) -> dict:
        with self._lock:
            _, cursor = self._get_connection()
            cursor.execute("SELECT COUNT(*) FROM memories")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT category, COUNT(*) FROM memories GROUP BY category")
            by_category = dict(cursor.fetchall())
            
            return {"total": total, "by_category": by_category}
    
    def close(self):
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
            self._local.cursor = None


class PermanentMemory:
    """固定记忆 - 从 YAML 文件加载"""
    
    def __init__(self, agent_name: str, memory_dir: Path):
        self.agent_name = agent_name
        self._lock = threading.Lock()
        
        self.config_path = memory_dir / "permanent.yaml"
        self._data = self._load()
        print(f"   📂 固定记忆文件: {self.config_path}")
    
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
    """Agent 记忆管理器"""
    
    def __init__(self, agent_name: str, memory_dir: Path, llm_callback=None):
        self.agent_name = agent_name
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"🧠 {agent_name} 记忆系统初始化")
        print(f"   记忆目录: {self.memory_dir}")
        
        # 初始化三类记忆
        self.short_term = ShortTermMemory(max_messages=30, llm_callback=llm_callback)
        self.long_term = LongTermMemory(agent_name, self.memory_dir)
        self.permanent = PermanentMemory(agent_name, self.memory_dir)
        
        self.short_term_file = self.memory_dir / "short_term.json"
        self._load_short_term_from_file()
        
        print(f"   ✅ 记忆系统就绪")
    
    def set_llm_callback(self, callback):
        """设置 LLM 回调（由 Agent 在初始化后调用）"""
        self.short_term.set_llm_callback(callback)
    
    def _load_short_term_from_file(self):
        if self.short_term_file.exists():
            try:
                with open(self.short_term_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.short_term.messages = data
                    if isinstance(data, dict) and "messages" in data:
                        self.short_term.messages = data["messages"]
                        self.short_term.summary = data.get("summary")
                print(f"   📂 已加载 {len(self.short_term.messages)} 条短期记忆")
            except Exception as e:
                print(f"   ⚠️ 加载短期记忆失败: {e}")
    
    def _save_short_term_to_file(self):
        try:
            data = {
                "messages": self.short_term.messages,
                "summary": self.short_term.summary,
                "updated_at": datetime.now().isoformat()
            }
            with open(self.short_term_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"   ⚠️ 保存短期记忆失败: {e}")
    
    def add_short_term(self, role: str, content: str):
        """添加短期记忆（自动触发压缩）"""
        self.short_term.add(role, content)
        self._save_short_term_to_file()
    
    def get_short_term_context(self) -> List[Dict]:
        """获取短期记忆上下文（包含摘要）"""
        return self.short_term.get_context()
    
    def clear_short_term(self):
        """手动清空短期记忆"""
        self.short_term.clear()
        self._save_short_term_to_file()
    
    def get_short_term_stats(self) -> dict:
        """获取短期记忆统计"""
        return self.short_term.get_stats()
    
    def add_long_term(self, content: str, category: str = "general", importance: float = 0.5) -> int:
        return self.long_term.add(content, category, importance)
    
    def search_long_term(self, keyword: str = None, category: str = None, limit: int = 10) -> List[Dict]:
        return self.long_term.search(keyword, category, limit)
    
    def get_long_term_all(self, limit: int = 50) -> List[Dict]:
        return self.long_term.get_all(limit)
    
    def delete_long_term(self, memory_id: int) -> bool:
        return self.long_term.delete(memory_id)
    
    def delete_long_term_batch(self, ids: List[int]) -> int:
        return self.long_term.delete_by_ids(ids)
    
    def clear_long_term_by_category(self, category: str) -> int:
        return self.long_term.delete_by_category(category)
    
    def clear_long_term(self) -> int:
        return self.long_term.clear_all()
    
    def get_permanent_prompt(self) -> str:
        return self.permanent.get_prompt()
    
    def get_permanent(self, key: str, default=None):
        return self.permanent.get(key, default)
    
    def reload_permanent(self):
        self.permanent.reload()
    
    def get_stats(self) -> dict:
        return {
            "short_term": self.short_term.get_stats(),
            "long_term": self.long_term.get_stats()
        }
    
    def close(self):
        self._save_short_term_to_file()
        self.long_term.close()