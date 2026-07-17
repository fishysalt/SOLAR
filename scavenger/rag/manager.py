"""RAG 工作经验管理器 - 负责分类、存储、检索"""

import re
from typing import Optional, Dict, Any, List
from datetime import datetime
import pymysql
import json

from .models import RAGExperience, RAGCategory


class RAGManager:
    """RAG 工作经验管理器"""
    
    def __init__(self, mysql_config: Dict[str, Any]):
        self.mysql_config = mysql_config
    
    def _get_mysql_connection(self):
        """获取 MySQL 连接"""
        return pymysql.connect(
            host=self.mysql_config.get("host", "localhost"),
            port=self.mysql_config.get("port", 3306),
            user=self.mysql_config.get("user", "solar_ma"),
            password=self.mysql_config.get("password", ""),
            database=self.mysql_config.get("database", "solar_ma"),
            charset='utf8mb4',
            autocommit=True
        )
    
    def _get_table_name(self, agent_name: str, category: str) -> str:
        """生成 RAG 表名"""
        clean_category = re.sub(r'[^a-zA-Z0-9_]', '_', category)
        return f"rag_{agent_name}_{clean_category}"
    
    # ========== 分类管理 ==========
    
    def get_all_categories(self, agent_name: str) -> List[RAGCategory]:
        """获取 Agent 的所有 RAG 分类"""
        conn = self._get_mysql_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        cursor.execute(f"""
            SELECT table_name, agent_name, category, description, created_at
            FROM rag_experience_types
            WHERE agent_name = %s
            ORDER BY created_at DESC
        """, (agent_name,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return [
            RAGCategory(
                table_name=r['table_name'],
                agent_name=r['agent_name'],
                category=r['category'],
                description=r['description'],
                created_at=r['created_at']
            )
            for r in results
        ]
    
    def _ensure_category_table(self, agent_name: str, category: str, description: str = None) -> str:
        """确保分类表存在，不存在则创建"""
        table_name = self._get_table_name(agent_name, category)
        
        conn = self._get_mysql_connection()
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute(f"""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = '{table_name}'
        """)
        exists = cursor.fetchone()[0] > 0
        
        if not exists:
            # 创建表
            cursor.execute(f"""
                CREATE TABLE {table_name} (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    task_id VARCHAR(64) NOT NULL,
                    user_id VARCHAR(64) NOT NULL,
                    instruction VARCHAR(500),
                    summary TEXT,
                    state_path VARCHAR(200),
                    key_steps TEXT,
                    result_preview VARCHAR(500),
                    success BOOLEAN DEFAULT TRUE,
                    time_cost INT DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user_id (user_id),
                    INDEX idx_created_at (created_at)
                )
            """)
            print(f"✅ 创建 RAG 表: {table_name}")
            
            # 记录到经验类型表
            cursor.execute(f"""
                INSERT INTO rag_experience_types (table_name, agent_name, category, description)
                VALUES (%s, %s, %s, %s)
            """, (table_name, agent_name, category, description or category))
        
        cursor.close()
        conn.close()
        return table_name
    
    def classify_category(self, agent_name: str, instruction: str, summary: str, llm_call_func) -> str:
        """
        使用 LLM 判断经验属于哪个分类
        
        Args:
            agent_name: Agent 名称
            instruction: 任务指令
            summary: 经验总结
            llm_call_func: LLM 调用函数 (prompt) -> str
        
        Returns:
            分类名称
        """
        existing = self.get_all_categories(agent_name)
        category_list = "\n".join([
            f"- {c.category}: {c.description or c.category}"
            for c in existing
        ]) if existing else "（暂无分类）"
        
        prompt = f"""你是一个经验分类专家。请判断以下任务经验属于哪个分类。

【已有分类】
{category_list}

【任务指令】
{instruction[:200]}

【经验总结】
{summary[:200]}

规则：
1. 如果已有分类中有匹配的，返回该分类名称
2. 如果没有匹配的，根据任务内容创建一个新的分类名称（简短、英文、小写、用下划线连接）
3. 只返回分类名称，不要其他内容

示例：video_generate, model_generate, web_search, error_fix, tool_generate"""
        
        try:
            result = llm_call_func(prompt, temperature=0.3)
            category = result.strip().lower().replace(' ', '_')
            category = re.sub(r'[^a-zA-Z0-9_]', '', category)
            return category or "general"
        except Exception as e:
            print(f"⚠️ 分类失败: {e}")
            return "general"
    
    # ========== 经验存储 ==========
    
    def save_experience(self, agent_name: str, exp: RAGExperience) -> str:
        """
        保存工作经验
        
        Returns:
            分类名称
        """
        # 1. 确保表存在
        table_name = self._get_table_name(agent_name, exp.category)
        self._ensure_category_table(agent_name, exp.category)
        
        # 2. 插入数据
        conn = self._get_mysql_connection()
        cursor = conn.cursor()
        
        sql = f"""
            INSERT INTO {table_name} 
            (task_id, user_id, instruction, summary, state_path, key_steps, 
             result_preview, success, time_cost)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        cursor.execute(sql, (
            exp.task_id,
            exp.user_id,
            exp.instruction[:500],
            exp.summary,
            exp.state_path,
            exp.key_steps,
            exp.result_preview[:500],
            exp.success,
            exp.time_cost
        ))
        
        cursor.close()
        conn.close()
        print(f"✅ RAG 经验已保存: {table_name}")
        
        return exp.category
    
    # ========== 经验检索 ==========
    
    def get_experiences(self, agent_name: str, category: str, user_id: str = None, limit: int = 10) -> List[Dict]:
        """获取最近的经验记录"""
        table_name = self._get_table_name(agent_name, category)
        
        conn = self._get_mysql_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 检查表是否存在
        cursor.execute(f"""
            SELECT COUNT(*) as cnt FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = '{table_name}'
        """)
        if cursor.fetchone()['cnt'] == 0:
            cursor.close()
            conn.close()
            return []
        
        if user_id:
            sql = f"""
                SELECT * FROM {table_name}
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """
            cursor.execute(sql, (user_id, limit))
        else:
            sql = f"""
                SELECT * FROM {table_name}
                ORDER BY created_at DESC
                LIMIT %s
            """
            cursor.execute(sql, (limit,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    
    def get_all_experiences_by_category(self, agent_name: str, category: str, limit: int = 10) -> List[Dict]:
        """按分类获取经验（简化版）"""
        return self.get_experiences(agent_name, category, limit=limit)