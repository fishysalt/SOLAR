"""状态注册器 - 单例，管理所有 Agent 的状态"""

import json
import threading
import pymysql
import importlib
from typing import Optional, Dict, Any, List
from .models import StateInfo


class StateRegistry:
    """状态注册器 - 单例"""

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

        self._states: Dict[str, StateInfo] = {}          # state_id -> StateInfo
        self._agent_states: Dict[str, List[str]] = {}   # agent_name -> [state_ids]
        self._lock = threading.Lock()
        self._mysql_config = None

        print("📌 状态注册器已初始化")

    def init_mysql(self, mysql_config: Dict):
        """初始化MySQL连接配置"""
        self._mysql_config = mysql_config
        self._ensure_table()

    def _get_mysql_connection(self):
        if not self._mysql_config:
            raise Exception("MySQL配置未初始化")
        return pymysql.connect(
            host=self._mysql_config.get("host", "localhost"),
            port=self._mysql_config.get("port", 3306),
            user=self._mysql_config.get("user", "solar_ma"),
            password=self._mysql_config.get("password", ""),
            database=self._mysql_config.get("database", "solar_ma"),
            charset='utf8mb4',
            autocommit=True
        )

    def _ensure_table(self):
        """确保状态表存在"""
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES LIKE 'agent_states'")
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE TABLE `agent_states` (
                        `id` BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        `agent_name` VARCHAR(50) NOT NULL,
                        `state_id` VARCHAR(50) NOT NULL,
                        `description` TEXT NOT NULL,
                        `handler_module` VARCHAR(255) NOT NULL,
                        `handler_name` VARCHAR(100) NOT NULL,
                        `estimated_duration` FLOAT DEFAULT 0.0,
                        `permission_level` INT DEFAULT 1,
                        `execution_count` INT DEFAULT 0,
                        `is_final` TINYINT(1) DEFAULT 0,
                        `is_available` BOOLEAN DEFAULT TRUE,
                        `order` INT DEFAULT 0,
                        `extra_metadata` JSON NULL,
                        `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                        `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY `uk_agent_state` (`agent_name`, `state_id`),
                        INDEX `idx_agent_name` (`agent_name`)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
            cursor.close()
            conn.close()
            print("✅ 状态表已就绪")
        except Exception as e:
            print(f"⚠️ 状态表检查失败: {e}")

    def load_states_for_agent(self, agent_name: str) -> int:
        """
        加载指定 Agent 的所有状态并注册到内存
        返回加载的状态数量
        """
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("""
                SELECT * FROM agent_states
                WHERE agent_name = %s AND is_available = TRUE
                ORDER BY `order` ASC
            """, (agent_name,))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"⚠️ 加载状态失败: {e}")
            return 0

        count = 0
        for row in rows:
            try:
                # 动态导入处理函数
                module = importlib.import_module(row['handler_module'])
                handler = getattr(module, row['handler_name'])
                if not callable(handler):
                    print(f"⚠️ 状态 {row['state_id']} 的处理函数不可调用")
                    continue

                state_info = StateInfo(
                    state_id=row['state_id'],
                    description=row['description'],
                    handler=handler,
                    estimated_duration=row.get('estimated_duration', 0.0),
                    permission_level=row.get('permission_level', 1),
                    execution_count=row.get('execution_count', 0),
                    is_final=bool(row.get('is_final', 0)),
                    is_available=row.get('is_available', True),
                    extra_metadata=row.get('extra_metadata', {})
                )
                with self._lock:
                    self._states[state_info.state_id] = state_info
                    if agent_name not in self._agent_states:
                        self._agent_states[agent_name] = []
                    if state_info.state_id not in self._agent_states[agent_name]:
                        self._agent_states[agent_name].append(state_info.state_id)
                count += 1
                print(f"   📌 状态: {state_info.state_id} ({state_info.description[:30]})")
            except Exception as e:
                print(f"⚠️ 注册状态 {row['state_id']} 失败: {e}")
        return count

    def get_state(self, state_id: str) -> Optional[StateInfo]:
        """获取状态信息"""
        with self._lock:
            return self._states.get(state_id)

    def get_agent_state_list(self, agent_name: str, level: int = 1) -> List[StateInfo]:
        with self._lock:
            state_ids = self._agent_states.get(agent_name, [])
            return [self._states[sid] for sid in state_ids if sid in self._states and self._states[sid].permission_level <= level]

    def update_state_execution(self, state_id: str) -> bool:
        """增加状态的执行次数（内存中+1），并异步更新数据库"""
        with self._lock:
            state = self._states.get(state_id)
            if not state:
                return False
            state.execution_count += 1
            # 异步更新数据库（使用线程）
            import threading
            threading.Thread(target=self._update_db_execution_count, args=(state_id, state.execution_count), daemon=True).start()
            return True

    def _update_db_execution_count(self, state_id: str, count: int):
        """更新数据库中的 execution_count（同步）"""
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE agent_states
                SET execution_count = %s, updated_at = NOW()
                WHERE state_id = %s
            """, (count, state_id))
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"⚠️ 更新状态执行计数失败: {e}")


# 全局单例
_state_registry = None

def get_state_registry() -> StateRegistry:
    """获取状态注册器单例"""
    global _state_registry
    if _state_registry is None:
        _state_registry = StateRegistry()
    return _state_registry