"""数据库初始化脚本 - 创建所有Agent的表"""

import pymysql
import yaml
from pathlib import Path

AGENTS = ["conductor", "creator", "scavenger", "engineer"]


def get_mysql_config():
    """从 config.yaml 读取 MySQL 配置"""
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            return config.get("memory", {}).get("mysql", {})
    return {}


def init_database():
    """初始化所有Agent的表"""
    mysql_config = get_mysql_config()
    
    if not mysql_config:
        print("❌ 未找到 MySQL 配置，请检查 config.yaml")
        return
    
    conn = pymysql.connect(
        host=mysql_config.get("host", "localhost"),
        port=mysql_config.get("port", 3306),
        user=mysql_config.get("user", "solar_ma"),
        password=mysql_config.get("password", ""),
        database=mysql_config.get("database", "solar_ma"),
        charset='utf8mb4',
        autocommit=True
    )
    
    cursor = conn.cursor()
    
    for agent in AGENTS:
        print(f"📋 创建 {agent} 的表...")
        
        # 完整版
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {agent}_task_memories_raw (
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
        
        # 摘要版
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {agent}_task_memories_summary (
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
        
        print(f"✅ {agent} 表创建完成")
    
    cursor.close()
    conn.close()
    print("🎉 所有表初始化完成")


if __name__ == "__main__":
    init_database()