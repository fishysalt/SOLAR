"""错误日志管理器 - 统一错误记录和索引"""
import json
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List  # ← 添加这行
import threading

class ErrorLogger:
    """错误日志管理器（单例）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.error_dir = Path(__file__).parent / "errors"
        self.error_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.error_dir / "index.json"
        self._load_index()
    
    def _load_index(self):
        """加载错误索引"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self.index = json.load(f)
                return
            except:
                pass
        self.index = {"errors": [], "total": 0}
    
    def _save_index(self):
        """保存错误索引"""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)
    
    def _generate_error_id(self, agent: str) -> str:
        """生成错误 ID"""
        self.index["total"] += 1
        return f"{agent}_error_{self.index['total']:03d}"
    
    def log_error(self, agent: str, original_task: str, error_info: Dict[str, Any]) -> str:
        """
        记录错误日志
        
        Args:
            agent: 出错的 Agent 名称
            original_task: 原始任务描述
            error_info: 错误信息（包含 type, tool, message, args, traceback 等）
        
        Returns:
            error_id: 错误 ID，用于后续引用
        """
        error_id = self._generate_error_id(agent)
        timestamp = datetime.now().isoformat()
        
        error_log = {
            "error_id": error_id,
            "timestamp": timestamp,
            "agent": agent,
            "original_task": original_task,
            "error": error_info,
            "context": {
                "tool_calls_history": [],
                "iteration": 0,
                "max_iterations": 20
            },
            "status": "open"
        }
        
        # 保存错误日志文件
        filepath = self.error_dir / f"{error_id}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(error_log, f, ensure_ascii=False, indent=2)
        
        # 更新索引
        self.index["errors"].append({
            "error_id": error_id,
            "timestamp": timestamp,
            "agent": agent,
            "status": "open",
            "file": f"{error_id}.json"
        })
        self._save_index()
        
        return error_id
    
    def get_error(self, error_id: str) -> Optional[Dict[str, Any]]:
        """获取错误日志内容"""
        filepath = self.error_dir / f"{error_id}.json"
        if not filepath.exists():
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def mark_fixed(self, error_id: str, diagnosis: str, solution: str, files_modified: list) -> str:
        """
        标记错误为已修复，记录修复方案
        
        Args:
            error_id: 错误 ID
            diagnosis: 诊断结果
            solution: 解决方案
            files_modified: 修改的文件列表
        
        Returns:
            fixed_file_path: 修复记录文件路径
        """
        error_log = self.get_error(error_id)
        if not error_log:
            return f"❌ 错误 {error_id} 不存在"
        
        error_log["status"] = "fixed"
        
        # 更新原始错误日志
        filepath = self.error_dir / f"{error_id}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(error_log, f, ensure_ascii=False, indent=2)
        
        # 创建修复记录
        fixed_record = {
            "error_id": error_id,
            "fixed_at": datetime.now().isoformat(),
            "fixed_by": "engineer",
            "diagnosis": diagnosis,
            "solution": solution,
            "files_modified": files_modified,
            "verification": "待验证",
            "status": "pending_verification"
        }
        
        fixed_file = self.error_dir / f"{error_id}_fixed.json"
        with open(fixed_file, 'w', encoding='utf-8') as f:
            json.dump(fixed_record, f, ensure_ascii=False, indent=2)
        
        # 更新索引
        for entry in self.index["errors"]:
            if entry["error_id"] == error_id:
                entry["status"] = "fixed"
                entry["fixed_file"] = f"{error_id}_fixed.json"
                break
        self._save_index()
        
        return str(fixed_file)
    
    def get_open_errors(self, agent: str = None) -> List[Dict]:
        """获取所有未修复的错误"""
        if agent:
            return [e for e in self.index["errors"] if e["status"] == "open" and e["agent"] == agent]
        return [e for e in self.index["errors"] if e["status"] == "open"]
    
    def get_error_path(self, error_id: str) -> str:
        """获取错误日志文件路径（供主 Agent 返回给用户）"""
        return str(self.error_dir / f"{error_id}.json")


# 全局单例
_error_logger = None

def get_error_logger() -> ErrorLogger:
    global _error_logger
    if _error_logger is None:
        _error_logger = ErrorLogger()
    return _error_logger