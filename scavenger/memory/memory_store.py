"""记忆存储层 - Redis（工作记忆）+ MySQL（长期记忆）"""

import json
import redis
import pymysql
from typing import Optional, Dict, Any, List
from datetime import datetime


def _json_default(obj):
    """JSON 序列化时的默认处理器"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, '__dict__'):
        return str(obj)
    return str(obj)


class MemoryStore:
    """统一记忆存储接口"""
    
    def __init__(self, agent_name: str, config: Dict = None):
        self.agent_name = agent_name
        self.config = config or {}
        
        # ========== Redis 连接 ==========
        redis_config = self.config.get("redis", {})
        try:
            self.redis_client = redis.Redis(
                host=redis_config.get("host", "localhost"),
                port=redis_config.get("port", 6379),
                db=redis_config.get("db", 0),
                decode_responses=True
            )
            self.redis_client.ping()
            print(f"✅ Redis 连接成功: {redis_config.get('host', 'localhost')}:{redis_config.get('port', 6379)}")
        except Exception as e:
            print(f"⚠️ Redis 连接失败: {e}，将使用内存模式")
            self.redis_client = None
        
        # ========== MySQL 连接配置 ==========
        self.mysql_config = self.config.get("mysql", {})
        # 确保密码是字符串
        if "password" in self.mysql_config:
            self.mysql_config["password"] = str(self.mysql_config["password"])
        
        # 初始化表
        self._init_tables()
    
    def _get_mysql_connection(self):
        """获取 MySQL 连接"""
        try:
            return pymysql.connect(
                host=self.mysql_config.get("host", "localhost"),
                port=self.mysql_config.get("port", 3306),
                user=self.mysql_config.get("user", "solar_ma"),
                password=self.mysql_config.get("password", ""),
                database=self.mysql_config.get("database", "solar_ma"),
                charset='utf8mb4',
                autocommit=True
            )
        except Exception as e:
            print(f"⚠️ MySQL 连接失败: {e}")
            raise
    
    def _init_tables(self):
        """初始化表结构"""
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.agent_name}_task_memories_raw (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    task_id VARCHAR(64) NOT NULL UNIQUE,
                    user_id VARCHAR(64) NOT NULL,
                    instruction TEXT,
                    final_result TEXT,
                    isolated_memory JSON,
                    subtasks JSON,
                    duration INT DEFAULT 0,
                    iteration_count INT DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    INDEX idx_user_id (user_id),
                    INDEX idx_completed_at (completed_at)
                )
            """)
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.agent_name}_task_memories_summary (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    task_id VARCHAR(64) NOT NULL UNIQUE,
                    user_id VARCHAR(64) NOT NULL,
                    summary TEXT NOT NULL,
                    key_points JSON,
                    lessons_learned TEXT,
                    useful_tools_used JSON,
                    instruction_preview VARCHAR(200),
                    result_preview VARCHAR(200),
                    tags JSON,
                    importance_score FLOAT DEFAULT 0.5,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    INDEX idx_user_id (user_id),
                    INDEX idx_completed_at (completed_at),
                    FULLTEXT idx_summary (summary)
                )
            """)
            
            cursor.close()
            conn.close()
            print(f"✅ {self.agent_name} 表已就绪")
        except Exception as e:
            print(f"⚠️ 表初始化跳过: {e}")
    
    # ========== Redis 操作（工作记忆） ==========
    
    def _task_memory_key(self, task_id: str) -> str:
        return f"{self.agent_name}:task:{task_id}:memory"
    
    def _recent_summaries_key(self, user_id: str) -> str:
        return f"{self.agent_name}:memory:recent_summaries:{user_id}"
    
    def save_task_memory(self, task_id: str, memory: List[Dict]):
        """存储任务独立记忆到Redis"""
        if not self.redis_client:
            return
        key = self._task_memory_key(task_id)
        self.redis_client.setex(
            key,
            7 * 24 * 3600,
            json.dumps(memory, ensure_ascii=False, default=_json_default)
        )
    
    def get_task_memory(self, task_id: str) -> Optional[List[Dict]]:
        """获取任务独立记忆"""
        if not self.redis_client:
            return None
        key = self._task_memory_key(task_id)
        data = self.redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    
    def delete_task_memory(self, task_id: str):
        """删除任务独立记忆"""
        if self.redis_client:
            self.redis_client.delete(self._task_memory_key(task_id))
    
    # ========== Redis 缓存（最近摘要） ==========
    
    def cache_recent_summaries_to_redis(self, user_id: str, summaries: List[Dict]):
        """缓存最近任务摘要到Redis（1小时过期）"""
        if not self.redis_client:
            return
        key = self._recent_summaries_key(user_id)
        self.redis_client.setex(
            key,
            3600,
            json.dumps(summaries, ensure_ascii=False, default=_json_default)
        )
        print(f"📦 缓存摘要到Redis: user={user_id}, count={len(summaries)}")
    
    def get_recent_summaries_from_redis(self, user_id: str) -> Optional[List[Dict]]:
        """从Redis获取缓存的摘要"""
        if not self.redis_client:
            return None
        key = self._recent_summaries_key(user_id)
        data = self.redis_client.get(key)
        if data:
            try:
                return json.loads(data)
            except:
                return None
        return None
    
    def clear_recent_summaries_cache(self, user_id: str):
        """清除用户的摘要缓存"""
        if self.redis_client:
            self.redis_client.delete(self._recent_summaries_key(user_id))
            print(f"🗑️ 清除摘要缓存: user={user_id}")
    
    # ========== MySQL 操作 ==========
    
    def save_raw_memory(
        self,
        task_id: str,
        user_id: str,
        instruction: str,
        final_result: str,
        isolated_memory: List[Dict],
        subtasks: List[Dict],
        duration: float,
        iteration_count: int,
        completed_at: datetime
    ):
        """存储完整版任务记忆"""
        conn = self._get_mysql_connection()
        cursor = conn.cursor()
        
        sql = f"""
            INSERT INTO {self.agent_name}_task_memories_raw 
            (task_id, user_id, instruction, final_result, isolated_memory, subtasks, duration, iteration_count, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                final_result = VALUES(final_result),
                isolated_memory = VALUES(isolated_memory),
                duration = VALUES(duration),
                iteration_count = VALUES(iteration_count),
                completed_at = VALUES(completed_at)
        """
        
        cursor.execute(
            sql,
            (
                task_id,
                user_id,
                instruction,
                final_result,
                json.dumps(isolated_memory, ensure_ascii=False, default=_json_default),
                json.dumps(subtasks, ensure_ascii=False, default=_json_default),
                int(duration),
                iteration_count,
                completed_at
            )
        )
        
        cursor.close()
        conn.close()
    
    def save_summary_memory(
        self,
        task_id: str,
        user_id: str,
        summary: str,
        key_points: List[str],
        lessons_learned: str,
        useful_tools_used: List[str],
        instruction_preview: str,
        result_preview: str,
        tags: List[str],
        importance_score: float,
        completed_at: datetime
    ):
        """存储摘要版任务记忆"""
        conn = self._get_mysql_connection()
        cursor = conn.cursor()
        
        sql = f"""
            INSERT INTO {self.agent_name}_task_memories_summary 
            (task_id, user_id, summary, key_points, lessons_learned, useful_tools_used,
             instruction_preview, result_preview, tags, importance_score, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                summary = VALUES(summary),
                key_points = VALUES(key_points),
                lessons_learned = VALUES(lessons_learned),
                useful_tools_used = VALUES(useful_tools_used),
                instruction_preview = VALUES(instruction_preview),
                result_preview = VALUES(result_preview),
                tags = VALUES(tags),
                importance_score = VALUES(importance_score),
                completed_at = VALUES(completed_at)
        """
        
        cursor.execute(
            sql,
            (
                task_id,
                user_id,
                summary,
                json.dumps(key_points, ensure_ascii=False, default=_json_default),
                lessons_learned,
                json.dumps(useful_tools_used, ensure_ascii=False, default=_json_default),
                instruction_preview[:200],
                result_preview[:200] if result_preview else "",
                json.dumps(tags, ensure_ascii=False, default=_json_default),
                importance_score,
                completed_at
            )
        )
        
        cursor.close()
        conn.close()
        
        # 清除该用户的Redis摘要缓存
        self.clear_recent_summaries_cache(user_id)
    
    def get_recent_summaries_from_mysql(self, user_id: str, limit: int = 3) -> List[Dict]:
        """从MySQL获取最近N个任务的摘要"""
        conn = self._get_mysql_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        sql = f"""
            SELECT 
                task_id,
                summary,
                key_points,
                lessons_learned,
                useful_tools_used,
                instruction_preview,
                result_preview,
                tags,
                importance_score,
                completed_at
            FROM {self.agent_name}_task_memories_summary
            WHERE user_id = %s
            ORDER BY completed_at DESC
            LIMIT %s
        """
        
        cursor.execute(sql, (user_id, limit))
        return cursor.fetchall()
    
    def search_summaries(self, user_id: str, keyword: str, limit: int = 10) -> List[Dict]:
        """按关键词搜索摘要（供长期记忆检索使用）"""
        conn = self._get_mysql_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        sql = f"""
            SELECT 
                task_id,
                summary,
                key_points,
                lessons_learned,
                useful_tools_used,
                instruction_preview,
                result_preview,
                tags,
                importance_score,
                completed_at
            FROM {self.agent_name}_task_memories_summary
            WHERE user_id = %s 
            AND (
                summary LIKE %s 
                OR instruction_preview LIKE %s 
                OR result_preview LIKE %s
            )
            ORDER BY importance_score DESC, completed_at DESC
            LIMIT %s
        """
        
        like_pattern = f"%{keyword}%"
        cursor.execute(sql, (user_id, like_pattern, like_pattern, like_pattern, limit))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return results

    def get_recent_summaries(self, user_id: str, limit: int = 3) -> List[Dict]:
        """获取最近N个任务的摘要（Redis优先，MySQL兜底）"""
        cached = self.get_recent_summaries_from_redis(user_id)
        if cached is not None:
            return cached[:limit]
        
        summaries = self.get_recent_summaries_from_mysql(user_id, limit)
        self.cache_recent_summaries_to_redis(user_id, summaries)
        return summaries
    
    def get_recent_summaries_sync(self, user_id: str, limit: int = 3) -> List[Dict]:
        """同步版本"""
        return self.get_recent_summaries(user_id, limit)
    
    def get_stats(self) -> Dict:
        """获取存储统计"""
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT COUNT(*) FROM {self.agent_name}_task_memories_raw")
            raw_count = cursor.fetchone()[0]
            
            cursor.execute(f"SELECT COUNT(*) FROM {self.agent_name}_task_memories_summary")
            summary_count = cursor.fetchone()[0]
            
            redis_keys = 0
            if self.redis_client:
                redis_keys = len(self.redis_client.keys(f"{self.agent_name}:task:*"))
            
            cursor.close()
            conn.close()
            
            return {
                "agent": self.agent_name,
                "raw_memories": raw_count,
                "summary_memories": summary_count,
                "redis_task_memories": redis_keys
            }
        except:
            return {"agent": self.agent_name, "raw_memories": 0, "summary_memories": 0}